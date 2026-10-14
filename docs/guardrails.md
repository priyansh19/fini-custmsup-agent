# Guardrails

Rules are enforced in **code**, and the prompt explains them so the model words things well. A model that ignores the prompt still can't refund against policy.

| # | Guardrail | Where | Source |
|---|---|---|---|
| 1 | Verify email + card last 4 before any account detail; `get_customer`/`get_transaction` blocked until verified | `paylane/agent.py` `_run_tool_inner` (verify / get_customer / get_transaction branches) | [From Deepak's brief] |
| 2 | `card_last4` never returned to the model | `agent.py` get_customer branch | [Our addition] |
| 3 | Lockout after 3 failed attempts; stays locked; auto-escalates once | `agent.py` verify branch, `_auto_escalate`; `policy.py` `MAX_FAILED_VERIFICATIONS` | [Our addition] |
| 4 | Missing details aren't counted as an attempt (`missing_credentials`) | `agent.py` verify branch | [Our addition] |
| 5 | No identity switching mid-chat | `agent.py` verify branch (`already_verified_as_another_customer`) | [Our addition] |
| 6 | Lookups scoped to the verified customer (transactions and deliveries) | `agent.py` get_transaction / check_delivery_status branches; `tools.py` | [Our addition] |
| 7 | $75 per-charge cap, including partials | `policy.py` `AUTO_LIMIT`, `refund_allowed` | [From Deepak's brief] |
| 8 | Under 30 days, day 30 excluded | `policy.py` `MAX_AGE_DAYS` | [From Deepak's brief] |
| 9 | $75 total per customer per rolling 30 days | `policy.py` `CUMULATIVE_REFUND_CAP`, `get_cumulative_refunds_rolling` | [Our addition] |
| 10 | No double refund; partial total ≤ the charge | `policy.py` `refund_allowed`; `tools.py` `issue_refund` | [Our addition] |
| 11 | Frozen card: explain, no refunds, auto-escalate | `policy.py` (`frozen_card_escalate`); `agent.py` verify branch | [From Deepak's brief] |
| 12 | Any fraud claim blocks refunds for the whole chat and escalates | `agent.py` `FRAUD_RE`, `send()` | [From Deepak's brief, applied to all amounts] |
| 13 | Eligible refunds aren't wrongly escalated (exactly $75, day 29) | `agent.py` `_wrongful_policy_escalation` | [Our addition] |
| 14 | Resolution first: offer the known fix before refunding | `agent.py` `_resolution_gate` | [Our addition] |
| 15 | Ask once what went wrong; never block a second time | `agent.py` `_reason_gate` | [Our addition] |
| 16 | Orders: delivery check first; no refund in transit; delivered needs a proof description, otherwise escalate | `agent.py` `_delivery_gate`, `PROOF_RE` | [Our addition] |
| 17 | Subscription proration (day 0 full, then unused days) | `policy.py` `subscription_max_refund` | [Our addition] |
| 18 | Refund = cancellation: consequence stated, then a clear yes | `agent.py` `_cancellation_gate`, `AFFIRM_RE` / `NEGATE_RE`, notice capture in `send()` | [Our addition] |
| 19 | No follow-up timelines; only "a specialist will follow up by email" | `agent.py` `sanitize_reply`, `TIMELINE_RE`, `SOFT_TIMELINE_RE` | [Our addition] |
| 20 | Transaction IDs normalised ("txn 58306", "58306" → `TXN-58306`) | `agent.py` `normalize_txn_id` | [Our addition] |
| 21 | Prompt-injection resistance: rules live in code; system prompt never revealed | `agent.py` gates; `prompt.py` | [Our addition] |
| 22 | Tampered conversation state rejected | `api/chat.py` `sign_state` / `verify_state` (HMAC-SHA256) | [Our addition] |
| 23 | Reliability: 8 steps, 42s turn budget, provider timeout, backoff and deadline; tool errors returned as results; on failure the previous state is kept | `agent.py` `MAX_STEPS`, `TURN_BUDGET_S`, `_run_tool`; `providers.py` | [Our addition] |
| 24 | Input cap of 4,000 characters | `agent.py` `MAX_USER_CHARS` | [Our addition] |

Each gate has unit tests in `tests/test_guardrails_v2.py` and `tests/test_policy.py`.
