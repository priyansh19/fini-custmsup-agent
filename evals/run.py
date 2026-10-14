"""Run all scenarios, print score, save transcripts.
  python -m evals.run --scripted     # no API key, uses canned scripts
  python -m evals.run                # real LLM via PAYLANE_PROVIDER + key
"""
import argparse, json, pathlib
from paylane.agent import Agent
from paylane.providers import ScriptedProvider, from_env
from evals.scenarios import SCENARIOS
from evals.scenarios_brief import SCENARIOS_BRIEF
from paylane.brief import make_agent

OUT = pathlib.Path(__file__).resolve().parent.parent / "transcripts"


def run_scenario(sc, provider, mode="expanded"):
    agent = make_agent(provider, mode=mode)
    replies = [agent.send(t) for t in sc["turns"]]
    results = [chk(agent, replies) for chk in sc["checks"]]
    return agent, replies, results


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--scripted", action="store_true"); ap.add_argument("--only")
    ap.add_argument("--mode", choices=["expanded", "brief"], default="expanded",
                    help="expanded = submitted version (26 scenarios); brief = Deepak's brief only (22 scenarios)")
    a = ap.parse_args()
    out = OUT / "scripted" if a.scripted else OUT
    if a.mode == "brief":
        out = out / "brief"   # committed transcripts/ = real-model runs only
    out.mkdir(parents=True, exist_ok=True)
    passed = 0
    scs = [s for s in (SCENARIOS_BRIEF if a.mode == "brief" else SCENARIOS) if not a.only or s["id"] == a.only]
    for sc in scs:
        prov = ScriptedProvider(sc["script"]) if a.scripted else from_env()
        agent, replies, results = run_scenario(sc, prov, a.mode)
        ok = all(r[0] for r in results); passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {sc['id']}")
        for good, msg in results:
            if not good: print(f"    x {msg}")
        (out / f"{sc['id']}.json").write_text(json.dumps({"scenario": sc["id"], "why": sc["why"], "messages": agent.messages,
            "tool_calls": agent.store.calls, "checks": [{"pass": g, "check": m} for g, m in results]}, indent=2, default=str))
    print(f"\nScore ({a.mode} mode{', scripted' if a.scripted else ''}): {passed}/{len(scs)}")


if __name__ == "__main__":
    main()
