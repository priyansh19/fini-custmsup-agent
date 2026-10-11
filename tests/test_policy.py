"""Guardrail must block bad refunds even if the LLM tries them."""
from paylane.agent import Agent
from paylane.providers import ScriptedProvider
from evals.scenarios import tc, say
from paylane.data import Store
from paylane.policy import refund_allowed

V = {"verified": True, "customer_id": "C001"}


def test_rules():
    s = Store()
    # Basic refund allowed
    assert refund_allowed(s, V, "T100", 42.5)[0]
    # $75 inclusive boundary
    assert refund_allowed(s, V, "T101", 75)[0]
    # Transaction over $75: hard cap, no partial refunds
    assert refund_allowed(s, V, "T102", 75)[1] == "over_auto_limit_escalate"
    assert refund_allowed(s, V, "T102", 120)[1] == "over_auto_limit_escalate"
    # Age checks: >= 30 days excluded
    assert refund_allowed(s, V, "T103", 30)[1] == "too_old_escalate"  # 52 days
    assert refund_allowed(s, V, "T104", 20)[1] == "too_old_escalate"  # exactly 30 days
    # Pending now allowed
    assert refund_allowed(s, V, "T105", 15)[0]
    # Partial refund allowed
    assert refund_allowed(s, V, "T106", 15)[0]
    # Wrong customer
    assert refund_allowed(s, V, "T200", 60)[1] == "not_customers_transaction"
    # Not verified
    assert refund_allowed(s, {"verified": False}, "T100", 42.5)[1] == "customer_not_verified"
    # Frozen card
    assert refund_allowed(s, {"verified": True, "customer_id": "C002"}, "T200", 60)[1] == "frozen_card_escalate"


def test_guardrail_blocks_rogue_llm():
    rogue = ScriptedProvider([tc(1, "issue_refund", txn_id="T102", amount=120), say("Refunded!")])
    a = Agent(rogue)
    a.send("refund T102")
    assert not any(c[2].get("ok") for c in a.store.calls if c[0] == "issue_refund")


def test_partial_refund_tracking():
    s = Store()
    from paylane.tools import issue_refund
    # First partial refund
    assert issue_refund(s, "T106", 15)["ok"]
    # Second partial refund (remaining: 25 - 15 = 10)
    assert issue_refund(s, "T106", 10)["ok"]
    # Third attempt exceeds remaining
    result = issue_refund(s, "T106", 5)
    assert not result["ok"]
    # Verify guardrail catches fully refunded
    assert refund_allowed(s, V, "T106", 1)[1] == "already_refunded"


def test_cumulative_limit():
    s = Store()
    from paylane.tools import issue_refund
    # Refund T100 ($42.50) and T101 ($75) = $117.50
    issue_refund(s, "T100", 42.5)
    issue_refund(s, "T101", 75)
    # Add a $40 partial refund on T106 ($25 transaction, so do $20)
    issue_refund(s, "T106", 20)
    # Now $137.50 total. Next $15 would exceed $150 cap
    ok, reason = refund_allowed(s, V, "T105", 15)
    assert not ok
    assert reason == "cumulative_limit_escalate"
    # But $12.50 should be allowed ($137.50 + $12.50 = $150)
    ok, reason = refund_allowed(s, V, "T105", 12.5)
    assert ok
