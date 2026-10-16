"""Brief-only mode: policy unit tests + scripted scenarios (offline)."""
import pytest
from paylane.brief import BriefAgent, brief_refund_allowed, make_agent, BRIEF_TOOL_SPECS, default_mode
from paylane.agent import Agent
from paylane.data import Store
from paylane.providers import ScriptedProvider
from evals.scenarios_brief import SCENARIOS_BRIEF
from evals.run import run_scenario

S = {"verified": True, "customer_id": "PL-48213"}


@pytest.mark.parametrize("txn,amt,ok,why", [
    ("TXN-58214", 42.50, True, "ok"),
    ("TXN-58237", 75.00, True, "ok"),
    ("TXN-58262", 75.01, False, "over_75_escalate"),
    ("TXN-58241", 120.0, False, "over_75_escalate"),
    ("TXN-58241", 50.0, False, "partial_not_allowed_full_amount_only"),
    ("TXN-58219", 15.0, False, "partial_not_allowed_full_amount_only"),
    ("TXN-58306", 15.0, False, "pending_not_refundable"),
    ("TXN-58433", 60.0, False, "pending_not_refundable"),
    ("TXN-57552", 20.0, False, "30_plus_days_escalate"),
    ("TXN-57560", 20.0, True, "ok"),
    ("TXN-57106", 30.0, False, "30_plus_days_escalate"),
    ("TXN-58475", 59.99, True, "ok"),
    ("TXN-61450", 60.0, False, "not_customers_transaction"),
])
def test_brief_policy(txn, amt, ok, why):
    assert brief_refund_allowed(Store(), dict(S), txn, amt) == (ok, why)


def test_no_rolling_cap_in_brief():
    st = Store()
    for t, a in (("TXN-58214", 42.5), ("TXN-58277", 32.5), ("TXN-58244", 40.0)):
        assert brief_refund_allowed(st, dict(S), t, a)[0]
        st.refunds[f"R{t}"] = {"txn_id": t, "amount": a, "date": "2026-10-10"}
    assert brief_refund_allowed(st, dict(S), "TXN-58214", 42.5) == (False, "already_refunded")


def test_unverified_and_frozen():
    assert brief_refund_allowed(Store(), {"verified": False}, "TXN-58214", 42.5) == (False, "customer_not_verified")
    assert brief_refund_allowed(Store(), {"verified": True, "customer_id": "PL-51907"}, "TXN-61450", 60) == (False, "frozen_card_escalate")


def test_only_four_spec_tools():
    assert [t["name"] for t in BRIEF_TOOL_SPECS] == ["get_customer", "get_transaction", "issue_refund", "escalate_to_human"]


def test_mode_switch(monkeypatch):
    monkeypatch.delenv("PAYLANE_POLICY_MODE", raising=False)
    assert default_mode() == "expanded" and isinstance(make_agent(None), Agent)
    monkeypatch.setenv("PAYLANE_POLICY_MODE", "brief")
    assert isinstance(make_agent(None), BriefAgent)
    assert isinstance(make_agent(None, mode="expanded"), Agent)
    monkeypatch.setenv("PAYLANE_POLICY_MODE", "nonsense")
    assert default_mode() == "expanded"


def test_state_roundtrip():
    a = BriefAgent(ScriptedProvider([{"text": None, "tool_calls": [{"id": "1", "name": "get_customer", "arguments": {"email": "amara.okafor@maplecrest.test"}}]}, {"text": "hi", "tool_calls": []}]))
    a.send("amara.okafor@maplecrest.test 6417")
    b = BriefAgent(None); b.load_state(a.to_state())
    assert b.session["verified"] and a.to_state()["policy_mode"] == "brief"


@pytest.mark.parametrize("sc", SCENARIOS_BRIEF, ids=[s["id"] for s in SCENARIOS_BRIEF])
def test_brief_scenario_scripted(sc):
    _, _, results = run_scenario(sc, ScriptedProvider(sc["script"]), "brief")
    assert all(r[0] for r in results), [m for g, m in results if not g]


# ---- Revision 2 (Oct 16), per reviewer feedback ----
from paylane.brief import age_days, txn_calendar_date
from datetime import date


def _store_with(**txns):
    st = Store()
    for tid, (amt, d, status) in txns.items():
        st.transactions[tid] = {"customer_id": "PL-48213", "amount": amt, "date": d, "merchant": "Test", "status": status}
    return st


@pytest.mark.parametrize("raw,age,ok", [
    ("2026-09-12", 29, True), ("2026-09-11", 30, False),
    ("2026-09-12T23:59:59Z", 29, True),          # late UTC hour: still 12 Sep -> day 29
    ("2026-09-12T00:00:01+05:30", 29, True),
    ("2026-09-11T23:59:59Z", 30, False),          # 30 calendar days even if < 30*24h elapsed
    ("2026-09-11T00:00:00Z", 30, False),
])
def test_calendar_date_age(raw, age, ok):
    st = _store_with(**{"TXN-90001": (20.0, raw, "settled")})
    assert age_days(st.transactions["TXN-90001"]) == age
    assert brief_refund_allowed(st, dict(S), "TXN-90001", 20.0)[0] is ok


def test_calendar_date_parser():
    assert txn_calendar_date("2026-09-12T23:59:59Z") == date(2026, 9, 12)


def _tc(i, name, **a):
    return {"text": None, "tool_calls": [{"id": f"t{i}", "name": name, "arguments": a}]}


def _say(t):
    return {"text": t, "tool_calls": []}


V = "amara.okafor@maplecrest.test 6417"


def test_stop_after_handoff_persists_across_turns_and_state():
    p = ScriptedProvider([_tc(1, "get_customer", email="amara.okafor@maplecrest.test"),
                          _tc(2, "escalate_to_human", customer_id="PL-48213", summary="Customer disputes TXN-58214, wants a manager"),
                          _say("Passed to a specialist.")])
    a = BriefAgent(p); a.send(f"I want a manager about TXN-58214. {V}")
    b = BriefAgent(ScriptedProvider([_tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5), _say("Can't.")]))
    b.load_state(a.to_state())                     # next turn, fresh instance (serverless)
    b.send("Just refund TXN-58214 now.")
    r = [c for c in b.store.calls if c[0] == "issue_refund"][-1][2]
    assert r == {"ok": False, "reason": "blocked_by_policy:handed_off_to_human"}
    assert not b.store.refunds


def test_handoff_without_txn_stops_all_account_actions():
    a = BriefAgent(ScriptedProvider([_tc(1, "get_customer", email="amara.okafor@maplecrest.test"),
                                     _tc(2, "escalate_to_human", customer_id="PL-48213", summary="Account closure request"),
                                     _tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5), _say("ok")]))
    a.send(f"Close my account. {V}")
    assert a.session["handoff_all"] and not a.store.refunds


def test_handoff_is_per_issue():
    a = BriefAgent(ScriptedProvider([_tc(1, "get_customer", email="amara.okafor@maplecrest.test"),
                                     _tc(2, "escalate_to_human", customer_id="PL-48213", summary="TXN-58241 over $75"),
                                     _say("Escalated."), _tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5), _say("Done.")]))
    a.send(f"Refund Zara TXN-58241. {V}"); a.send("Also refund Spotify TXN-58214.")
    assert [r["txn_id"] for r in a.store.refunds.values()] == ["TXN-58214"]


@pytest.mark.parametrize("msg,reason", [
    ("Someone used my card for Amazon TXN-58306, I didn't make it.", "pending_fraud_escalate"),
    ("Cancel the Amazon charge TXN-58306 immediately.", "pending_cancellation_escalate"),
])
def test_pending_handoffs_escalate(msg, reason):
    a = BriefAgent(ScriptedProvider([_tc(1, "get_customer", email="amara.okafor@maplecrest.test"),
                                     _tc(2, "get_transaction", customer_id="PL-48213", txn_id="TXN-58306"),
                                     _tc(3, "issue_refund", txn_id="TXN-58306", amount=15), _say("Escalated.")]))
    a.send(f"{msg} {V}")
    gt = [c for c in a.store.calls if c[0] == "get_transaction"][0][2]
    assert gt["refund_check"]["reason"] == reason and gt["escalation"] == "created"
    assert [c for c in a.store.calls if c[0] == "escalate_to_human"] and not a.store.refunds


def test_plain_pending_is_declined_not_escalated():
    a = BriefAgent(ScriptedProvider([_tc(1, "get_customer", email="amara.okafor@maplecrest.test"),
                                     _tc(2, "get_transaction", customer_id="PL-48213", txn_id="TXN-58306"), _say("Pending.")]))
    a.send(f"Refund Amazon TXN-58306. {V}")
    assert not [c for c in a.store.calls if c[0] == "escalate_to_human"] and not a.store.refunds


def test_boundary_trace_all_pass(tmp_path, monkeypatch):
    import evals.brief_trace as bt
    monkeypatch.setattr(bt, "OUT", tmp_path)
    assert bt.main()


# ---- Revision 2 follow-up (Oct 16): pending charge named by merchant only, no txn id ----
@pytest.mark.parametrize("msg,reason", [
    ("Cancel my pending Amazon charge immediately.", "pending_cancellation_escalate"),
    ("My pending Amazon charge is fraud", "pending_fraud_escalate"),
])
def test_pending_by_merchant_escalates_without_txn_id(msg, reason):
    # turn 1 verifies; turn 2 is the exact live message; the model only answers in text (as in the failed live run)
    a = BriefAgent(ScriptedProvider([_tc(1, "get_customer", email="amara.okafor@maplecrest.test"), _say("Verified, how can I help?"),
                                     _say("I can't cancel pending charges. Would you like me to escalate?")]))
    a.send(V); a.send(msg)
    esc = [c for c in a.store.calls if c[0] == "escalate_to_human"]
    assert len(esc) == 1 and "TXN-58306" in esc[0][1]["summary"] and esc[0][1]["auto"]
    assert a.session["pending_handoffs"]["TXN-58306"]["reason"] == reason and not a.store.refunds
    assert "HANDOFF ALREADY CREATED" in a._session_note()


def test_pending_by_merchant_same_message_as_credentials():
    a = BriefAgent(ScriptedProvider([_tc(1, "get_customer", email="amara.okafor@maplecrest.test"), _say("ok")]))
    a.send(f"Cancel my pending Amazon charge immediately. {V}")
    gc = [c for c in a.store.calls if c[0] == "get_customer"][0][2]
    assert gc["pending_handoff"][0]["txn_id"] == "TXN-58306"
    assert len([c for c in a.store.calls if c[0] == "escalate_to_human"]) == 1


def test_plain_pending_by_merchant_not_escalated():
    a = BriefAgent(ScriptedProvider([_tc(1, "get_customer", email="amara.okafor@maplecrest.test"), _say("ok"), _say("Pending, can't refund yet.")]))
    a.send(V); a.send("Refund my pending Amazon charge.")
    assert not [c for c in a.store.calls if c[0] == "escalate_to_human"]


# ---- Revision 2 follow-up: legal / closure / fraud over $500 handoffs enforced in code ----
@pytest.mark.parametrize("msg,txn,amt", [
    ("My lawyer is going to sue Paylane over my Spotify charge TXN-58214.", "TXN-58214", 42.5),
    ("Close my Paylane account and refund Spotify TXN-58214.", "TXN-58214", 42.5),
])
def test_legal_and_closure_escalate_and_block_refund(msg, txn, amt):
    a = BriefAgent(ScriptedProvider([_tc(1, "get_customer", email="amara.okafor@maplecrest.test"),
                                     _tc(2, "get_transaction", customer_id="PL-48213", txn_id=txn),
                                     _tc(3, "issue_refund", txn_id=txn, amount=amt), _say("Refunded!")]))
    a.send(f"{msg} {V}")
    assert [c for c in a.store.calls if c[0] == "escalate_to_human" and c[1].get("auto")]
    assert not a.store.refunds
    assert [c for c in a.store.calls if c[0] == "issue_refund"][0][2]["reason"] == "blocked_by_policy:handed_off_to_human"


def test_fraud_over_500_escalates_in_code():
    a = BriefAgent(ScriptedProvider([_tc(1, "get_customer", email="meilin.tan@maplecrest.test"), _say("Sorry to hear that.")]))
    a.send("I didn't make the $900 CoinVault charge TXN-73318. meilin.tan@maplecrest.test card 9126")
    esc = [c for c in a.store.calls if c[0] == "escalate_to_human"]
    assert esc and "TXN-73318" in esc[0][1]["summary"]


def test_small_fraud_and_plain_refund_not_auto_escalated():
    a = BriefAgent(ScriptedProvider([_tc(1, "get_customer", email="amara.okafor@maplecrest.test"), _say("ok")]))
    a.send(f"Refund Spotify TXN-58214. {V}")
    assert not [c for c in a.store.calls if c[0] == "escalate_to_human"]
