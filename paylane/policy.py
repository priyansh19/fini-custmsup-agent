"""Deterministic policy guardrail. Called before issue_refund executes, so a
misbehaving LLM still cannot refund against policy. Final policy decisions
documented in README with rationale."""
from datetime import date, timedelta
from .data import Store, TODAY

# POLICY CONSTANTS
AUTO_LIMIT = 75.00                  # Hard cap: transaction amount must be ≤ $75 (inclusive)
MAX_AGE_DAYS = 30                   # Age < 30 days (day 30 excluded) from transaction date
MAX_FAILED_VERIFICATIONS = 3        # Lock out after 3 failed attempts
CUMULATIVE_REFUND_CAP = 75.00       # Max agent-issued refunds per customer per rolling 30 days
CUMULATIVE_REFUND_WINDOW_DAYS = 30  # Rolling window for cumulative cap


def subscription_max_refund(t: dict, today: date = None) -> tuple[float, dict]:
    """Proration (code): cancel on the day of the charge (day 0) = full refund; afterwards
    refund only the unused days: amount * (period - days_used) / period, rounded to cents."""
    from decimal import Decimal, ROUND_HALF_UP
    today = today or TODAY
    period = int(t.get("billing_period_days") or 30)
    used = max(0, (today - date.fromisoformat(t.get("period_start") or t["date"])).days)
    if used == 0:
        return round(t["amount"], 2), {"days_used": 0, "period_days": period, "rule": "same_day_full_refund"}
    unused = max(0, period - used)
    amt = float((Decimal(str(t["amount"])) * unused / period).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return amt, {"days_used": used, "period_days": period, "unused_days": unused, "rule": "prorated_unused_days"}


def refund_allowed(store: Store, session: dict, txn_id: str, amount: float) -> tuple[bool, str]:
    """Check if a refund can be auto-approved. Returns (allowed, reason)."""
    
    # 1. Verification required
    if not session.get("verified"):
        return False, "customer_not_verified"
    
    customer_id = session.get("customer_id")
    
    # 2. Transaction existence and ownership
    t = store.transactions.get(txn_id)
    if not t or t["customer_id"] != customer_id:
        return False, "not_customers_transaction"
    
    # 3. Customer must have active status (not frozen)
    customer = store.customers.get(customer_id)
    if customer and customer.get("status") == "frozen":
        return False, "frozen_card_escalate"
    
    # 4. Check if already fully refunded
    already_refunded = sum(r["amount"] for r in store.refunds.values() if r["txn_id"] == txn_id)
    remaining = t["amount"] - already_refunded
    
    if remaining <= 0:
        return False, "already_refunded"
    
    # 5. Amount validation
    if amount <= 0:
        return False, "invalid_amount"
    if amount > remaining:
        return False, "amount_exceeds_remaining"
    if amount > t["amount"]:
        return False, "amount_exceeds_transaction"
    
    # 5b. Subscriptions: refund = cancellation; after day 0 only the prorated unused part
    if t.get("kind") == "subscription":
        max_amt, _ = subscription_max_refund(t)
        if amount > round(max_amt - already_refunded, 2) + 1e-9:
            return False, f"exceeds_prorated_max:{max(0, round(max_amt - already_refunded, 2))}"

    # 6. Transaction amount hard cap (POLICY: no refunds on txns > $75, not even partial)
    if t["amount"] > AUTO_LIMIT:
        return False, "over_auto_limit_escalate"
    
    # 7. Pending transactions CAN be refunded (POLICY DECISION)
    # (removed pending check per new policy)
    
    # 8. Age check: must be < 30 days from transaction date (day 30 excluded)
    age = (TODAY - date.fromisoformat(t["date"])).days
    if age >= MAX_AGE_DAYS:
        return False, "too_old_escalate"
    
    # 9. Cumulative refund cap (anti-abuse: max $75 total per customer per rolling 30 days)
    cumulative = get_cumulative_refunds_rolling(store, customer_id, CUMULATIVE_REFUND_WINDOW_DAYS)
    if cumulative + amount > CUMULATIVE_REFUND_CAP:
        return False, "cumulative_limit_escalate"
    
    return True, "ok"


def check_verification(store: Store, email: str, last4: str) -> str | None:
    """Return customer_id if email + last4 match, else None.
    
    POLICY: Verification is strict. No switching identity mid-chat without restarting.
    """
    for c in store.customers.values():
        if c["email"].lower() == (email or "").strip().lower() and c["card_last4"] == str(last4).strip():
            return c["id"]
    return None


def get_cumulative_refunds_rolling(store: Store, customer_id: str, days: int) -> float:
    """Return total amount refunded for a customer in the last N days.
    
    POLICY: Anti-abuse measure. Max $75 total in agent-issued refunds per rolling 30 days.
    Beyond that, escalate to human review.
    
    Note: Uses the transaction date (when the original charge occurred) to determine
    if the refund is within the rolling window.
    """
    cutoff = TODAY - timedelta(days=days)
    total = 0.0
    for refund in store.refunds.values():
        txn = store.transactions.get(refund["txn_id"])
        if txn and txn["customer_id"] == customer_id:
            # Use the transaction date from the refund record (set when refund issued)
            refund_txn_date = date.fromisoformat(refund.get("date", txn["date"]))
            if refund_txn_date >= cutoff:
                total += refund["amount"]
    return total


def verification_locked_out(session: dict) -> bool:
    """Check if customer has exceeded max failed verification attempts.
    
    POLICY: After 3 failed attempts, escalate and stop sharing any information.
    """
    return session.get("failed_verifications", 0) >= MAX_FAILED_VERIFICATIONS


def should_reveal_account_info(session: dict) -> bool:
    """Check if agent can reveal ANY account information.
    
    POLICY: Before verification, reveal nothing — not even account existence or frozen status.
    """
    return session.get("verified", False)
