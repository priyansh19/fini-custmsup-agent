"""Agent loop: LLM -> tool calls -> guardrail -> tool results -> LLM, until text reply."""
import json, re
from .data import Store, TODAY
from .tools import TOOLS, TOOL_SPECS
from .policy import subscription_max_refund
from .policy import refund_allowed, check_verification
from .prompt import SYSTEM_PROMPT

# Extra (non-spec) tool so the model can record verification. Spec has no verify
# endpoint -- TODO(Priyansh): decide whether to keep this or verify in-prompt only.
VERIFY_SPEC = {"name": "verify_customer", "description": "Check the email + card last 4 the customer gave. Required before discussing account details.",
               "parameters": {"type": "object", "properties": {"email": {"type": "string"}, "last4": {"type": "string"}}, "required": ["email", "last4"]}}

MAX_STEPS = 8
MAX_USER_CHARS = 4000
TURN_BUDGET_S = 42   # whole-turn budget, inside Vercel's 60s function limit
FRAUD_RE = re.compile(r"fraud|unauthori[sz]ed|stol(e|en)|didn'?t (make|authori[sz]e)|did not (make|authori[sz]e)|wasn'?t me|not me|hacked|someone (used|took|charged)|scammed|scam (charge|transaction|payment)", re.I)
TIMELINE_RE = re.compile(r"(follow(?:s|ing)?[- ]up|get back to you|contact you|reach out|be in touch|respond)([^.!?\n]*?)\b(today|tonight|tomorrow|shortly|soon|right away|asap|within [^.!?,\n]*?(?:minutes?|hours?|days?)|in (?:a few|\d+) (?:minutes?|hours?|days?)|by (?:end of|eod|close of)[^.!?,\n]*)", re.I)

SOFT_TIMELINE_RE = re.compile(r"as (?:soon|quickly|fast) as (?:possible|they can|we can)|at the earliest|within (?:the )?(?:next )?(?:\d+|a few|one|two|24|48)\b|\b(?:24|48|72)[- ]?hours?\b|business days?", re.I)


def sanitize_reply(text: str) -> str:
    """Code guardrail: never promise a follow-up timeline. Only 'a specialist will follow up by email'."""
    if not text:
        return text
    std = "A specialist will follow up by email."
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for p in parts:
        if TIMELINE_RE.search(p) or SOFT_TIMELINE_RE.search(p):
            p = std
        if p == std and std in out:
            continue
        out.append(p)
    return " ".join(out)


def normalize_txn_id(raw):
    m = re.search(r'(?i)\btxn[\s_-]*(\d{4,6})\b', str(raw))
    if m:
        return f"TXN-{m.group(1)}"
    bare = re.fullmatch(r'\s*#?(\d{5})\s*', str(raw))  # model sometimes passes just "58306"
    return f"TXN-{bare.group(1)}" if bare else str(raw).strip()


AFFIRM_RE = re.compile(r"\b(yes|yeah|yep|yup|sure|ok(ay)?|confirm(ed)?|go ahead|proceed|do it|please do|that'?s fine|fine|understood|i understand|agreed?|correct|cancel it)\b", re.I)
NEGATE_RE = re.compile(r"\b(no|nope|don'?t|do not|never ?mind|wait|stop|keep it|hold on|not yet)\b", re.I)
PROOF_RE = re.compile(r"photo|picture|pic\b|screenshot|video|footage|camera|cctv|ring\b|doorbell|claim|police|report|neighbou?r|concierge|building|mail ?room|carrier|case (number|no|#)|reference|ref\b|statement from|witness", re.I)


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

    POLICY_REASON_RE = re.compile(r"limit|exceed|cap\b|\$?75|over|old|30 days|age|amount", re.I)
    MUST_ESCALATE_RE = re.compile(r"fraud|unauthori|stol|legal|lawyer|sue|clos|frozen|human|specialist|manager|complain|dispute|transfer|lock", re.I)

    def _wrongful_policy_escalation(self, args):
        """Code guardrail: the model sometimes escalates refunds the policy engine says are allowed
        (exactly $75.00, day 29). Block only amount/age-based escalations of eligible transactions."""
        if not self.guardrail or not self.session.get("verified") or self.session.get("fraud_claim"):
            return None
        summary = str(args.get("summary", ""))
        if self.MUST_ESCALATE_RE.search(summary) or not self.POLICY_REASON_RE.search(summary):
            return None
        for tid in {normalize_txn_id(m) for m in re.findall(r"(?i)\btxn[\s_-]*\d{4,6}\b", summary)}:
            t = self.store.transactions.get(tid)
            if not t or t["customer_id"] != self.session["customer_id"]:
                continue
            left = round(t["amount"] - sum(r["amount"] for r in self.store.refunds.values() if r["txn_id"] == tid), 2)
            if left > 0 and refund_allowed(self.store, self.session, tid, left)[0]:
                return tid
        return None

    _GENERIC = set("""i im i'm me my mine we our you your u it its this that these those a an the and or but so to of on for in at by
        with from is was were be been am are do did does can could would will should please pls plz just now asap
        want wanted need needs like get give send make issue process refund refunds refunded refunding money back
        charge charges charged charging transaction transactions txn payment purchase order hi hello hey thanks thank
        ok okay yes yeah sure email card last digits ending ends ending four 4 is help also too again another one""".split())

    def _reason_given(self, txn_id):
        """Has the customer said anything beyond 'refund <id>' + credentials? (merchant names don't count)"""
        t = self.store.transactions.get(txn_id) or {}
        merchant = set(re.findall(r"[a-z+']+", str(t.get("merchant", "")).lower()))
        for m in self.messages:
            if m.get("role") != "user":
                continue
            txt = re.sub(r"\S+@\S+|\btxn[\s_-]*\d+|\$?\d+(\.\d+)?", " ", str(m.get("content", "")).lower())
            words = [w.strip("'") for w in re.findall(r"[a-z']+", txt)]
            if [w for w in words if len(w) > 1 and w not in self._GENERIC and w not in merchant]:
                return True
        return False

    def _reason_gate(self, txn_id, args):
        """Resolution-first (code): if the customer hasn't said what went wrong, ask once before refunding.
        Not obstructive: the second attempt in a later turn goes through even without a reason."""
        if self._reason_given(txn_id) or str(args.get("reason", "")).strip().lower() in ("customer declined to say",):
            return None
        asked = self.session.setdefault("reason_asked", {})
        if txn_id in asked and asked[txn_id] < self.session.get("turn", 0):
            return None
        asked.setdefault(txn_id, self.session.get("turn", 0))
        return {"ok": False, "reason": "ask_reason_first",
                "instruction": "Ask the customer briefly what went wrong with this charge (so you can fix it if possible). Don't refund in this reply."}

    def _touch(self, txn_id):
        if txn_id:
            tt = self.session.setdefault("turn_txns", {})
            tt[txn_id] = self.session.get("turn", 0)

    def _user_msgs_after(self, turn):
        """User messages whose turn number is > turn (turn = 1-based count of user messages)."""
        out, n = [], 0
        for m in self.messages:
            if m.get("role") == "user":
                n += 1
                if n > turn:
                    out.append(str(m.get("content", "")))
        return out

    def _delivery_gate(self, txn_id):
        """Orders (code): check_delivery_status first; no refund in transit; delivered needs a proof description."""
        t = self.store.transactions.get(txn_id) or {}
        if t.get("kind") != "order":
            return None
        chk = self.session.get("delivery_checked", {}).get(txn_id)
        if not chk:
            return {"ok": False, "reason": "check_delivery_status_first",
                    "instruction": "Call check_delivery_status for this order first, then follow its next_step."}
        when, status = chk
        if status == "in_transit":
            return {"ok": False, "reason": "order_in_transit_no_refund",
                    "instruction": "The order is still on its way. Explain and offer to wait; if they insist, escalate_to_human."}
        if status == "delivered":
            if not any(PROOF_RE.search(u) for u in self._user_msgs_after(when)):
                return {"ok": False, "reason": "need_proof_of_non_delivery",
                        "instruction": "Carrier shows delivered. Ask the customer to describe proof it didn't arrive (carrier claim, photo, police/neighbour report). If they can't, escalate_to_human. Don't refund yet."}
        return None

    def _cancellation_gate(self, txn_id, amount):
        """Refund = cancellation (code): the customer must be told the consequence in an earlier turn and say yes."""
        t = self.store.transactions.get(txn_id) or {}
        turn = self.session.get("turn", 0)
        notice = self.session.setdefault("cancel_notice", {})
        last_user = next((str(m.get("content", "")) for m in reversed(self.messages) if m.get("role") == "user"), "")
        if txn_id in notice and notice[txn_id] < turn:
            if AFFIRM_RE.search(last_user) and not NEGATE_RE.search(last_user):
                return None
            return {"ok": False, "reason": "awaiting_cancellation_confirmation",
                    "instruction": "The customer hasn't clearly confirmed. Restate that refunding cancels it and ask for a clear yes. Don't refund."}
        notice.setdefault(txn_id, turn)
        kind = t.get("kind")
        effect = ("cancel your " + t.get("merchant", "") + " subscription, so you'll lose access" if kind == "subscription"
                  else "cancel the " + t.get("merchant", "") + " order, so it won't be delivered if it hasn't arrived" if kind == "order"
                  else "cancel this " + t.get("merchant", "") + " purchase")
        return {"ok": False, "reason": "confirm_cancellation_first",
                "tell_customer": f"Refunding ${amount:.2f} will {effect}. Do you want me to go ahead?",
                "instruction": "Tell the customer exactly this consequence and ask them to confirm. Refund only after they say yes in their next message."}

    def _resolution_gate(self, txn_id):
        """Resolution-first (code): for charges with a known non-refund fix (descriptor, auth hold,
        subscription, duplicate-looking pending), the fix must be offered in an earlier turn first."""
        t = self.store.transactions.get(txn_id) or {}
        if not t.get("resolution"):
            return None
        shown_turn = self.session.get("resolution_shown", {}).get(txn_id)
        if shown_turn is not None and shown_turn < self.session.get("turn", 0):
            return None
        self.session.setdefault("resolution_shown", {}).setdefault(txn_id, self.session.get("turn", 0))
        return {"ok": False, "reason": "resolution_first",
                "resolution": t["resolution"],
                "instruction": "Explain this to the customer and ask if it solves their issue. Refund only if they still want it in their next message."}

    def _session_note(self) -> str:
        """Authoritative session facts from code, refreshed every model call (models forget across turns)."""
        s = self.session
        if s.get("verification_locked"):
            v = "LOCKED after 3 failed verification attempts. Do not verify or share anything; an escalation exists."
        elif s.get("verified"):
            v = f"VERIFIED as customer {s['customer_id']}. Do NOT ask for email/last 4 again; act on their requests."
        else:
            v = f"NOT verified ({s.get('failed_verifications', 0)} failed attempts)."
        refunds = ", ".join(f"{r['txn_id']} ${r['amount']}" for r in self.store.refunds.values()) or "none"
        return (f"\n\nSESSION STATE (from the system, authoritative): customer {v} Refunds issued this chat: {refunds}."
                " If the customer named a transaction ID earlier in the chat, use it without asking again.")

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
        """Reliability wrapper: a bad tool call becomes an error result the model can recover from,
        never an exception that kills the customer's turn."""
        if not isinstance(args, dict) or "_malformed_arguments" in args:
            res = {"error": "malformed_arguments: send valid JSON arguments"}
            self.store.calls.append((name, args if isinstance(args, dict) else {}, res))
            return res
        try:
            return self._run_tool_inner(name, args)
        except Exception as e:  # noqa: BLE001
            res = {"error": f"tool_failed: {type(e).__name__}"}
            self.store.calls.append((name, args, res))
            return res

    def _run_tool_inner(self, name, args):
        # SECURITY: After 3 failed verification attempts, lock verification and force escalation
        if name == "verify_customer":
            if self.session["verification_locked"]:
                res = {"verified": False, "error": "verification_locked"}
            elif self.session.get("verified"):
                cid = check_verification(self.store, args.get("email"), args.get("last4"))
                res = ({"verified": True, "customer_id": cid} if cid == self.session["customer_id"]
                       else {"verified": False, "error": "already_verified_as_another_customer_restart_chat"})
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(args.get("email") or "").strip()) or not re.search(r"\d", str(args.get("last4") or "")):
                # Missing/incomplete credentials are not a failed attempt (don't burn the 3-strike budget)
                res = {"verified": False, "error": "missing_credentials_ask_for_email_and_card_last4"}
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
        elif name == "check_delivery_status":
            if not self.session.get("verified"):
                res = {"error": "verify_customer_first"}
            else:
                tid = normalize_txn_id(args.get("txn_id", "")) if args.get("txn_id") else ""
                res = TOOLS[name](self.store, customer_id=self.session["customer_id"], txn_id=tid, order_id=str(args.get("order_id") or ""))
                if "status" in res:
                    self.session.setdefault("delivery_checked", {})[res["txn_id"]] = [self.session.get("turn", 0), res["status"]]
                    t = self.store.transactions[res["txn_id"]]
                    left = round(t["amount"] - sum(r["amount"] for r in self.store.refunds.values() if r["txn_id"] == res["txn_id"]), 2)
                    ok, why = refund_allowed(self.store, self.session, res["txn_id"], max(left, 0.01))
                    res["order_charge"] = {"merchant": t["merchant"], "amount": t["amount"], "date": t["date"],
                                           "refundable_remaining": max(left, 0), "policy_allows_refund": ok and not self.session.get("fraud_claim"), "policy_reason": why}
                    self._touch(res["txn_id"])
                    res["next_step"] = {
                        "delivered": "Carrier shows it delivered. Ask the customer for proof it didn't arrive (carrier claim, photo, police/neighbour report, describe it). Once they describe proof and policy_allows_refund is true, do NOT escalate: tell them refunding cancels the order, get a yes, then issue_refund the full refundable_remaining. Only if they have no proof: escalate_to_human.",
                        "in_transit": "Still on its way. Explain and offer to wait. No refund while in transit.",
                        "not_shipped": "Not shipped yet. Offer to wait, or cancel the order + refund if the customer prefers (tell them refunding cancels the order and get a yes first).",
                        "lost": "Carrier lost it. Offer a refund of refundable_remaining (tell them refunding cancels the order and get a yes first). Use the exact amount from order_charge.",
                    }.get(res["status"], "")
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
            # Normalize transaction ID: "Amazon txn 58306" / "txn58306" -> "TXN-58306"
            args = {**args, "txn_id": normalize_txn_id(args.get("txn_id", ""))}
            # SECURITY: always scope lookups to the verified customer
            args = {**args, "customer_id": self.session["customer_id"]}
            try:
                res = TOOLS[name](self.store, **args)
            except TypeError as e:
                res = {"error": f"bad_arguments: {e}"}
            if "amount" in res and self.guardrail:
                # Code-computed eligibility so the model doesn't do policy arithmetic itself
                t = self.store.transactions[args["txn_id"]]
                left = round(t["amount"] - sum(r["amount"] for r in self.store.refunds.values() if r["txn_id"] == args["txn_id"]), 2)
                ok, why = refund_allowed(self.store, self.session, args["txn_id"], max(left, 0.01))
                if self.session.get("fraud_claim"): ok, why = False, "fraud_claim_escalate"
                res["refund_check"] = {"eligible_for_full_refund": ok, "reason": why, "refundable_remaining": max(left, 0)}
                if t.get("kind") == "subscription":
                    mx, info = subscription_max_refund(t)
                    mx = max(0, round(mx - (t["amount"] - left), 2))
                    ok2, why2 = refund_allowed(self.store, self.session, args["txn_id"], max(mx, 0.01))
                    res["refund_check"] = {"eligible_for_full_refund": False if info["days_used"] else ok,
                                           "max_refund_now": mx, "proration": info,
                                           "eligible_for_max_refund_now": ok2 and not self.session.get("fraud_claim"), "reason": why2}
            self._touch(args["txn_id"])
            if "resolution" in res:
                shown = self.session.setdefault("resolution_shown", {})
                shown.setdefault(args["txn_id"], self.session.get("turn", 0))
                res["resolution_first"] = ("Explain this to the customer and ask whether it solves their issue. "
                                           "Do NOT refund in this reply; refund only if they still want it afterwards and policy allows.")
        elif name == "issue_refund" and self.guardrail:
            # SECURITY: Refuse refunds if verification is locked
            if self.session.get("verification_locked"):
                res = {"ok": False, "reason": "blocked_by_policy:verification_locked"}
            elif self.session.get("fraud_claim"):
                res = {"ok": False, "reason": "blocked_by_policy:fraud_claim_escalate"}
            else:
                args = {**args, "txn_id": normalize_txn_id(args.get("txn_id", ""))}
                try: float(args.get("amount", 0))
                except (TypeError, ValueError): args = {**args, "amount": 0}
                ok, reason = refund_allowed(self.store, self.session, args.get("txn_id"), float(args.get("amount", 0)))
                tid = args.get("txn_id")
                self._touch(tid)
                gate = (self._resolution_gate(tid) or self._reason_gate(tid, args)
                        or self._delivery_gate(tid) or self._cancellation_gate(tid, float(args.get("amount", 0))))
                if ok and gate:
                    res = gate
                else:
                    res = TOOLS[name](self.store, **args) if ok else {"ok": False, "reason": f"blocked_by_policy:{reason}"}
        elif name == "escalate_to_human" and self._wrongful_policy_escalation(args):
            res = {"ok": False, "error": "not_escalated: " + self._wrongful_policy_escalation(args) +
                   " is within policy (refund_check eligible: amount <= $75 and under 30 days). Issue the refund with issue_refund instead."}
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
        self.session["turn"] = self.session.get("turn", 0) + 1
        import time as _t
        turn_deadline = _t.monotonic() + TURN_BUDGET_S
        for _ in range(MAX_STEPS):
            if _t.monotonic() > turn_deadline:
                text = "Sorry, that took longer than expected on my side. Could you send your last message again?"
                self.messages.append({"role": "assistant", "content": text})
                return text
            out = self.provider.complete(self.system + self._session_note(), self.messages, TOOL_SPECS + [VERIFY_SPEC])
            calls = out.get("tool_calls") or []
            self.messages.append({"role": "assistant", "content": out.get("text"), "tool_calls": calls} if calls
                                 else {"role": "assistant", "content": out.get("text") or ""})
            if not calls:
                text = sanitize_reply(out.get("text") or "")
                self.messages[-1]["content"] = text
                if re.search(r"cancel", text, re.I) and re.search(r"\?", text):
                    turn = self.session.get("turn", 0)
                    low = text.lower()
                    for tid, tn in self.session.get("turn_txns", {}).items():
                        t = self.store.transactions.get(tid) or {}
                        amt = float(t.get("amount", 0) or 0)
                        mentioned = (tid.lower() in low or (t.get("merchant") and t["merchant"].lower() in low)
                                     or f"${amt:.2f}" in text or f"${amt:g}" in text)
                        if tn == turn or (tn >= turn - 2 and mentioned):
                            self.session.setdefault("cancel_notice", {}).setdefault(tid, turn)
                return text
            # interim text that rides along with tool calls ("I'll process that now") is dropped: the final reply speaks
            self.messages[-1]["content"] = None
            for c in calls:
                res = self._run_tool(c["name"], c["arguments"])
                self.messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": json.dumps(res)})
        return "Sorry, I'm having trouble with that request. Could you rephrase it, or tell me the transaction ID you need help with?"
