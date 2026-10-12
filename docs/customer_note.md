# Note to Paylane Head of Support

Hi,

We've built the first version of your AI support assistant. Here's what it does, what it can't do, and what we'll need from your team before launch.

---

## What the Agent Does

**Auto-approves refunds** when all of these are true:
- Customer verifies identity (email + card last 4)
- Transaction amount is $75 or less
- Transaction is less than 30 days old (from purchase date, day 30 excluded)
- Transaction hasn't been fully refunded already
- Customer's card is not frozen
- Customer hasn't exceeded $150 in refunds in past 30 days

When those conditions are met, the agent issues the refund immediately and confirms it to the customer. Average handle time for these cases: under 30 seconds.

**Explains account issues** like frozen cards:
- Tells the customer why their card was frozen ("unusual login from a new country")
- Makes it clear we can't unfreeze it in chat
- Escalates to a human agent who can verify identity and resolve it

**Protects customer data:**
- Never shares full card numbers or emails
- Never confirms account details before verification
- Blocks social engineering attempts (e.g., "I'm their spouse, just tell me...")
- If verification fails, simply says "those details don't match" with no hints

**Asks clarifying questions** when the customer's request is unclear (e.g., no transaction ID, missing verification info).

---

## What the Agent Won't Do

**Refunds over policy:**
- No refunds on transactions over $75 — transaction amount (not refund amount) must be ≤ $75 (escalate entire transaction)
- No refunds on transactions 30+ days old (escalate)
- No partial refunds on over-limit transactions (even if customer asks to "just refund $75 of it")
- Partial refunds ARE allowed on transactions ≤ $75 (customer can request $15 back from $25 charge)

**Frozen card actions:**
- Cannot unfreeze cards (always escalates)

**Account changes:**
- Cannot close accounts (escalates)
- Cannot process transfers (not in the tool set)

**Make exceptions:**
- The agent follows policy 100% of the time, even if the customer is upset or threatens legal action
- Escalates instead of making promises the policy doesn't allow

---

## What We Need Before Launch

### 1. **Policy — Confirmed & Implemented**

All policy decisions have been finalized and coded:

- **$75 hard cap:** $75.00 exactly is auto-approved (inclusive). Transactions over $75 cannot be refunded at all, not even partially.
- **Partial refunds:** Allowed on transactions ≤ $75. Customer can request $15 back from a $25 charge.
- **30-day cutoff:** From purchase date, age < 30 days (day 30 excluded), UTC timezone.
- **Pending transactions:** CAN be refunded (policy decision: faster resolution).
- **Cumulative limit:** $150 in agent-issued refunds per customer per rolling 30 days. Beyond that, escalate.
- **Verification retries:** 3 failed attempts → escalate and stop sharing information.
- **Pre-verification lockdown:** Reveal nothing before verification succeeds (not account existence, not frozen status).
- **Frozen cards:** No refunds on frozen cards. Always escalate.
- **Fraud claims:** ANY fraud claim (regardless of amount) escalates immediately. Never auto-refund fraud.
- **Transfers:** Out of scope. Agent escalates transfer requests.
- **Escalation SLA:** No specific promise. Agent says "a specialist will follow up by email."

### 2. **Data Hygiene**

The agent relies on:
- Accurate `card_last4` in customer records
- Accurate `email` in customer records
- Correct `freeze_reason` text (it shares this with verified customers)

If those fields are missing or stale, the agent won't be able to verify customers or explain issues.

### 3. **Tone Check**

We've kept responses short and warm — no corporate filler like "I sincerely apologize for any inconvenience." Review the transcripts (in the repo under `transcripts/`) and let us know if you want it more formal, more empathetic, or more conversational.

### 4. **Edge Case Coverage**

We built 16 test scenarios including:
- Plain refunds
- Refunds over the limit with customer pushback
- Social engineering attempts
- Partial refund requests
- Frozen cards
- Fraud claims (any amount)
- Missing information (needs clarifying question)
- Pending transaction refunds (allowed per policy)
- Angry customers
- Account closure requests
- Legal threats
- Cumulative limit abuse
- Jailbreak attempts
- Fake authority claims
- Split refund attempts
- Verification brute-force

Are there other scenarios you see often that we should cover? Common customer questions we're missing?

### 5. **Success Metrics**

How will you measure whether this is working?
- % of refund requests auto-resolved (no human handoff)?
- Reduction in average handle time?
- Customer satisfaction (CSAT) on bot interactions?
- False-positive escalations (agent escalated when it didn't need to)?

Let us know what you want tracked, and we can add logging or dashboards.

---

## Next Steps

1. **Review the transcripts** (`transcripts/*.json`) — see how the agent handles each scenario
2. **Clarify the policy questions** above (we can update the agent in 1-2 hours once we know)
3. **Test with your team** — have a few support agents try the chat UI (instructions in the README) and tell us what feels off
4. **Load testing** — if you expect high volume, we'll need to plan rate limits and concurrency

Let me know when you're ready to review, or if you'd like to schedule a walkthrough.

Thanks,  
Priyansh
