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


def test_verification_lockout_after_3_failures():
    """SECURITY: After 3 failed verification attempts, lock verification and refuse refunds."""
    # Rogue LLM tries 3 wrong card endings, then tries to bypass by calling get_customer
    script = [
        tc(1, "verify_customer", email="aisha@example.com", last4="9999"),  # Wrong, attempt 1
        tc(2, "verify_customer", email="aisha@example.com", last4="8888"),  # Wrong, attempt 2
        tc(3, "verify_customer", email="aisha@example.com", last4="7777"),  # Wrong, attempt 3 - triggers lock
        tc(4, "get_customer", email="aisha@example.com"),  # Try to learn card_last4
        tc(5, "verify_customer", email="aisha@example.com", last4="4242"),  # Try with real last4
        tc(6, "issue_refund", txn_id="T100", amount=42.5),  # Try to refund
        say("Done!")
    ]
    a = Agent(ScriptedProvider(script))
    a.send("Hi, refund T100")
    
    # Check that verification is locked after 3 attempts
    assert a.session["verification_locked"]
    assert a.session["failed_verifications"] == 3
    
    # Check that the 4th verify_customer call failed with locked error
    verify_calls = [c for c in a.store.calls if c[0] == "verify_customer"]
    assert len(verify_calls) == 4
    assert verify_calls[3][2].get("error") == "verification_locked"
    
    # Check that refund was blocked
    refund_calls = [c for c in a.store.calls if c[0] == "issue_refund"]
    assert len(refund_calls) == 1
    assert not refund_calls[0][2].get("ok")
    assert "verification_locked" in refund_calls[0][2].get("reason", "")


def test_get_customer_no_leak_before_verification():
    """SECURITY: get_customer must not return card_last4 before verification."""
    script = [
        tc(1, "get_customer", email="aisha@example.com"),  # Try to learn card_last4
        tc(2, "verify_customer", email="aisha@example.com", last4="4242"),  # Use leaked last4
        tc(3, "issue_refund", txn_id="T100", amount=42.5),
        say("Refunded!")
    ]
    a = Agent(ScriptedProvider(script))
    a.send("Hi")
    
    # Check that get_customer call before verification didn't leak card_last4
    get_customer_calls = [c for c in a.store.calls if c[0] == "get_customer"]
    assert len(get_customer_calls) == 1
    result = get_customer_calls[0][2]
    assert "card_last4" not in result or result.get("card_last4") is None
    assert result == {"error": "verify_customer_first"}  # reveal nothing pre-verification


def test_transaction_id_normalization():
    r"""SECURITY FIX: get_transaction should extract T\d+ from inputs like 'Amazon T105'."""
    script = [
        tc(1, "verify_customer", email="aisha@example.com", last4="4242"),
        tc(2, "get_transaction", customer_id="C001", txn_id="Amazon T105"),  # Model may include merchant name
        tc(3, "issue_refund", txn_id="T105", amount=15),
        say("Done!")
    ]
    a = Agent(ScriptedProvider(script))
    a.send("Refund my Amazon charge")
    
    # Check that get_transaction normalized the ID
    get_txn_calls = [c for c in a.store.calls if c[0] == "get_transaction"]
    assert len(get_txn_calls) == 1
    # The call should have succeeded (not error)
    assert "error" not in get_txn_calls[0][2]
    assert get_txn_calls[0][2].get("amount") == 15.0  # T105 is $15
