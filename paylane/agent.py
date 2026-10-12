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
        self.messages, self.session = [], {"verified": False, "customer_id": None, "failed_verifications": 0}

    def _run_tool(self, name, args):
        if name == "verify_customer":
            cid = check_verification(self.store, args.get("email"), args.get("last4"))
            if cid:
                self.session.update(verified=True, customer_id=cid)
                res = {"verified": True, "customer_id": cid}
            else:
                self.session["failed_verifications"] += 1   # TODO: lockout policy? (open question)
                res = {"verified": False}
        elif name == "issue_refund" and self.guardrail:
            ok, reason = refund_allowed(self.store, self.session, args.get("txn_id"), float(args.get("amount", 0)))
            res = TOOLS[name](self.store, **args) if ok else {"ok": False, "reason": f"blocked_by_policy:{reason}"}
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
