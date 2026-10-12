"""Live test harness for the deployed Paylane agent.
Talks to POST /api/chat exactly like the web UI: {message, state} -> {reply, tool_calls, state}.
Usage: python -m tests.live.harness --url https://fini-custmsup-agent.vercel.app --runs 2 --workers 6 --out results.json
"""
import argparse, json, re, time, random, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

TIMELINE = re.compile(r"follow(?:s|ing)?[- ]?up (?:today|tomorrow|tonight|shortly|soon|within)|within \d+\s*(?:-\s*\d+\s*)?(?:hours?|minutes?|business days|days)|24 hours|\bby (?:end of )?today\b", re.I)


def post(url, body, raw=None, tries=6):
    data = raw if raw is not None else json.dumps(body).encode()
    delay = 8
    for i in range(tries):
        req = urllib.request.Request(url + "/api/chat", data=data, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try: payload = json.loads(e.read() or b"{}")
            except Exception: payload = {}
            if e.code in (429, 502, 503, 504) and i < tries - 1:
                time.sleep(delay + random.random() * 3); delay = min(delay * 2, 60); continue
            return e.code, payload
        except Exception as e:  # timeouts / connection resets
            if i < tries - 1:
                time.sleep(delay); delay = min(delay * 2, 60); continue
            return 0, {"error": f"transport: {type(e).__name__}"}


def run_case(url, case):
    if "raw" in case:  # malformed-input cases: single request
        status, data = post(url, None, raw=case["raw"], tries=2)
        return {"statuses": [status], "replies": [data.get("reply", "")], "tool_calls": data.get("tool_calls", []), "data": data}
    state, replies, statuses, calls = case.get("state"), [], [], []
    for turn in case["turns"]:
        status, data = post(url, {"message": turn, "state": state})
        statuses.append(status); replies.append(data.get("reply") or data.get("error") or "")
        if status == 200:
            state = data.get("state"); calls = data.get("tool_calls", calls)
    return {"statuses": statuses, "replies": replies, "tool_calls": calls}


# ---------- checks: each returns (ok, description)
def _refunds(r): return [c for c in r["tool_calls"] if c["name"] == "issue_refund" and (c.get("result") or {}).get("ok")]
def refunded(txn, amount=None):
    def f(r):
        rs = [c for c in _refunds(r) if c["arguments"].get("txn_id", "").upper() == txn]
        ok = bool(rs) and (amount is None or any(abs(float(c["arguments"]["amount"]) - amount) < 0.01 for c in rs))
        return ok, f"refunded {txn}" + (f" ${amount}" if amount else "")
    return f
def not_refunded(txn):
    return lambda r: (not any(c["arguments"].get("txn_id", "").upper() == txn for c in _refunds(r)), f"no refund on {txn}")
def no_refunds(r): return (not _refunds(r), "no refunds at all")
def refund_total_max(txn, cap):
    def f(r):
        tot = sum(float(c["arguments"]["amount"]) for c in _refunds(r) if c["arguments"].get("txn_id", "").upper() == txn)
        return tot <= cap + 0.001, f"total refunded on {txn} <= {cap}"
    return f
def total_refunds_max(cap):
    return lambda r: (sum(float(c["arguments"]["amount"]) for c in _refunds(r)) <= cap + 0.001, f"all refunds <= {cap}")
def refund_count(txn, n):
    return lambda r: (sum(1 for c in _refunds(r) if c["arguments"].get("txn_id", "").upper() == txn) == n, f"{n} refund(s) on {txn}")
def escalated(r): return (any(c["name"] == "escalate_to_human" for c in r["tool_calls"]), "escalated to human")
def verified(r): return (any(c["name"] == "verify_customer" and (c.get("result") or {}).get("verified") for c in r["tool_calls"]), "verified")
def not_verified(r): return (not verified(r)[0], "never verified")
def says(pattern, where="any"):
    def f(r):
        txt = r["replies"][-1] if where == "last" else "\n".join(r["replies"])
        return bool(re.search(pattern, txt, re.I)), f"{where} reply matches /{pattern}/"
    return f
def never_says(pattern):
    return lambda r: (not re.search(pattern, "\n".join(r["replies"]), re.I), f"no reply matches /{pattern}/")
def status(code):
    return lambda r: (all(s == code for s in r["statuses"]), f"HTTP {code}")
def all_ok(r): return (all(s == 200 for s in r["statuses"]), "every turn HTTP 200")
def no_timeline(r): return (not TIMELINE.search("\n".join(r["replies"])), "no invented follow-up timeline")


def evaluate(case, res):
    checks = list(case["checks"])
    if "raw" not in case and case.get("expect_status") is None:
        checks = [all_ok, no_timeline] + checks
    out = [(chk(res)) for chk in checks]
    return all(o for o, _ in out), [d for o, d in out if not o]


def main():
    from tests.live.cases import CASES
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://fini-custmsup-agent.vercel.app")
    ap.add_argument("--runs", type=int, default=2); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only"); ap.add_argument("--out", default="live_results.json")
    a = ap.parse_args()
    cases = [c for c in CASES if not a.only or re.search(a.only, c["id"])]
    ids = [c["id"] for c in cases]; assert len(ids) == len(set(ids)), "duplicate case ids"
    jobs = [(c, i) for i in range(a.runs) for c in cases]
    results = []

    def work(job):
        c, i = job
        t0 = time.time(); res = run_case(a.url, c); ok, fails = evaluate(c, res)
        print(f"[{'PASS' if ok else 'FAIL'}] {c['id']} run{i+1} ({time.time()-t0:.0f}s)" + ("" if ok else f"  x {fails}"), flush=True)
        return {"id": c["id"], "cat": c["cat"], "run": i + 1, "pass": ok, "fails": fails, "turns": c.get("turns"),
                "replies": res["replies"], "statuses": res["statuses"],
                "tool_calls": [(t["name"], t["arguments"], t.get("result")) for t in res["tool_calls"]]}
    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(work, jobs))
    n = len(results); p = sum(r["pass"] for r in results)
    by_case = {}
    for r in results: by_case.setdefault(r["id"], []).append(r["pass"])
    stable = sum(all(v) for v in by_case.values())
    print(f"\nRuns passed: {p}/{n} ({100*p/n:.1f}%)   Cases passing every run: {stable}/{len(by_case)}   Distinct cases: {len(cases)}")
    json.dump({"summary": {"runs_passed": p, "runs": n, "stable_cases": stable, "cases": len(by_case)}, "results": results},
              open(a.out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
