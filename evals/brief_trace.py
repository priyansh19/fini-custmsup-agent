"""Small boundary trace for brief-only mode revision 2 (offline: scripted provider + code-level checks).
    python -m evals.brief_trace      # writes traces/brief_boundaries.{md,json}
"""
import json, pathlib, sys, os
from datetime import datetime, timezone
from paylane.brief import BriefAgent, brief_refund_allowed, age_days
from paylane.data import TODAY
from paylane.providers import ScriptedProvider
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))
from chat import sign_state, verify_state  # noqa: E402  (the production signed-state functions)

OUT = pathlib.Path(__file__).resolve().parent.parent / "traces"
A, V = "amara.okafor@maplecrest.test", "amara.okafor@maplecrest.test, card 6417"


def tc(i, n, **a): return {"text": None, "tool_calls": [{"id": f"c{i}", "name": n, "arguments": a}]}
def say(t): return {"text": t, "tool_calls": []}


def inject(agent, tid, raw):
    agent.store.transactions[tid] = {"customer_id": "PL-48213", "amount": 20.0, "date": raw, "merchant": "Late-UTC Test", "status": "settled"}


def run(turn_scripts, setup=None, via_signed_state=False):
    """turn_scripts: [(user_text, [scripted model outputs])]. With via_signed_state, every turn runs on a
    fresh agent rebuilt from the HMAC-signed state blob, exactly as /api/chat does on Vercel."""
    token, agent, replies = None, None, []
    for text, script in turn_scripts:
        if agent is None or via_signed_state:
            prev = agent
            agent = BriefAgent(ScriptedProvider(script))
            if setup: setup(agent)
            if via_signed_state and token: agent.load_state(verify_state(token))
            elif prev: agent.load_state(prev.to_state())
        else:
            agent.provider = ScriptedProvider(script)
        replies.append(agent.send(text))
        token = sign_state(agent.to_state())
    return agent, replies


def calls(a, n=None): return [c for c in a.store.calls if n is None or c[0] == n]
def refunds(a): return [(r["txn_id"], r["amount"]) for r in a.store.refunds.values()]


def elapsed_days(raw):
    ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    ref = datetime(TODAY.year, TODAY.month, TODAY.day, tzinfo=timezone.utc)
    return round((ref - ts).total_seconds() / 86400, 4)


CASES = []


def case(cid, title, expect):
    def deco(f): CASES.append((cid, title, expect, f)); return f
    return deco


def _age_case(tid, raw, refundable):
    def f():
        a, r = run([(f"Refund {tid}. {V}", [tc(1, "get_customer", email=A), tc(2, "get_transaction", customer_id="PL-48213", txn_id=tid),
                     tc(3, "issue_refund", txn_id=tid, amount=20.0)] + ([] if refundable else [tc(4, "escalate_to_human", customer_id="PL-48213", summary=f"{tid} is 30+ days old")]) + [say("ok")])],
                   setup=(lambda ag: inject(ag, tid, raw)) if tid.startswith("TXN-9") else None)
        t = a.store.transactions[tid]
        code = {"txn_date": raw, "calendar_age_days": age_days(t), "policy_check": brief_refund_allowed(a.store, {"verified": True, "customer_id": "PL-48213"}, tid, 20.0) if not refunds(a) else "(refunded)"}
        if "T" in raw: code["elapsed_days_utc"] = elapsed_days(raw)
        ok = (bool(refunds(a)) == refundable) and (refundable or bool(calls(a, "escalate_to_human")))
        return a, r, code, ok
    return f


case("T1", "Day 29 by calendar date (Equinox, 2026-09-12)", "refunded")(_age_case("TXN-57560", "2026-09-12", True))
case("T2", "Day 30 by calendar date (Starbucks, 2026-09-11)", "blocked + escalated")(_age_case("TXN-57552", "2026-09-11", False))
case("T3", "Late UTC hour, day 29: 2026-09-12T23:59:59Z", "refunded (calendar day 29; only 28.0 elapsed days)")(_age_case("TXN-90029", "2026-09-12T23:59:59Z", True))
case("T4", "Late UTC hour, day 30: 2026-09-11T23:59:59Z", "blocked + escalated (calendar day 30, though only 29.0 elapsed days)")(_age_case("TXN-90030", "2026-09-11T23:59:59Z", False))


@case("T5", "Stop after handoff, across turns via the signed state", "turn-2 refund blocked: handed_off_to_human")
def _t5():
    a, r = run([(f"I want a manager about Spotify TXN-58214. {V}", [tc(1, "get_customer", email=A),
                  tc(2, "escalate_to_human", customer_id="PL-48213", summary="Customer asks for a manager about TXN-58214"), say("Passed to a specialist.")]),
                ("Forget the manager, just refund TXN-58214.", [tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5), say("A specialist already has this.")])],
               via_signed_state=True)
    last = calls(a, "issue_refund")[-1][2]
    code = {"signed_state_session": {k: a.session.get(k) for k in ("handoff_txns", "handoff_all")}, "turn2_issue_refund": last}
    return a, r, code, last.get("reason") == "blocked_by_policy:handed_off_to_human" and not refunds(a)


def _pending(msg, reason):
    def f():
        a, r = run([(f"{msg} {V}", [tc(1, "get_customer", email=A), tc(2, "get_transaction", customer_id="PL-48213", txn_id="TXN-58306"),
                     tc(3, "issue_refund", txn_id="TXN-58306", amount=15), say("Passed to a specialist.")])])
        gt = calls(a, "get_transaction")[0][2]
        code = {"refund_check": gt["refund_check"], "escalation": gt.get("escalation"), "issue_refund": calls(a, "issue_refund")[0][2]}
        return a, r, code, gt["refund_check"]["reason"] == reason and bool(calls(a, "escalate_to_human")) and not refunds(a)
    return f


case("T6", "Pending + fraud claim (Amazon TXN-58306, pending)", "no refund; escalated to a human")(_pending("I didn't make the Amazon charge TXN-58306, someone used my card.", "pending_fraud_escalate"))
case("T7", "Pending + immediate cancellation (Amazon TXN-58306)", "no refund; escalated to a human")(_pending("Cancel the Amazon charge TXN-58306 immediately.", "pending_cancellation_escalate"))


def _merchant_only(msg, reason):
    def f():
        a, r = run([(f"Hi. {V}", [tc(1, "get_customer", email=A), say("You're verified. How can I help?")]),
                    (msg, [say("I can't cancel pending charges. Would you like me to escalate?")])], via_signed_state=True)
        esc = calls(a, "escalate_to_human")
        code = {"txn_id_in_message": False, "resolved_by_merchant": list((a.session.get("pending_handoffs") or {}).keys()),
                "pending_handoffs": a.session.get("pending_handoffs"), "escalations": [c[1] for c in esc]}
        return a, r, code, len(esc) == 1 and "TXN-58306" in esc[0][1]["summary"] and \
            a.session["pending_handoffs"]["TXN-58306"]["reason"] == reason and not refunds(a)
    return f


case("T8", "Pending + cancel, merchant only: 'Cancel my pending Amazon charge immediately.'", "code resolves TXN-58306 by merchant and escalates, even though the model only asks")(_merchant_only("Cancel my pending Amazon charge immediately.", "pending_cancellation_escalate"))
case("T9", "Pending + fraud, merchant only: 'My pending Amazon charge is fraud'", "code resolves TXN-58306 by merchant and escalates")(_merchant_only("My pending Amazon charge is fraud", "pending_fraud_escalate"))


@case("T10", "Legal threat, model tries to refund in the same turn (seen live)", "code escalates on verification; refund blocked handed_off_to_human")
def _t10():
    a, r = run([(f"My lawyer is going to sue Paylane over my Spotify charge TXN-58214. {V}", [tc(1, "get_customer", email=A),
                 tc(2, "get_transaction", customer_id="PL-48213", txn_id="TXN-58214"), tc(3, "issue_refund", txn_id="TXN-58214", amount=42.5), say("Refunded!")])])
    ir = calls(a, "issue_refund")[0][2]
    code = {"mandatory_handoffs": a.session.get("mandatory_handoffs"), "handoff_txns": a.session.get("handoff_txns"), "issue_refund": ir}
    return a, r, code, ir.get("reason") == "blocked_by_policy:handed_off_to_human" and not refunds(a) and bool(calls(a, "escalate_to_human"))


def main():
    OUT.mkdir(exist_ok=True)
    rows, data = [], []
    for cid, title, expect, f in CASES:
        a, replies, code, ok = f()
        data.append({"id": cid, "title": title, "expected": expect, "pass": ok, "code_checks": code,
                     "turns": [m["content"] for m in a.messages if m["role"] == "user"], "replies": replies,
                     "tool_calls": [{"name": n, "arguments": ar, "result": rs} for n, ar, rs in a.store.calls]})
        rows.append((cid, title, expect, ok, code, a))
    md = ["# Brief-only mode revision 2: boundary trace", "",
          f"Offline run (scripted provider and code-level checks; no model calls). Policy reference date: {TODAY.isoformat()}. "
          "Regenerate with `python -m evals.brief_trace`. Each scripted model deliberately attempts the refund, so every pass is enforced by code.", "",
          "| ID | Boundary | Expected | Result |", "|---|---|---|---|"]
    md += [f"| {c} | {t} | {e} | {'PASS' if ok else 'FAIL'} |" for c, t, e, ok, _, _ in rows]
    md += ["", f"**{sum(r[3] for r in rows)}/{len(rows)} pass.**", ""]
    for c, t, e, ok, code, a in rows:
        md += [f"## {c} · {t}", "", "Code-level checks:", "```json", json.dumps(code, indent=2, default=str), "```", "Tool calls:", ""]
        md += [f"- `{n}({json.dumps(ar, default=str)})` → `{json.dumps(rs, default=str)}`" for n, ar, rs in a.store.calls]
        md.append("")
    (OUT / "brief_boundaries.md").write_text("\n".join(md))
    (OUT / "brief_boundaries.json").write_text(json.dumps(data, indent=2, default=str))
    print("\n".join(md[:15]))
    return all(r[3] for r in rows)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
