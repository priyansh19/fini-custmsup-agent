"""Code guardrails added after live testing (round 1)."""
from paylane.agent import Agent, sanitize_reply
from paylane.providers import ScriptedProvider
from evals.scenarios import tc, say
from paylane.policy import refund_allowed
from paylane.data import Store

V = {"verified": True, "customer_id": "PL-48213"}


def run(script, *msgs):
    a = Agent(ScriptedProvider(script))
    for m in msgs: a.send(m)
    return a


def ok_refunds(a):
    return [c for c in a.store.calls if c[0] == "issue_refund" and c[2].get("ok")]


def test_boundaries():
    s = Store()
    assert refund_allowed(s, V, "TXN-58262", 75.01)[1] == "over_auto_limit_escalate"
    assert refund_allowed(s, V, "TXN-58262", 10)[1] == "over_auto_limit_escalate"
    assert refund_allowed(s, V, "TXN-57560", 20)[0]                       # day 29
    assert refund_allowed(s, V, "TXN-57549", 20)[1] == "too_old_escalate"  # day 31


def test_cumulative_exact_150_then_over():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58214", amount=42.5), tc(3, "issue_refund", txn_id="TXN-58237", amount=75),
             tc(4, "issue_refund", txn_id="TXN-58277", amount=32.5), tc(5, "issue_refund", txn_id="TXN-58209", amount=10), say("x")], "hi")
    assert len(ok_refunds(a)) == 3


def test_fraud_claim_blocks_refund_in_code():
    a = run([tc(1, "verify_customer", email="meilin.tan@maplecrest.test", last4="9126"),
             tc(2, "issue_refund", txn_id="TXN-73325", amount=50), say("x")], "Someone stole my card, refund TXN-73325")
    assert not ok_refunds(a)


def test_no_identity_switch():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "verify_customer", email="meilin.tan@maplecrest.test", last4="9126"),
             tc(3, "issue_refund", txn_id="TXN-73325", amount=50), say("x")], "hi")
    assert a.session["customer_id"] == "PL-48213" and not ok_refunds(a)


def test_get_transaction_scoped_and_requires_verification():
    a = run([tc(1, "get_transaction", customer_id="PL-48213", txn_id="TXN-58214"),
             tc(2, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(3, "get_transaction", customer_id="PL-36642", txn_id="TXN-73318"), say("x")], "hi")
    assert a.store.calls[0][2] == {"error": "verify_customer_first"}
    assert a.store.calls[2][2] == {"error": "not_found"}


def test_lockout_blocks_later_correct_details():
    a = run([tc(i, "verify_customer", email="amara.okafor@maplecrest.test", last4=l) for i, l in enumerate(["1", "2", "3", "6417"])]
            + [tc(9, "issue_refund", txn_id="TXN-58214", amount=42.5), say("x")], "hi")
    assert not a.session["verified"] and not ok_refunds(a)


def test_sanitize_timeline():
    out = sanitize_reply("I've passed it to a teammate who'll follow up today.")
    assert "today" not in out and "by email" in out
    assert sanitize_reply("A specialist will follow up by email.") == "A specialist will follow up by email."


def test_state_roundtrip():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58214", amount=42.5), say("x")], "hi")
    b = Agent(ScriptedProvider([tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5), say("y")]))
    b.load_state(a.to_state())
    b.send("again")
    assert b.session["verified"] and len(ok_refunds(b)) == 1  # second refund blocked: already refunded


def test_ids_unique_after_state_rebuild():
    """Round-1 live bug: refund ids restarted per serverless instance and overwrote earlier refunds."""
    import paylane.tools as T
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58237", amount=75), tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5),
             tc(4, "issue_refund", txn_id="TXN-58277", amount=32.5), say("x")], "hi")
    st = a.to_state()
    T._ids = __import__("itertools").count(1)  # simulate a cold start
    b = Agent(ScriptedProvider([tc(5, "issue_refund", txn_id="TXN-58219", amount=25), say("y")]))
    b.load_state(st); b.send("and TXN-58219")
    assert len(b.store.refunds) == 3 and not ok_refunds(b)[3:]


def test_lockout_auto_escalates():
    a = run([tc(i, "verify_customer", email="amara.okafor@maplecrest.test", last4=l) for i, l in enumerate(["1", "2", "3"])] + [say("x")], "hi")
    assert any(c[0] == "escalate_to_human" for c in a.store.calls)


def test_frozen_auto_escalates_once():
    a = run([tc(1, "verify_customer", email="mateo.alvarez@maplecrest.test", last4="3058"),
             tc(2, "verify_customer", email="mateo.alvarez@maplecrest.test", last4="3058"), say("x")], "why is my card frozen")
    assert sum(c[0] == "escalate_to_human" for c in a.store.calls) == 1


def test_refund_check_in_get_transaction():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "get_transaction", customer_id="PL-48213", txn_id="TXN-58237"),
             tc(3, "get_transaction", customer_id="PL-48213", txn_id="TXN-58262"), say("x")], "hi")
    assert a.store.calls[1][2]["refund_check"]["eligible_for_full_refund"] is True      # exactly $75
    assert a.store.calls[2][2]["refund_check"]["reason"] == "over_auto_limit_escalate"  # $75.01


def test_session_note_reflects_verification():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"), say("x")], "hi")
    assert "VERIFIED as customer PL-48213" in a._session_note()


def test_wrongful_escalation_of_eligible_refund_is_bounced():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "escalate_to_human", customer_id="PL-48213", summary="Refund for TXN-58237 which is $75.00, exceeds limit"),
             tc(3, "escalate_to_human", customer_id="PL-48213", summary="Refund for TXN-58262 $75.01 exceeds limit"),
             tc(4, "escalate_to_human", customer_id="PL-48213", summary="Customer wants a human about TXN-58214"), say("x")], "hi")
    r = [c[2] for c in a.store.calls if c[0] == "escalate_to_human"]
    assert r[0].get("ok") is False and "ticket_id" in r[1] and "ticket_id" in r[2]


def test_malformed_tool_args_do_not_crash_turn():
    a = run([{"text": None, "tool_calls": [{"id": "x", "name": "issue_refund", "arguments": {"_malformed_arguments": "{bad"}}]},
             {"text": None, "tool_calls": [{"id": "y", "name": "issue_refund", "arguments": {"txn_id": "TXN-58214", "bogus": 1}}]},
             say("ok")], "refund")
    assert a.messages[-1]["content"] == "ok" and not ok_refunds(a)


def test_message_filter_handles_none_content(monkeypatch):
    """Live bug 2026-10-13: assistant tool-call messages have content=None and crashed the API filter."""
    import api.chat as c, io, json as j
    h = c.handler.__new__(c.handler)
    raw = j.dumps({"message": "My email is amara.okafor@maplecrest.test and last 4 is 6417"}).encode()
    h.rfile, h.wfile, h.headers = io.BytesIO(raw), io.BytesIO(), {"Content-Length": str(len(raw))}
    codes = []; h.send_response = codes.append; h.send_header = lambda *a: None; h.end_headers = lambda: None
    for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"): monkeypatch.delenv(k, raising=False)
    h.do_POST()   # demo mode -> scripted provider with tool calls
    assert codes == [200] and j.loads(h.wfile.getvalue())["state"]
