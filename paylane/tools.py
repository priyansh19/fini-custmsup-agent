"""The 4 mock tools from the brief (JSON in, JSON out) + provider-agnostic schemas.

Note: the brief's issue_refund(txn_id, amount) has NO policy logic -- like a real
payments API it just executes. Policy enforcement lives in policy.py (guardrail)
and in the prompt. Decide how much belongs where.
"""
from itertools import count
from .data import Store

_ids = count(1)  # legacy; ids now derive from store contents (stateless-safe)


def _new_id(prefix, existing):
    """Unique per conversation even when state is rebuilt on a fresh serverless
    instance (a process-global counter restarted at 1 and overwrote earlier refunds)."""
    n = len(existing) + 1
    while f"{prefix}{n:04d}" in existing:
        n += 1
    return f"{prefix}{n:04d}"


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
    out = {k: t[k] for k in ("amount", "date", "merchant", "status")}
    # Resolution context (statement descriptor, holds, subscriptions, linked txns) so the
    # agent can solve the issue in chat before reaching for a refund.
    out.update({k: t[k] for k in ("descriptor", "recurring", "kind", "related_txn", "resolution",
                                  "billing_period_days", "period_start", "order_id") if k in t})
    if t.get("kind") == "subscription":
        out["refund_effect"] = "Refunding this charge CANCELS the subscription; the customer loses access."
    elif t.get("kind") == "order":
        out["refund_effect"] = "Refunding this charge CANCELS the order (it won't be delivered if not delivered yet). Call check_delivery_status first."
    else:
        out["refund_effect"] = "Refunding this charge cancels the purchase."
    return out


def check_delivery_status(store: Store, customer_id: str, txn_id: str = "", order_id: str = "") -> dict:
    """Our addition (5th tool, at Priyansh's request): mock carrier lookup for an order."""
    rec = None
    if order_id:
        rec = store.deliveries.get(str(order_id).strip().upper())
    if rec is None and txn_id:
        rec = next((d for d in store.deliveries.values() if d["txn_id"] == txn_id), None)
    if rec is None:
        return {"error": "no_delivery_record"}
    t = store.transactions.get(rec["txn_id"]) or {}
    if t.get("customer_id") != customer_id:
        return {"error": "no_delivery_record"}
    oid = next(k for k, v in store.deliveries.items() if v is rec)
    return {"order_id": oid, "txn_id": rec["txn_id"], **{k: v for k, v in rec.items() if k != "txn_id"}}


def issue_refund(store: Store, txn_id: str, amount: float, reason: str = "") -> dict:
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
    
    rid = _new_id("R", store.refunds)
    store.refunds[rid] = {"txn_id": txn_id, "amount": amount, "date": str(t["date"]), "reason": (reason or "")[:200]}
    
    # Mark as refunded only if fully refunded
    if already_refunded + amount >= t["amount"]:
        t["status"] = "refunded"
    
    return {"ok": True, "refund_id": rid}


def escalate_to_human(store: Store, customer_id: str, summary: str) -> dict:
    tid = _new_id("TK", store.tickets)
    store.tickets[tid] = {"customer_id": customer_id, "summary": summary}
    return {"ticket_id": tid}


TOOLS = {f.__name__: f for f in (get_customer, get_transaction, issue_refund, escalate_to_human, check_delivery_status)}

# JSON-schema tool specs (OpenAI "function" / Anthropic "input_schema" compatible)
TOOL_SPECS = [
    {"name": "check_delivery_status", "description": "Our addition: carrier status for an order (by txn_id or order_id). Call it FIRST whenever a customer says an order didn't arrive. Returns status delivered|in_transit|lost|not_shipped, carrier, tracking, delivered_at, proof.",
     "parameters": {"type": "object", "properties": {"txn_id": {"type": "string"}, "order_id": {"type": "string"}}}},
    {"name": "get_customer", "description": "Look up a customer by email. Returns card_last4 for verification; never reveal it.",
     "parameters": {"type": "object", "properties": {"email": {"type": "string"}}, "required": ["email"]}},
    {"name": "get_transaction", "description": "Fetch one transaction for a customer. May include descriptor, recurring, kind (e.g. authorization_hold), related_txn and a resolution note: use these to solve the customer's issue before considering a refund.",
     "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "txn_id": {"type": "string"}},
                    "required": ["customer_id", "txn_id"]}},
    {"name": "issue_refund", "description": "Refund a transaction. Only when policy allows AND the customer's issue can't be solved otherwise (or they still want a refund after you offered the fix).",
     "parameters": {"type": "object", "properties": {"txn_id": {"type": "string"}, "amount": {"type": "number"},
                                                    "reason": {"type": "string", "description": "Customer's reason for the refund, in a few words."}},
                    "required": ["txn_id", "amount"]}},
    {"name": "escalate_to_human", "description": "Hand off to a human agent with a short summary.",
     "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "summary": {"type": "string"}},
                    "required": ["customer_id", "summary"]}},
]
