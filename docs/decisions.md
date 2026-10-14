# Design decisions (ADR log)

Each entry: date, context, decision, and why. **[From Deepak's brief]** marks rules the assignment set. **[Our addition]** marks choices we made. Policy is enforced in code (`paylane/policy.py`, gates in `paylane/agent.py`), and the prompt explains it to the model.

---

### ADR-01 · Refund rules · 2026-10-11 (rolling limit updated 2026-10-14)
- **$75 per charge** [From Deepak's brief]. A charge of $75.00 or less can be auto-refunded; exactly $75.00 is allowed. Anything above goes to a specialist, with no partial refund on charges over $75. That closes off "split refund" abuse.
- **Partial refunds on charges up to $75** [Our addition]. The total refunded per charge never exceeds the original amount.
- **$75 total per customer per rolling 30 days** [Our addition]. This counts every agent-issued refund in the window, and anything beyond it escalates. One $75 refund uses the whole allowance.
- **Pending transactions are refundable** [Our addition], for faster resolution.
- **Under 30 days old, day 30 excluded** [From Deepak's brief], counted from the transaction date. With `TODAY` = 2026-10-11, Sep 12 qualifies and Sep 11 doesn't.
- **No double refunds** [Our addition]. A fully refunded charge returns `already_refunded`.

### ADR-02 · Fraud, legal, closure, frozen cards · 2026-10-11
- **Any fraud claim goes to a human, at any amount** [From Deepak's brief, applied to all amounts]. A fraud claim sets a session flag in code (`FRAUD_RE`), and every refund in that chat is then blocked. A complaint like "your fees are a scam" is not a fraud claim (ADR-14).
- **Legal threats and account closure go to a human** [From Deepak's brief].
- **Frozen cards** [From Deepak's brief]. After verification the agent explains the freeze reason, never unfreezes, issues no refunds, and auto-escalates once.

### ADR-03 · Verification and lockout · 2026-10-11 (refined 2026-10-13)
- **Email plus card last 4 before any account detail** [From Deepak's brief]. Verification is done by the `verify_customer` helper [Our addition] and enforced in code.
- **Lockout after 3 failed attempts** [Our addition]. The chat stays locked even if correct details follow, and it auto-escalates.
- **Missing details don't count as an attempt** [Our addition]. An email with no card digits, or a prompt-injection line, gets a request for what's missing and doesn't use up a strike.
- **No identity switching mid-chat** [Our addition].

### ADR-04 · Closing the verification hole · 2026-10-11
An early run showed a model calling `get_customer` after failed attempts, reading `card_last4`, and then verifying itself. **Decision:** `get_customer` and `get_transaction` are blocked before verification, and `card_last4` is stripped from every result the model sees. Locked sessions refuse every account tool. [Our addition]

### ADR-05 · Resolution first · 2026-10-14
Support should solve the problem rather than just refund it [Our addition]. `get_transaction` returns resolution context: statement descriptor, recurring flag, `authorization_hold`, `related_txn` and a resolution note. Two code gates back this up:
- The **resolution gate** requires the fix to be offered in an earlier turn.
- The **reason gate** asks once what went wrong, and never blocks a second time.

Covered by scenarios 17–20 (descriptor, hotel hold, forgot-to-cancel, posted + pending duplicate).

### ADR-06 · Refund = cancellation, confirmed with a yes · 2026-10-14
A refund cancels what was bought: a subscription loses access, and an undelivered order is cancelled [Our addition]. The first `issue_refund` returns the exact consequence text. The refund only executes in a later turn after a clear yes; "no", "wait" or "keep it" blocks it. If the model states the consequence itself while naming the charge, that also counts as the notice.

### ADR-07 · Subscription proration · 2026-10-14
Cancelling on the day of the charge (day 0) gives a full refund. After that the refund is `amount × (period − days_used) / period`, rounded to cents (`subscription_max_refund`) [Our addition]. The per-charge cap, the rolling limit and the 30-day window still apply, and auto-renewals get no other special treatment. Examples: Headspace day 0 → $12.99; Adobe $59.99 on day 15 of 30 → $30.00.

### ADR-08 · Delivery check and proof · 2026-10-14
For an order, `check_delivery_status` must be called before any refund [Our addition]:
- `in_transit`: no refund; the agent offers to wait.
- `not_shipped`: the agent offers to wait, or cancels and refunds.
- `lost`: refund.
- `delivered`: the customer must describe proof it didn't arrive (carrier claim, photo, neighbour or police report). Otherwise a specialist follows up.

### ADR-09 · A 5th tool · 2026-10-14
`check_delivery_status(txn_id | order_id)` → `status, carrier, tracking, delivered_at, proof`, plus the order's refund eligibility [Our addition, at Priyansh's request]. It's scoped to the verified customer. The four tools from the brief keep their original signatures; `issue_refund` gains an optional `reason`.

### ADR-10 · Model: gpt-4o-mini via OpenRouter · 2026-10-12
**Decision:** `openai/gpt-4o-mini` through OpenRouter (`PAYLANE_PROVIDER=openrouter`) [Our addition].
- **Why:** reliable tool calling, low latency (a turn in roughly 2–6s, inside Vercel's 60s limit) and very low cost (a full 26-scenario eval costs a few cents).
- **Also evaluated:** local Qwen 2.5 (0.5b–7b via Ollama), which couldn't call tools reliably at small sizes, and NVIDIA Nemotron free tiers on OpenRouter (75–88% on the 16-scenario set).
- **Swappable:** the provider layer also supports OpenAI, Anthropic and a scripted model for tests.

### ADR-11 · Stateless HMAC-signed state, one Vercel deploy · 2026-10-12
Serverless instances share no memory, and an in-memory session could leak one visitor's verified chat to another. **Decision:** the whole conversation round-trips through the client as an HMAC-SHA256-signed blob (`api/chat.py`), and a tampered blob is rejected. Refund and ticket IDs come from the conversation's own store, so a cold start can't overwrite them. The frontend and API ship as one Vercel project (`vercel.json`: `@vercel/next` + `@vercel/python`) [Our addition].

### ADR-12 · Escalation wording without timelines · 2026-10-11 (hardened 2026-10-13)
The only promise is "a specialist will follow up by email" [Our addition]. `sanitize_reply` replaces any sentence that promises a timeframe ("soon", "within 24 hours", "as soon as possible", "business days") with that line. The prompt never offers a "manager".

### ADR-13 · Eval approach · 2026-10-11
Three layers [From Deepak's brief: own pass/fail checks and a score; the extra layers are Our addition]:
1. Scripted-model scenarios: deterministic, no key needed.
2. The same scenarios on real gpt-4o-mini, with the transcripts committed.
3. Live checks: a live HTTP harness, UI replays with screenshots, and an adversarial round.

Details in [evals.md](evals.md).

### ADR-14 · Adversarial hardening · 2026-10-13
After an angry-customer round [Our addition]:
- The timeline scrubber now replaces whole sentences, so replies are no longer garbled.
- "Scam" in a complaint is no longer treated as a fraud claim.
- Missing details no longer count as a failed attempt.
- The prompt has guidance for angry customers: acknowledge once, never argue, threats don't change policy.

### ADR-15 · Spend cap · 2026-10-12
OpenRouter spend is capped at $1 for the whole project [Our addition]. The live harness takes a budget baseline and a cap, and every run is sized to stay well under it.

### ADR-16 · Seed data · 2026-10-13
All demo customers are fictional, on the reserved `maplecrest.test` domain, with `PL-#####` customer IDs, `TXN-#####` transaction IDs and real-world merchants [Our addition]. Every policy edge has its own charge:
- $75.00 exactly and $75.01
- day 29, day 30 and day 31
- pending charges
- the $75 rolling limit (Spotify + Uniqlo)
- over-cap (Zara) and too-old (Netflix)
- holds and duplicates
- subscriptions on day 0 and day 15
- orders in each delivery state

`TODAY` is fixed, so age rules are deterministic.

### ADR-17 · Brief-only mode alongside the expanded mode · 2026-10-15
Brief-only mode runs Deepak's brief exactly. Expanded mode stays the default and is untouched, so the two can be compared directly, with their scores labelled separately.
- **Separate agent class.** `paylane/brief.py` (`BriefAgent`) is selected by `make_agent()` from `PAYLANE_POLICY_MODE`, or per request with `policy_mode`. The expanded `Agent` and its gates are byte-for-byte unchanged, so its 26/26 real-model result still describes it. The mode is stored in the HMAC-signed state, so one conversation never mixes policies.
- **Refund rules [From Deepak's brief].** In order: verified → owns the transaction → card not frozen → no refund ever issued on the transaction → not pending → amount equals the full transaction amount → original transaction amount ≤ $75 → under 30 days. Any failure blocks `issue_refund` in code (`brief_refund_allowed`). The $75 test always uses the original amount, so asking for $50 of a $120 charge is still a partial request and still over the limit.
- **Only the 4 spec tools.** The brief's API has no verification endpoint, so verification happens inside `get_customer`: code checks the email the model looks up against the card last 4 the customer typed in chat. The answer is the same whether the email exists or not, and `card_last4` never reaches the model.
- **Escalations [From Deepak's brief].** Over $75, 30+ days, frozen card (auto-escalated on verification), legal action, fraud over $500 and account closure all go to a human. Replies keep the "A specialist will follow up by email" wording; the shared sanitiser removes any timeline.
- **Interpretations, labelled.** The 3-strike lockout is kept as part of "verify before discussing any account detail". A fraud claim of any size is not auto-refunded, which keeps refunds within "never promise things the policy doesn't allow".
- **Not in this mode.** The rolling $75 cap, subscription proration, refund-as-cancellation with a yes, delivery proof with `check_delivery_status`, pending refunds, partial refunds and the resolution-first gates. All of them remain in expanded mode, each marked [Our addition].
- **UI.** The help page has a Brief-only / Expanded toggle (also `?mode=brief`), a mode badge in the nav and the chat header, a brief policy panel listing every rule plus the 4 tools, 12 scenario cards (one per brief rule, each tagged with its rule) and a live tool-call trace in the chat.
- **Evaluation.** 22 scripted brief scenarios and 40 brief unit tests, offline only (no paid model runs for this mode).
