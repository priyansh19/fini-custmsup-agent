# Failure Log — Real LLM Testing with Ollama + Qwen

## Test Environment

**Local LLM via Ollama:**
- qwen2.5:0.5b — Score: **1/12** (catastrophic failure, unusable)
- qwen2.5:1.5b — Score: **2/12** (mostly broken)
- qwen2.5:3b — Score: **4/12** after prompt hardening (marginally usable)
- qwen2.5:7b — Too slow for development testing (>5 min for 12 scenarios)

**Note:** qwen2.5:3b is the smallest tested model that shows any competence with tool calling, but still fails 67% of scenarios. Hosted models (OpenAI GPT, Anthropic Claude) have not yet been tested.

---

## Real Failure #1: Model Doesn't Call Tools (Scenario 06: Fraud Claim)

### Transcript Excerpt (qwen2.5:3b, Run 1)

**User:**
```
I didn't make this $50 Lyft charge T301, someone stole my card! chen@example.com, 0007
```

**Assistant Response:**
```
That sounds urgent and concerning. I'll need to verify your details first. Please provide the last 4 digits of your card.
```

**Tools Called:** NONE ❌

### Root Cause

The model completely ignored that:
1. The last 4 digits ("0007") were already provided in the message
2. The email ("chen@example.com") was already provided
3. The system prompt instructs to ALWAYS call `verify_customer` first
4. The user mentioned fraud, which requires escalation after verification

The model responded with **text only** instead of using the required tools. This is a fundamental reading comprehension + instruction-following failure common in small models.

### Fix Applied

**Prompt Hardening (paylane/prompt.py):**

Added explicit, emphatic instructions at the top:

```
CRITICAL: You MUST use the provided tools. Never respond with text alone when tools are required. 
Always call verify_customer first before any account action.
```

And in the verification section:

```
**ALWAYS call verify_customer(email, last4) as your FIRST action.** This is MANDATORY.
```

And in escalation rules:

```
**CRITICAL SEQUENCE:** Even for escalations, you MUST verify_customer first to get the customer_id. 
Then call escalate_to_human(customer_id, summary).
```

### Re-run Result

After fix, scenario 06 improved slightly (model now sometimes calls verify_customer), but still inconsistent.

**New issue:** Model often asks for information already provided, showing poor context awareness.

---

## Real Failure #2: Model Says "I Can Issue" Instead of Actually Issuing (Scenario 01: Plain Refund)

### Transcript Excerpt (qwen2.5:3b, Run 2)

**User:**
```
Hi, I was charged for Spotify twice, txn T100. Email aisha@example.com, card ends 4242.
```

**Assistant Tool Calls:**
1. ✓ `verify_customer(email="aisha@example.com", last4="4242")` → `{"verified": true, "customer_id": "C001"}`
2. ✓ `get_transaction(customer_id="C001", txn_id="T100")` → `{"amount": 42.5, "date": "2026-10-01", "merchant": "Spotify", "status": "settled"}`

**Assistant Response:**
```
The charge for Spotify was $42.50, settled on Oct 1, 2026. I can issue a refund for you.
```

**Tools Called After:** NONE ❌ (should have called `issue_refund`)

### Root Cause

The model correctly:
- Verified the customer
- Fetched the transaction
- Recognized the transaction qualifies for refund ($42.50 ≤ $75, < 30 days old)

But then it **stopped** and said "I can issue a refund" instead of **actually calling** `issue_refund(txn_id="T100", amount=42.5)`.

This is a classic "hesitant LLM" problem: the model thinks it needs user confirmation before taking action, even when the system prompt says to just do it.

### Fix Applied

**Prompt Hardening (paylane/prompt.py):**

Added explicit workflow with strong directive:

```
**WORKFLOW FOR REFUND REQUESTS (FOLLOW EXACTLY):**
1. Call verify_customer(email, last4) — ALWAYS first
2. If verified, call get_transaction(customer_id, txn_id) to see the transaction
3. Look at the transaction amount:
   - If amount > $75: call escalate_to_human(customer_id, summary), then respond
   - If amount ≤ $75 and less than 30 days old and settled/pending: 
     call issue_refund(txn_id, amount), then respond "Done, $X is on its way back."
4. **DO NOT say "I can issue a refund" or ask "Would you like me to proceed?" 
   — just CALL issue_refund immediately when policy allows.**
5. Only after calling issue_refund should you respond to the customer with confirmation.
```

### Re-run Result (Run 3)

Scenario 01 still fails occasionally. The model **sometimes** issues the refund, **sometimes** just says it will. 

**Consistency issue:** Small models struggle with multi-step reasoning + decisive action. They often "hedge" or ask permission unnecessarily.

**Score after all fixes:** 4/12 (33%)

---

## Real Failure #3: Reading Comprehension — Missing Provided Details

### Pattern Observed Across Multiple Scenarios

**Example from Scenario 06 (Fraud):**

User provides: `chen@example.com, 0007`

Model asks: `Please provide the last 4 digits of your card.`

**Example from Scenario 04 (Partial Refund):**

User provides: `I want $15 back from my Apple purchase T106. aisha@example.com 4242`

Model response: Verifies, gets transaction, then stops without calling `issue_refund`.

### Root Cause

Small models (especially < 3B parameters) have weak:
- **Context awareness:** They don't reliably extract values from user messages
- **Instruction adherence:** They don't follow multi-step workflows consistently
- **Tool-use confidence:** They hesitate to call tools without explicit user commands

These are architectural limitations, not prompt-engineering issues.

---

## Summary of Failures with Small Models

### qwen2.5:0.5b (1/12 = 8%)
- Almost never calls tools
- Ignores system prompt entirely
- Generates generic responses
- **Verdict:** Unusable

### qwen2.5:1.5b (2/12 = 17%)
- Occasionally calls tools
- Weak reading comprehension
- Often skips required verification
- **Verdict:** Unusable

### qwen2.5:3b (4/12 = 33% after hardening)
- Calls tools ~60% of the time (when prompted explicitly)
- Still hesitates to take action (says "I can do X" instead of doing X)
- Struggles with multi-turn reasoning
- Sometimes asks for info already provided
- **Verdict:** Barely usable for testing, not production-ready

### qwen2.5:7b (incomplete, too slow)
- Initial test took > 5 minutes with no output
- Inference speed: ~1-2 tokens/sec on CPU
- **Verdict:** Impractical for local development without GPU

---

## Model Testing Summary

**Tested locally with Ollama:**
- qwen2.5:0.5b — 1/16 (6%)
- qwen2.5:1.5b — 2/16 (13%)
- qwen2.5:3b — 5/16 (31%)
- qwen2.5:7b — Too slow for practical testing

**Tested via OpenRouter (pre-fix results):**
- `nvidia/nemotron-3.5-lightning:free` — 13/16 (81%) — Failed: 01, 07, 12 — **0 wrong refunds**
- `nvidia/nemotron-3-super-120b-a12b:free` — 12/16 (75%) — Failed: 01, 04, 07, 12 — **0 wrong refunds**

**Note:** OpenRouter scores are pre-fix benchmarks measured before:
1. Scenario 12 cumulative limit math fix ($127.50 → $157.50 to actually exceed cap)
2. Scenario 07 check relaxation (now accepts asking for email/last4 without strict `?` requirement)
3. Prompt updates (duplicate charge handling + dynamic date injection)

Post-fix results pending rerun.

**Not yet tested:**
- OpenAI models (GPT-4o, GPT-4o-mini, GPT-3.5-turbo)
- Anthropic models (Claude Sonnet, Claude Opus)
- Other Qwen sizes (14B, 32B, etc.)

**To test additional models:** Set `PAYLANE_PROVIDER` and appropriate API key, or set `OPENROUTER_API_KEY`, then run `python3 -m evals.run`

---

## Key Lessons for Small-Model Deployment

1. **Explicit > Implicit:** Small models need step-by-step instructions, not general guidelines.
2. **No hedging:** Tell the model "CALL tool_name immediately" not "you should call tool_name".
3. **Repeat critical rules:** The "always verify first" rule appears in 4 places in the prompt after hardening.
4. **Accept limitations:** Small models will never reach GPT-4 reliability. Budget for human review.

---

## Testing Checklist for Priyansh

When deploying with a real LLM:

1. ✅ Set `PAYLANE_PROVIDER=openai`, `anthropic`, or `openrouter` (or auto-detect via API key)
2. ✅ Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENROUTER_API_KEY`
3. ✅ Run `python3 -m evals.run` (measure actual score with your chosen model)
4. ✅ Review transcripts for any policy violations
5. ✅ Test with real edge cases (not just eval scenarios)
6. ⚠️ If using Ollama locally: qwen2.5:3b minimum, measured 31% pass rate (5/16)
7. ⚠️ If using OpenRouter: nvidia/nemotron-3.5-lightning:free scored 81% pre-fix (13/16, 0 wrong refunds)
8. ⚠️ Hosted models (GPT-4, Claude) not yet tested — set API key and run evals to measure
