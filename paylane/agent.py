"""Agent loop: LLM -> tool calls -> guardrail -> tool results -> LLM, until text reply."""
import json
from .data import Store, TODAY
from .tools import TOOLS, TOOL_SPECS
from .policy import refund_allowed, check_verification
from .prompt import SYSTEM_PROMPT

# Extra (non-spec) tool so the model can record verification. Spec has no verify
# endpoint -- TODO(Priyansh): decide whether to keep this or verify in-prompt only.
VERIFY_SPEC = {"name": "verify_customer", "description": "Check the email + card last 4 the customer gave. Required before discussing account details.",
               "parameters": {"type": "object", "properties": {"email": {"type": "string"}, "last4": {"type": "string"}}, "required": ["email", "last4"]}}

MAX_STEPS = 8


class Agent:
    def __init__(self, provider, store: Store | None = None, system_prompt: str = SYSTEM_PROMPT, guardrail: bool = True):
        self.provider, self.store = provider, store or Store()
        # Inject today's date dynamically into the prompt
        self.system = system_prompt.replace("{{TODAY}}", TODAY.strftime("%Y-%m-%d"))
        self.guardrail = guardrail
        self.messages, self.session = [], {"verified": False, "customer_id": None, "failed_verifications": 0, "verification_locked": False}

    def _run_tool(self, name, args):
        # SECURITY: After 3 failed verification attempts, lock verification and force escalation
        if name == "verify_customer":
            if self.session["verification_locked"]:
                res = {"verified": False, "error": "verification_locked"}
            else:
                cid = check_verification(self.store, args.get("email"), args.get("last4"))
                if cid:
                    self.session.update(verified=True, customer_id=cid)
                    res = {"verified": True, "customer_id": cid}
                else:
                    self.session["failed_verifications"] += 1
                    if self.session["failed_verifications"] >= 3:
                        self.session["verification_locked"] = True
                        res = {"verified": False, "error": "verification_locked_after_3_attempts"}
                    else:
                        res = {"verified": False}
        elif name == "get_customer":
            # SECURITY: Don't leak card_last4 before verification
            res = TOOLS[name](self.store, **args)
            if not self.session.get("verified") and "card_last4" in res:
                # Return minimal info only
                res = {"id": res.get("id"), "name": res.get("name"), "verified": False}
        elif name == "get_transaction":
            # Normalize transaction ID: extract T\d+ from inputs like "Amazon T105"
            import re
            txn_id = args.get("txn_id", "")
            match = re.search(r'T\d+', txn_id)
            if match:
                args = {**args, "txn_id": match.group(0)}
            try:
                res = TOOLS[name](self.store, **args)
            except TypeError as e:
                res = {"error": f"bad_arguments: {e}"}
        elif name == "issue_refund" and self.guardrail:
            # SECURITY: Refuse refunds if verification is locked
            if self.session.get("verification_locked"):
                res = {"ok": False, "reason": "blocked_by_policy:verification_locked"}
            else:
                ok, reason = refund_allowed(self.store, self.session, args.get("txn_id"), float(args.get("amount", 0)))
                res = TOOLS[name](self.store, **args) if ok else {"ok": False, "reason": f"blocked_by_policy:{reason}"}
        elif name == "escalate_to_human":
            # SECURITY: Require minimal customer_id even if not verified (for locked sessions)
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
        self.messages.append({"role": "user", "content": user_text})
        for _ in range(MAX_STEPS):
            out = self.provider.complete(self.system, self.messages, TOOL_SPECS + [VERIFY_SPEC])
            calls = out.get("tool_calls") or []
            self.messages.append({"role": "assistant", "content": out.get("text"), "tool_calls": calls} if calls
                                 else {"role": "assistant", "content": out.get("text") or ""})
            if not calls:
                return out.get("text") or ""
            for c in calls:
                res = self._run_tool(c["name"], c["arguments"])
                self.messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": json.dumps(res)})
        return "Sorry, I'm having trouble. Let me get a teammate to help."
