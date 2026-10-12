"""Agent loop: LLM -> tool calls -> guardrail -> tool results -> LLM, until text reply."""
import json, re
from .data import Store, TODAY
from .tools import TOOLS, TOOL_SPECS
from .policy import refund_allowed, check_verification
from .prompt import SYSTEM_PROMPT

# Extra (non-spec) tool so the model can record verification. Spec has no verify
# endpoint -- TODO(Priyansh): decide whether to keep this or verify in-prompt only.
VERIFY_SPEC = {"name": "verify_customer", "description": "Check the email + card last 4 the customer gave. Required before discussing account details.",
               "parameters": {"type": "object", "properties": {"email": {"type": "string"}, "last4": {"type": "string"}}, "required": ["email", "last4"]}}

MAX_STEPS = 8
MAX_USER_CHARS = 4000
FRAUD_RE = re.compile(r"fraud|unauthori[sz]ed|stol(e|en)|didn'?t (make|authori[sz]e)|did not (make|authori[sz]e)|wasn'?t me|not me|hacked|someone (used|took|charged)|scam", re.I)
TIMELINE_RE = re.compile(r"(follow(?:s|ing)?[- ]up|get back to you|contact you|reach out|be in touch|respond)([^.!?\n]*?)\b(today|tonight|tomorrow|shortly|soon|right away|asap|within [^.!?,\n]*?(?:minutes?|hours?|days?)|in (?:a few|\d+) (?:minutes?|hours?|days?)|by (?:end of|eod|close of)[^.!?,\n]*)", re.I)


def sanitize_reply(text: str) -> str:
    """Code guardrail: never promise a follow-up timeline. Only 'a specialist will follow up by email'."""
    if not text:
        return text
    return TIMELINE_RE.sub(lambda m: m.group(1) + m.group(2).rstrip() + " by email", text)


class Agent:
    def __init__(self, provider, store: Store | None = None, system_prompt: str = SYSTEM_PROMPT, guardrail: bool = True):
        self.provider, self.store = provider, store or Store()
        # Inject today's date dynamically into the prompt
        self.system = system_prompt.replace("{{TODAY}}", TODAY.strftime("%Y-%m-%d"))
        self.guardrail = guardrail
        self.messages, self.session = [], {"verified": False, "customer_id": None, "failed_verifications": 0, "verification_locked": False, "fraud_claim": False}

    # ---- stateless serialization (serverless: state round-trips via signed client blob)
    def to_state(self) -> dict:
        st = self.store
        return {"messages": self.messages, "session": self.session,
                "refunds": st.refunds, "tickets": st.tickets, "calls": st.calls,
                "txn_status": {k: v["status"] for k, v in st.transactions.items()}}

    def load_state(self, state: dict):
        self.messages = state.get("messages", [])
        self.session.update(state.get("session", {}))
        st = self.store
        st.refunds = state.get("refunds", {}); st.tickets = state.get("tickets", {})
        st.calls = [tuple(c) for c in state.get("calls", [])]
        for k, v in state.get("txn_status", {}).items():
            if k in st.transactions: st.transactions[k]["status"] = v

    def _auto_escalate(self, customer_id, summary):
        """Deterministic escalation for spec-mandated cases (lockout, frozen card). Once per session."""
        key = "auto_escalated:" + summary[:20]
        if self.session.get(key):
            return {"escalation": "already_created"}
        self.session[key] = True
        res = TOOLS["escalate_to_human"](self.store, customer_id=customer_id, summary=summary)
        self.store.calls.append(("escalate_to_human", {"customer_id": customer_id, "summary": summary, "auto": True}, res))
        return {"escalation": "created_automatically", "ticket_id": res.get("ticket_id"),
                "tell_customer": "A specialist will follow up by email."}

    def _run_tool(self, name, args):
        # SECURITY: After 3 failed verification attempts, lock verification and force escalation
        if name == "verify_customer":
            if self.session["verification_locked"]:
                res = {"verified": False, "error": "verification_locked"}
            elif self.session.get("verified"):
                cid = check_verification(self.store, args.get("email"), args.get("last4"))
                res = ({"verified": True, "customer_id": cid} if cid == self.session["customer_id"]
                       else {"verified": False, "error": "already_verified_as_another_customer_restart_chat"})
            else:
                cid = check_verification(self.store, args.get("email"), args.get("last4"))
                if cid:
                    self.session.update(verified=True, customer_id=cid)
                    res = {"verified": True, "customer_id": cid}
                    cust = self.store.customers.get(cid, {})
                    if cust.get("status") == "frozen":   # spec: frozen card -> escalate (code-enforced)
                        res.update(card_status="frozen", freeze_reason=cust.get("freeze_reason"),
                                   **self._auto_escalate(cid, "Frozen card: customer contacted support; needs identity check/unfreeze review."))
                else:
                    self.session["failed_verifications"] += 1
                    if self.session["failed_verifications"] >= 3:
                        self.session["verification_locked"] = True
                        res = {"verified": False, "error": "verification_locked_after_3_attempts",
                               **self._auto_escalate("unverified", "3 failed verification attempts; session locked.")}
                    else:
                        res = {"verified": False}
        elif name == "get_customer":
            # SECURITY: no lookups before verification; only the verified customer's own record
            if not self.session.get("verified"):
                res = {"error": "verify_customer_first"}
            else:
                res = TOOLS[name](self.store, email=args.get("email", ""))
                if res.get("id") != self.session["customer_id"]:
                    res = {"error": "not_authorized_for_other_customers"}
                else:
                    res = {k: v for k, v in res.items() if k != "card_last4"}
        elif name == "get_transaction" and not self.session.get("verified"):
            res = {"error": "verify_customer_first"}
        elif name == "get_transaction":
            # Normalize transaction ID: extract T\d+ from inputs like "Amazon T105"
            txn_id = args.get("txn_id", "")
            match = re.search(r'[Tt]\d+', str(txn_id))
            if match:
                args = {**args, "txn_id": match.group(0).upper()}
            # SECURITY: always scope lookups to the verified customer
            args = {**args, "customer_id": self.session["customer_id"]}
            try:
                res = TOOLS[name](self.store, **args)
            except TypeError as e:
                res = {"error": f"bad_arguments: {e}"}
        elif name == "issue_refund" and self.guardrail:
            # SECURITY: Refuse refunds if verification is locked
            if self.session.get("verification_locked"):
                res = {"ok": False, "reason": "blocked_by_policy:verification_locked"}
            elif self.session.get("fraud_claim"):
                res = {"ok": False, "reason": "blocked_by_policy:fraud_claim_escalate"}
            else:
                m = re.search(r'[Tt]\d+', str(args.get("txn_id", "")))
                args = {**args, "txn_id": m.group(0).upper() if m else args.get("txn_id")}
                try: float(args.get("amount", 0))
                except (TypeError, ValueError): args = {**args, "amount": 0}
                ok, reason = refund_allowed(self.store, self.session, args.get("txn_id"), float(args.get("amount", 0)))
                res = TOOLS[name](self.store, **args) if ok else {"ok": False, "reason": f"blocked_by_policy:{reason}"}
        elif name == "escalate_to_human":
            # Escalation always allowed; bind to verified customer if known
            args = {"customer_id": self.session.get("customer_id") or args.get("customer_id") or "unverified",
                    "summary": str(args.get("summary", ""))[:1000]}
            try:
                res = TOOLS[name](self.store, **args)
            except TypeError as e:
                res = {"error": f"bad_arguments: {e}"}
        elif name in TOOLS:
            try:
                res = TOOLS[name](self.store, **args)
            except TypeError as e:
                res = {"error": f"bad_arguments: {e}"}
        else:
            res = {"error": f"unknown_tool {name}"}
        self.store.calls.append((name, args, res))
        return res

    def send(self, user_text: str) -> str:
        user_text = (user_text or "")[:MAX_USER_CHARS]
        if FRAUD_RE.search(user_text):
            self.session["fraud_claim"] = True   # code guardrail: no auto-refunds once fraud is claimed
        self.messages.append({"role": "user", "content": user_text})
        for _ in range(MAX_STEPS):
            out = self.provider.complete(self.system, self.messages, TOOL_SPECS + [VERIFY_SPEC])
            calls = out.get("tool_calls") or []
            self.messages.append({"role": "assistant", "content": out.get("text"), "tool_calls": calls} if calls
                                 else {"role": "assistant", "content": out.get("text") or ""})
            if not calls:
                text = sanitize_reply(out.get("text") or "")
                self.messages[-1]["content"] = text
                return text
            for c in calls:
                res = self._run_tool(c["name"], c["arguments"])
                self.messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": json.dumps(res)})
        return "Sorry, I'm having trouble with that request. Could you rephrase it, or tell me the transaction ID you need help with?"
