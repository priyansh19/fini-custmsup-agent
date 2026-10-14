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
