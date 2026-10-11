"""The 4 mock tools from the brief (JSON in, JSON out) + provider-agnostic schemas.

Note: the brief's issue_refund(txn_id, amount) has NO policy logic -- like a real
payments API it just executes. Policy enforcement lives in policy.py (guardrail)
and in the prompt. Decide how much belongs where.
"""
from itertools import count
from .data import Store

_ids = count(1)


def get_customer(store: Store, email: str) -> dict:
    for c in store.customers.values():
        if c["email"].lower() == (email or "").strip().lower():
            # Spec returns verified: false always -- verification is the agent's job.
            return {"id": c["id"], "name": c["name"], "card_last4": c["card_last4"],
                    "status": c["status"], "verified": False,
                    "freeze_reason": c["freeze_reason"]}  # extension: brief says agent may explain freezes
    return {"error": "not_found"}


def get_transaction(store: Store, customer_id: str, txn_id: str) -> dict:
    t = store.transactions.get(txn_id)
    if not t or t["customer_id"] != customer_id:
        return {"error": "not_found"}
    return {k: t[k] for k in ("amount", "date", "merchant", "status")}


def issue_refund(store: Store, txn_id: str, amount: float) -> dict:
    """Issue a full or partial refund. Tracks cumulative refunds per transaction."""
    t = store.transactions.get(txn_id)
    if not t:
        return {"ok": False, "reason": "unknown_transaction"}
    
    # Calculate already refunded amount
    already_refunded = sum(r["amount"] for r in store.refunds.values() if r["txn_id"] == txn_id)
    remaining = t["amount"] - already_refunded
    
    if remaining <= 0:
        return {"ok": False, "reason": "already_refunded"}
    if amount <= 0:
        return {"ok": False, "reason": "invalid_amount"}
    if amount > remaining:
        return {"ok": False, "reason": "exceeds_remaining"}
    if amount > t["amount"]:
        return {"ok": False, "reason": "invalid_amount"}
    
    rid = f"R{next(_ids):04d}"
    store.refunds[rid] = {"txn_id": txn_id, "amount": amount, "date": str(t["date"])}
    
    # Mark as refunded only if fully refunded
    if already_refunded + amount >= t["amount"]:
        t["status"] = "refunded"
    
    return {"ok": True, "refund_id": rid}


def escalate_to_human(store: Store, customer_id: str, summary: str) -> dict:
    tid = f"TK{next(_ids):04d}"
    store.tickets[tid] = {"customer_id": customer_id, "summary": summary}
    return {"ticket_id": tid}


TOOLS = {f.__name__: f for f in (get_customer, get_transaction, issue_refund, escalate_to_human)}

# JSON-schema tool specs (OpenAI "function" / Anthropic "input_schema" compatible)
TOOL_SPECS = [
    {"name": "get_customer", "description": "Look up a customer by email. Returns card_last4 for verification; never reveal it.",
     "parameters": {"type": "object", "properties": {"email": {"type": "string"}}, "required": ["email"]}},
    {"name": "get_transaction", "description": "Fetch one transaction for a customer.",
     "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "txn_id": {"type": "string"}},
                    "required": ["customer_id", "txn_id"]}},
    {"name": "issue_refund", "description": "Refund a transaction. Only when policy allows.",
     "parameters": {"type": "object", "properties": {"txn_id": {"type": "string"}, "amount": {"type": "number"}},
                    "required": ["txn_id", "amount"]}},
    {"name": "escalate_to_human", "description": "Hand off to a human agent with a short summary.",
     "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "summary": {"type": "string"}},
                    "required": ["customer_id", "summary"]}},
]
