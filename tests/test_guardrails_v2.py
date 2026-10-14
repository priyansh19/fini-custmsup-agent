"""Code guardrails added after live testing (round 1)."""
from paylane.agent import Agent, sanitize_reply
from paylane.providers import ScriptedProvider
from evals.scenarios import tc, say
from paylane.policy import refund_allowed
from paylane.data import Store

V = {"verified": True, "customer_id": "PL-48213"}


def run(script, *msgs, confirmed=()):
    """confirmed: txns whose 'refund = cancellation' notice was already given (turn 0), so a
    'yes, go ahead' message passes the cancellation gate. Lets policy tests focus on policy."""
    a = Agent(ScriptedProvider(script))
    for t in confirmed:
        a.session.setdefault("cancel_notice", {})[t] = 0
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


def test_cumulative_exact_75_then_over():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58214", amount=42.5), tc(3, "issue_refund", txn_id="TXN-58277", amount=32.5),
             tc(4, "issue_refund", txn_id="TXN-58209", amount=10), say("x")], "Yes go ahead, these were all billed after I cancelled",
            confirmed=("TXN-58214", "TXN-58277", "TXN-58209"))
    assert len(ok_refunds(a)) == 2


def test_single_75_uses_whole_rolling_allowance():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58237", amount=75), tc(3, "issue_refund", txn_id="TXN-58219", amount=25), say("x")], "Yes go ahead: driver never came and the Apple item arrived broken",
            confirmed=("TXN-58237", "TXN-58219"))
    assert [c[1]["txn_id"] for c in ok_refunds(a)] == ["TXN-58237"]


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
             tc(2, "issue_refund", txn_id="TXN-58214", amount=42.5), say("x")], "Yes go ahead, cancelled but billed", confirmed=("TXN-58214",))
    b = Agent(ScriptedProvider([tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5), say("y")]))
    b.load_state(a.to_state())
    b.send("again")
    assert b.session["verified"] and len(ok_refunds(b)) == 1  # second refund blocked: already refunded


def test_ids_unique_after_state_rebuild():
    """Round-1 live bug: refund ids restarted per serverless instance and overwrote earlier refunds."""
    import paylane.tools as T
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58214", amount=42.5), tc(3, "issue_refund", txn_id="TXN-58277", amount=32.5), say("x")], "Yes go ahead, both were billed after I cancelled",
            confirmed=("TXN-58214", "TXN-58277"))
    st = a.to_state()
    T._ids = __import__("itertools").count(1)  # simulate a cold start
    b = Agent(ScriptedProvider([tc(5, "issue_refund", txn_id="TXN-58219", amount=25), say("y")]))
    b.load_state(st); b.send("and TXN-58219")
    assert len(b.store.refunds) == 2 and not ok_refunds(b)[2:]   # $75 rolling cap reached; R0001/R0002 not overwritten


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


def test_sanitize_soft_timelines_replaced_cleanly():
    from paylane.agent import sanitize_reply
    out = sanitize_reply("I can't give a date. A specialist will reach out to you as soon as possible. Thanks!")
    assert "as soon as" not in out and "as by email" not in out
    assert "A specialist will follow up by email." in out
    out2 = sanitize_reply("They will contact you within 24 hours.")
    assert "24" not in out2


def test_complaint_word_scam_is_not_fraud():
    from paylane.agent import FRAUD_RE
    assert not FRAUD_RE.search("Your app is garbage and your fees are a scam.")
    assert FRAUD_RE.search("I got scammed, someone used my card")


def test_incomplete_credentials_do_not_count_as_failed_attempt():
    from paylane.agent import Agent
    a2 = Agent(provider=None)
    for _ in range(4):
        r = a2._run_tool("verify_customer", {"email": "amara.okafor@maplecrest.test", "last4": ""})
    assert a2.session["failed_verifications"] == 0 and not a2.session["verification_locked"]


def test_resolution_first_blocks_refund_same_turn():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58433", amount=60), say("x")], "Refund the Marriott hold TXN-58433")
    assert not ok_refunds(a)


def test_resolution_first_allows_refund_after_offer_next_turn():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "get_transaction", customer_id="PL-48213", txn_id="TXN-58447"), say("Cancel in Disney+ settings?"),
             tc(3, "issue_refund", txn_id="TXN-58447", amount=12.12, reason="forgot to cancel"), say("Refunding cancels it, ok?"),
             tc(4, "issue_refund", txn_id="TXN-58447", amount=12.12, reason="forgot to cancel"), say("Done")],
            "I forgot to cancel Disney+ TXN-58447", "I'd still like the refund", "Yes, go ahead")
    assert len(ok_refunds(a)) == 1


def test_plain_eligible_refund_needs_cancellation_confirmation():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58214", amount=42.5, reason="cancelled but billed"), say("This cancels it. Go ahead?"),
             tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5, reason="cancelled but billed"), say("Done")],
            "Refund TXN-58214, I cancelled Spotify but was billed", "Yes please")
    assert len(ok_refunds(a)) == 1
    assert a.store.calls[1][2]["reason"] == "confirm_cancellation_first" and "tell_customer" in a.store.calls[1][2]


def test_cancellation_gate_blocks_without_yes():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58214", amount=42.5), say("This cancels it. Go ahead?"),
             tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5), say("ok")],
            "Refund TXN-58214, I cancelled Spotify but was billed", "hmm, what does that mean for my playlists")
    assert not ok_refunds(a)


def test_get_transaction_exposes_resolution_context():
    from paylane.tools import get_transaction
    r = get_transaction(Store(), "PL-48213", "TXN-58451")
    assert r["kind"] == "authorization_hold" and r["related_txn"] == "TXN-58450" and "resolution" in r


def test_reason_gate_asks_once_then_allows():
    # "TXN-58214" alone gives no reason: the first attempt is held so the agent asks what went wrong
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58214", amount=42.5), say("What went wrong with it?"),
             tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5), say("This cancels it, ok?"),
             tc(4, "issue_refund", txn_id="TXN-58214", amount=42.5), say("Done")],
            "I want a refund. amara.okafor@maplecrest.test 6417 TXN-58214", "I cancelled Spotify but was still billed", "yes")
    assert len(ok_refunds(a)) == 1 and a.store.calls[1][2]["reason"] == "ask_reason_first"


def test_reason_gate_not_obstructive_if_customer_wont_say():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58214", amount=42.5), say("What went wrong?"),
             tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5), say("This cancels it, ok?"),
             tc(4, "issue_refund", txn_id="TXN-58214", amount=42.5), say("Done")],
            "refund TXN-58214 amara.okafor@maplecrest.test 6417", "just do it", "yes")
    assert len(ok_refunds(a)) == 1


# ---- proration, delivery, cancellation (Oct 14)
from paylane.policy import subscription_max_refund


def test_proration_examples():
    s = Store()
    assert subscription_max_refund(s.transactions["TXN-58470"])[0] == 12.99    # day 0: full
    assert subscription_max_refund(s.transactions["TXN-58475"])[0] == 30.00    # 59.99 * 15/30
    assert subscription_max_refund(s.transactions["TXN-58447"])[0] == 12.12    # 13.99 * 26/30
    assert refund_allowed(s, V, "TXN-58475", 59.99)[1].startswith("exceeds_prorated_max")
    assert refund_allowed(s, V, "TXN-58475", 30.00)[0]


def _order_run(txn, status_msgs, script_tail):
    return run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
                tc(2, "check_delivery_status", txn_id=txn)] + script_tail, *status_msgs)


def test_delivered_requires_proof_then_refunds():
    a = _order_run("TXN-58461", ["My Allbirds order TXN-58461 never arrived", "I don't know, it just isn't here",
                                 "My neighbour checked her porch and I filed a UPS claim, ref 55102", "Yes, go ahead"],
                   [tc(3, "issue_refund", txn_id="TXN-58461", amount=48), say("Carrier says delivered. Any proof?"),
                    tc(4, "issue_refund", txn_id="TXN-58461", amount=48), say("Still need proof"),
                    tc(5, "issue_refund", txn_id="TXN-58461", amount=48), say("Refunding cancels the order. OK?"),
                    tc(6, "issue_refund", txn_id="TXN-58461", amount=48), say("Done")])
    reasons = [c[2].get("reason") for c in a.store.calls if c[0] == "issue_refund"]
    assert reasons[:3] == ["need_proof_of_non_delivery", "need_proof_of_non_delivery", "confirm_cancellation_first"]
    assert len(ok_refunds(a)) == 1


def test_in_transit_never_refunds():
    a = _order_run("TXN-58480", ["Where is my IKEA order TXN-58480? It hasn't arrived, refund it", "yes refund it anyway"],
                   [tc(3, "issue_refund", txn_id="TXN-58480", amount=64), say("It's in transit"),
                    tc(4, "issue_refund", txn_id="TXN-58480", amount=64), say("Still in transit")])
    assert not ok_refunds(a) and a.store.calls[-1][2]["reason"] == "order_in_transit_no_refund"


def test_order_refund_requires_delivery_check():
    a = run([tc(1, "verify_customer", email="amara.okafor@maplecrest.test", last4="6417"),
             tc(2, "issue_refund", txn_id="TXN-58485", amount=55), say("x")], "My Nike order TXN-58485 never came, yes refund")
    assert a.store.calls[-1][2]["reason"] == "check_delivery_status_first"


def test_lost_order_refunds_after_confirmation():
    a = _order_run("TXN-58485", ["My Nike order TXN-58485 never came", "Yes go ahead"],
                   [tc(3, "issue_refund", txn_id="TXN-58485", amount=55), say("Lost; refunding cancels the order. OK?"),
                    tc(4, "issue_refund", txn_id="TXN-58485", amount=55), say("Done")])
    assert len(ok_refunds(a)) == 1


def test_delivery_status_scoped_to_customer():
    a = run([tc(1, "verify_customer", email="meilin.tan@maplecrest.test", last4="9126"),
             tc(2, "check_delivery_status", txn_id="TXN-58461"), say("x")], "where's my order TXN-58461")
    assert a.store.calls[1][2] == {"error": "no_delivery_record"}


def test_model_stated_notice_in_later_turn_counts():
    # live replay bug: proof given in a turn with no tool call; the model's own "refunding will cancel… $48.00?" must count
    a = _order_run("TXN-58461", ["My Allbirds order TXN-58461 never arrived", "I filed a UPS claim, ref 55102", "Yes, go ahead."],
                   [say("Carrier says delivered. Any proof?"),
                    say("Thanks. Refunding will cancel your order. Proceed with the refund of $48.00?"),
                    tc(3, "issue_refund", txn_id="TXN-58461", amount=48), say("Done")])
    assert len(ok_refunds(a)) == 1
