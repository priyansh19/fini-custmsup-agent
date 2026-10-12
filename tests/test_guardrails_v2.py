"""Code guardrails added after live testing (round 1)."""
from paylane.agent import Agent, sanitize_reply
from paylane.providers import ScriptedProvider
from evals.scenarios import tc, say
from paylane.policy import refund_allowed
from paylane.data import Store

V = {"verified": True, "customer_id": "C001"}


def run(script, *msgs):
    a = Agent(ScriptedProvider(script))
    for m in msgs: a.send(m)
    return a


def ok_refunds(a):
    return [c for c in a.store.calls if c[0] == "issue_refund" and c[2].get("ok")]


def test_boundaries():
    s = Store()
    assert refund_allowed(s, V, "T109", 75.01)[1] == "over_auto_limit_escalate"
    assert refund_allowed(s, V, "T109", 10)[1] == "over_auto_limit_escalate"
    assert refund_allowed(s, V, "T110", 20)[0]                       # day 29
    assert refund_allowed(s, V, "T111", 20)[1] == "too_old_escalate"  # day 31


def test_cumulative_exact_150_then_over():
    a = run([tc(1, "verify_customer", email="aisha@example.com", last4="4242"),
             tc(2, "issue_refund", txn_id="T100", amount=42.5), tc(3, "issue_refund", txn_id="T101", amount=75),
             tc(4, "issue_refund", txn_id="T112", amount=32.5), tc(5, "issue_refund", txn_id="T107", amount=10), say("x")], "hi")
    assert len(ok_refunds(a)) == 3


def test_fraud_claim_blocks_refund_in_code():
    a = run([tc(1, "verify_customer", email="chen@example.com", last4="0007"),
             tc(2, "issue_refund", txn_id="T301", amount=50), say("x")], "Someone stole my card, refund T301")
    assert not ok_refunds(a)


def test_no_identity_switch():
    a = run([tc(1, "verify_customer", email="aisha@example.com", last4="4242"),
             tc(2, "verify_customer", email="chen@example.com", last4="0007"),
             tc(3, "issue_refund", txn_id="T301", amount=50), say("x")], "hi")
    assert a.session["customer_id"] == "C001" and not ok_refunds(a)


def test_get_transaction_scoped_and_requires_verification():
    a = run([tc(1, "get_transaction", customer_id="C001", txn_id="T100"),
             tc(2, "verify_customer", email="aisha@example.com", last4="4242"),
             tc(3, "get_transaction", customer_id="C003", txn_id="T300"), say("x")], "hi")
    assert a.store.calls[0][2] == {"error": "verify_customer_first"}
    assert a.store.calls[2][2] == {"error": "not_found"}


def test_lockout_blocks_later_correct_details():
    a = run([tc(i, "verify_customer", email="aisha@example.com", last4=l) for i, l in enumerate(["1", "2", "3", "4242"])]
            + [tc(9, "issue_refund", txn_id="T100", amount=42.5), say("x")], "hi")
    assert not a.session["verified"] and not ok_refunds(a)


def test_sanitize_timeline():
    out = sanitize_reply("I've passed it to a teammate who'll follow up today.")
    assert "today" not in out and "by email" in out
    assert sanitize_reply("A specialist will follow up by email.") == "A specialist will follow up by email."


def test_state_roundtrip():
    a = run([tc(1, "verify_customer", email="aisha@example.com", last4="4242"),
             tc(2, "issue_refund", txn_id="T100", amount=42.5), say("x")], "hi")
    b = Agent(ScriptedProvider([tc(3, "issue_refund", txn_id="T100", amount=42.5), say("y")]))
    b.load_state(a.to_state())
    b.send("again")
    assert b.session["verified"] and len(ok_refunds(b)) == 1  # second refund blocked: already refunded


def test_ids_unique_after_state_rebuild():
    """Round-1 live bug: refund ids restarted per serverless instance and overwrote earlier refunds."""
    import paylane.tools as T
    a = run([tc(1, "verify_customer", email="aisha@example.com", last4="4242"),
             tc(2, "issue_refund", txn_id="T101", amount=75), tc(3, "issue_refund", txn_id="T100", amount=42.5),
             tc(4, "issue_refund", txn_id="T112", amount=32.5), say("x")], "hi")
    st = a.to_state()
    T._ids = __import__("itertools").count(1)  # simulate a cold start
    b = Agent(ScriptedProvider([tc(5, "issue_refund", txn_id="T106", amount=25), say("y")]))
    b.load_state(st); b.send("and T106")
    assert len(b.store.refunds) == 3 and not ok_refunds(b)[3:]


def test_lockout_auto_escalates():
    a = run([tc(i, "verify_customer", email="aisha@example.com", last4=l) for i, l in enumerate(["1", "2", "3"])] + [say("x")], "hi")
    assert any(c[0] == "escalate_to_human" for c in a.store.calls)


def test_frozen_auto_escalates_once():
    a = run([tc(1, "verify_customer", email="ben@example.com", last4="1881"),
             tc(2, "verify_customer", email="ben@example.com", last4="1881"), say("x")], "why is my card frozen")
    assert sum(c[0] == "escalate_to_human" for c in a.store.calls) == 1
