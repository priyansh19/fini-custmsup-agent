import pytest
from paylane.agent import Agent
from paylane.providers import ScriptedProvider
from evals.scenarios import SCENARIOS
from evals.run import run_scenario


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_scenario_scripted(sc):
    _, _, results = run_scenario(sc, ScriptedProvider(sc["script"]))
    assert all(r[0] for r in results), [m for g, m in results if not g]
