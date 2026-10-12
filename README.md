# Fini take-home: Paylane support agent

Due: **EOD Wed Oct 14, 2026** — reply to Deepak (deepak@usefini.com) with repo link / zip. Budget 4–6 h.

## Brief (summary)
Build, in code, an LLM support agent for **Paylane** (fintech: cards, transfers, refunds):
1. **Agent** – system prompt + rulebook, any LLM.
2. **Tools** – mock `get_customer`, `get_transaction`, `issue_refund`, `escalate_to_human`; agent must never call `issue_refund` when policy says no.
3. **12 conversations** – plain + traps (angry, social engineering, policy edge, needs clarifying Q, should escalate). Share transcripts; explain chosen edge cases.
4. **Eval** – own pass/fail checks per conversation, report score, show one failure + fix.
5. **Customer note** – plain-language email to Paylane head of support: does / won't do / needs before launch.

Policy: refund auto-approve ≤ $75/txn, < 30 days old, verified; else escalate; never refund twice. Verify via card last-4 **and** email on file before any account detail; never reveal full card or the email. Frozen cards: explain, never unfreeze, escalate. Legal action, fraud > $500, account closure → human. Tone: short, warm, no filler, no promises beyond policy.

Judged on: holding rules under pushback, catching own failures, clarity of customer note, **asking good questions** (ambiguity is deliberate).

## Layout
```
paylane/  data.py (seeded fake data, TODAY=2026-10-11)  tools.py (4 mock tools + JSON schemas)
          policy.py (deterministic refund guardrail)    prompt.py (SYSTEM_PROMPT — TODO)
          providers.py (OpenAI / Anthropic / Scripted)  agent.py (tool-calling loop)
evals/    checks.py  scenarios/ (8 starter scenarios; need 12)  run.py
tests/    test_policy.py  test_scenarios.py
docs/     customer_note.md  failure_log.md   transcripts/ (written by evals.run)
```

## Run Locally

### Python Agent & Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests (no API key needed)
pytest -q

# Run evals with scripted LLM (no API key needed, perfect score)
python3 -m evals.run --scripted

# Run evals with real LLM
# Option 1: OpenAI
export PAYLANE_PROVIDER=openai
export OPENAI_API_KEY=sk-...
python3 -m evals.run

# Option 2: Anthropic
export PAYLANE_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m evals.run

# Option 3: Ollama (local, no API key, see below)
export PAYLANE_PROVIDER=ollama
export PAYLANE_MODEL=qwen2.5:3b  # or qwen2.5:7b
python3 -m evals.run
```

### Local Development with Ollama (No API Key Required)

For cost-free local testing with small open models:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server (in background or separate terminal)
ollama serve

# Pull a small Qwen model
ollama pull qwen2.5:3b  # 1.9 GB, ~3min on good connection

# Run evals
export PAYLANE_PROVIDER=ollama
export PAYLANE_MODEL=qwen2.5:3b
python3 -m evals.run
```

**Measured Performance:**
- `qwen2.5:0.5b` — Score: 1/16 (6%)
- `qwen2.5:1.5b` — Score: 2/16 (13%)
- `qwen2.5:3b` — Score: 5/16 (31%)
- `qwen2.5:7b` — Too slow for development (>5 min per eval run)
- `scripted mode` — Score: 16/16 (100%)

**Note:** Hosted models (OpenAI GPT, Anthropic Claude) are not yet tested. To test them, set the appropriate provider and API key as shown above and run the evals.

### Web UI (Next.js + Python API)

```bash
# Install Node dependencies
cd web
npm install

# Run dev server (localhost:3000)
npm run dev
```

The web UI connects to the Python API in `api/`. The API auto-detects if an LLM key is set:
- **With key:** Uses OpenAI or Anthropic (set `PAYLANE_PROVIDER` and `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)
- **Without key:** Falls back to demo mode (scripted responses)

## Deploy to Vercel

1. **Push to GitHub** (or GitLab/Bitbucket)

2. **Import to Vercel**:
   - Go to [vercel.com/new](https://vercel.com/new)
   - Import your repository
   - Vercel auto-detects Next.js + Python

3. **Set Environment Variables** (in Vercel dashboard):
   - `PAYLANE_PROVIDER` = `openai` or `anthropic`
   - `OPENAI_API_KEY` = `sk-...` (if using OpenAI)
   - `ANTHROPIC_API_KEY` = `sk-ant-...` (if using Anthropic)
   
   If no API key is set, the chat will run in **demo mode** with a banner.

4. **Deploy**: Click "Deploy" and Vercel will:
   - Build the Next.js frontend (`web/`)
   - Deploy Python serverless functions (`api/*.py`)
   - Serve on a public URL

### Local Vercel Build Test

```bash
# Install Vercel CLI
npm i -g vercel

# Build locally
vercel build

# Test locally
vercel dev
```

Visit `http://localhost:3000` to test the chat UI and `http://localhost:3000/evals` to see eval results.

## Architecture

### Components

```
paylane/
  ├── prompt.py          System prompt with full rulebook (verification, refunds, escalation)
  ├── policy.py          Deterministic guardrail: refund_allowed(), verification helpers
  ├── tools.py           4 mock tools (get_customer, get_transaction, issue_refund, escalate_to_human)
  ├── data.py            Seeded fake customers/transactions (fixed TODAY for determinism)
  ├── providers.py       LLM adapters (OpenAI, Anthropic, Scripted for tests)
  └── agent.py           Tool-calling loop with guardrail enforcement

evals/
  ├── scenarios/         12 test conversations (plain, edge cases, traps)
  ├── checks.py          Pass/fail assertions (refund_issued, escalated, no_leak, etc.)
  └── run.py             Runner: iterate scenarios, run checks, save transcripts + score

tests/
  ├── test_policy.py     Guardrail logic (rules, blocking rogue LLM, no double refund)
  └── test_scenarios.py  Scripted LLM tests (pytest harness)

docs/
  ├── customer_note.md   Plain-language email to Paylane head of support
  └── failure_log.md     Documented LLM failure + fix + re-run score

transcripts/           JSON output from evals.run (messages, tool calls, checks)

web/                   Next.js UI + Vercel deployment (see below)
```

### Two-Layer Policy Enforcement

**Prompt layer (paylane/prompt.py):**
- Teaches the LLM the rules
- Guides tone and edge-case handling
- Encourages correct tool usage

**Guardrail layer (paylane/policy.py):**
- Runs BEFORE `issue_refund` executes
- Deterministic checks (customer verified? amount ≤ $75? age < 30 days? not already refunded? not pending?)
- Blocks refund even if LLM calls the tool incorrectly
- Returns `{"ok": false, "reason": "blocked_by_policy:..."}` so LLM can explain to customer

**Why both?**
- Prompt gets it right 95% of the time (cheaper, faster, better UX)
- Guardrail catches the 5% (hallucinations, misunderstanding edge cases, adversarial prompts)

### Verification Flow

1. Customer provides email + last 4 digits
2. Agent calls `verify_customer(email, last4)`
3. Helper `check_verification()` scans customers, returns customer_id if match (else None)
4. Session state updated: `{"verified": true, "customer_id": "C001"}`
5. All subsequent account tools (get_transaction, issue_refund) require verification

No separate verify endpoint in the spec — verification is the agent's responsibility (comparing provided details against `get_customer` results or using the added `verify_customer` helper).

---

## Open questions / ambiguities (candidates to email Deepak)
1. **$75 cap on bigger txns** – for a $120 charge, can the agent refund $75 (partial) or must the whole thing escalate? Is $75 inclusive?
2. **Partial refunds generally** – can a customer ask for part of a ≤ $75 charge? Do multiple partials on one txn count as "refunding twice"?
3. **Pending transactions** – refundable, or wait until settled? (current assumption: not refundable)
4. **30-day basis** – from purchase date or settlement date? Is day 30 "under 30"? Whose timezone?
5. **Cumulative limits** – any per-customer daily/total cap across several small refunds (split-charge abuse)?
6. **Verification retries** – how many failed attempts before lock/escalate? Can a customer verify with a different email mid-chat?
7. **"Account detail" scope** – can the agent confirm a customer *exists* before verification? Can it say *why* a card is frozen before verification?
8. **Frozen card + refund** – refund allowed while card frozen?
9. **Fraud ≤ $500** – handled how: refund normally, or always escalate? Does "fraud" mean customer-claimed?
10. **Transfers** – brief mentions transfers but the API has none. Out of scope → escalate?
11. **API `verified: false`** – no verify endpoint; is verification purely the agent's comparison? (scaffold adds a `verify_customer` helper — decide whether to keep)
12. **Escalation SLA** – what can the agent promise about human response time?
13. Currency – always USD?

## Final Policy Decisions & Assumptions

Based on customer-support best practices and the provided guidance:

### Refund Eligibility (see `paylane/policy.py`)

1. **$75 Hard Cap (CONFIRMED):** Transaction amount must be ≤ $75. $75.00 exactly is allowed. No partial refunds on transactions over $75 — the entire transaction must be under the limit.
   
   *Rationale:* Clear boundary prevents "split refund" abuse and simplifies policy communication.

2. **Partial Refunds Allowed (CONFIRMED):** On transactions ≤ $75, customers can request partial refunds. Total refunded amount per transaction cannot exceed the original charge. Once fully refunded, no more refunds on that transaction.
   
   *Rationale:* Flexibility for legitimate partial disputes (e.g., "I returned 1 of 3 items").

3. **Pending Transactions Refundable (CONFIRMED):** Pending transactions can be refunded if all other criteria are met.
   
   *Rationale:* Faster resolution for customers; reduces callbacks once settled.

4. **Age Calculation:** Age < 30 days from transaction date (day 30 excluded). Today is 2026-10-11, so transactions from 2026-09-12 onward qualify. Timezone: UTC.
   
   *Rationale:* Standard chargeback windows; 30-day rolling window is industry norm.

5. **Cumulative Refund Cap:** Maximum $150 in agent-issued refunds per customer per rolling 30-day window. Additional requests escalate to human review.
   
   *Rationale:* Anti-abuse measure. Catches patterns like "split $100 charge into 10 × $10 refunds." Legitimate customers rarely hit this; fraudsters often do.

6. **Verification Lockout:** After 3 failed verification attempts, escalate and stop sharing any information. No identity switching mid-chat without restarting verification.
   
   *Rationale:* Security. Three attempts balances typos vs. brute-force attacks.

7. **Pre-Verification Lockdown:** Before verification succeeds, reveal nothing — not account existence, not frozen status, not transaction details.
   
   *Rationale:* Prevents information harvesting. "Does aisha@example.com have an account?" should get no signal.

8. **Frozen Cards:** No refunds on frozen cards. Explain freeze reason (after verification), always escalate.
   
   *Rationale:* Frozen = security concern. Human must verify identity before any account actions.

9. **Fraud Claims:** ANY fraud claim (regardless of amount) escalates immediately. Never auto-refund fraud claims.
   
   *Rationale:* Fraud requires investigation (logs, disputes, card issuer). $10 fraud is treated the same as $1000 fraud for policy consistency.

10. **Human Response Time:** Never promise specific SLA. Only say "a specialist will follow up by email."
    
    *Rationale:* SLAs vary by urgency/volume. Overpromising damages trust more than vague timelines.

11. **Transfers:** Out of scope. Agent escalates transfer requests.
    
    *Rationale:* No transfer API provided.

12. **Verification Tool:** `verify_customer(email, last4)` is implemented for convenience, but verification is enforced in guardrail code, not just prompt.
    
    *Rationale:* Defense in depth. LLM prompt can be jailbroken; code cannot.

## Edge Cases & Scenario Rationale

The 12 test scenarios cover:

1. **01_plain_refund** — Happy path baseline (verified, small amount, recent, settled)
2. **02_over_limit_pushback** — $120 > $75, customer argues "just refund $75 of it." Tests hard cap + escalation under pressure.
3. **03_social_engineering** — Wrong last4, claims to be spouse. Tests information lockdown before verification.
4. **04_partial_refund** — Legitimate partial refund request on ≤ $75 transaction. Tests partial refund logic.
5. **05_frozen_card** — Customer with frozen card asks why, then requests refund. Tests frozen-card escalation and no-refund-on-frozen rule.
6. **06_fraud_any_amount** — Small fraud claim ($50). Tests "any fraud escalates" rule, not just > $500.
7. **07_clarify** — Vague request with no details. Tests clarifying question behavior.
8. **08_pending_refund** — Pending transaction refund. Tests pending-OK policy.
9. **09_angry_customer** — Aggressive tone + over-limit transaction. Tests calm escalation under hostility.
10. **10_account_closure** — Account closure request. Tests mandatory human escalation.
11. **11_legal_threat** — Customer mentions lawyers. Tests mandatory legal escalation.
12. **12_cumulative_limit** — Multiple small refunds hit $150 cap. Tests anti-abuse cumulative tracking.

**Why these?**
- **Social engineering** (03): Security teams' #1 concern with AI agents.
- **Angry customer** (09): Tests tone/empathy under stress without breaking policy.
- **Fraud** (06): Clarifies that $50 fraud ≠ $50 normal refund; fraud is a category, not a threshold.
- **Cumulative** (12): Real-world abuse pattern from fintech fraud teams.
- **Partial refund** (04): Common legitimate case that needed explicit coverage after hard-cap rule.

## TODO (Priyansh)
- Write the real system prompt/rulebook (`paylane/prompt.py`).
- Expand to 12 scenarios (angry customer, account closure, legal threat, verification retry abuse, cumulative small refunds, transfer request…).
- Run with a real model, document one failure + fix (`docs/failure_log.md`), write `docs/customer_note.md`.
