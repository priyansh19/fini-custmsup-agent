# Architecture

One Vercel project serves the Next.js frontend and the Python API. The agent, the policy engine and the mock bank are Python modules inside the API functions. Each part has its own module and a narrow interface, so any of them can become a separate service later without touching the others.

Tags: **[From Deepak's brief]** = required by the assignment. **[Our addition]** = a design choice we made.

## 1. System and service split

```mermaid
flowchart LR
  subgraph Browser
    HELP["Help page + messenger (/)<br/>scenario cards, persona picker"]
    ADMIN["Developer / evaluator view (/admin)<br/>tool calls, model settings"]
  end

  subgraph Vercel["Vercel (single deploy)"]
    subgraph Web["Next.js (@vercel/next)"]
      HELP
      ADMIN
    end
    subgraph API["Python functions (@vercel/python, 60s max)"]
      CHAT["/api/chat"]
      HEALTH["/api/health"]
      SCEN["/api/scenarios"]
    end
    subgraph Agent["Agent service (paylane/agent.py, prompt.py)"]
      LOOP["Tool-calling loop<br/>session note, 42s turn budget"]
      GATES["Code gates<br/>verify · resolution · reason ·<br/>delivery · cancellation"]
    end
    POLICY["Policy engine (paylane/policy.py)<br/>$75 per charge · &lt;30 days ·<br/>$75 rolling / 30 days · proration"]
    subgraph Tools["Mock tool service (paylane/tools.py, data.py)"]
      T1["get_customer"]
      T2["get_transaction"]
      T3["issue_refund"]
      T4["escalate_to_human"]
      T5["check_delivery_status<br/>[Our addition]"]
    end
  end

  LLM["LLM provider: OpenRouter<br/>openai/gpt-4o-mini"]

  HELP -- "message + signed state" --> CHAT
  ADMIN --> CHAT
  HELP --> SCEN
  CHAT -- "verify HMAC, rebuild Agent" --> LOOP
  LOOP <--> LLM
  LOOP --> GATES --> POLICY
  GATES --> Tools
  CHAT -- "reply + new HMAC-signed state" --> HELP
```

| Layer | Code | Notes |
|---|---|---|
| Frontend | `web/pages/index.tsx`, `web/pages/admin.tsx` | **[Our addition]** Branded help page with a messenger, plus a separate developer view for evaluators. |
| API | `api/chat.py`, `api/health.py`, `api/scenarios.py` | `/api/chat` is stateless. The whole conversation round-trips as an HMAC-SHA256-signed blob (`sign_state` / `verify_state`), so serverless instances share nothing and a tampered blob is rejected. |
| Agent service | `paylane/agent.py`, `paylane/prompt.py` | LLM ↔ tool loop (max 8 steps, 42s budget), code gates, and reply sanitising (no follow-up timelines). |
| Policy engine | `paylane/policy.py` | Deterministic. Runs before every refund executes, so the LLM can't override it. |
| Mock tool service | `paylane/tools.py`, `paylane/data.py` | **[From Deepak's brief]** 4 tools. **[Our addition]** `check_delivery_status`, plus a `verify_customer` helper. Seeded fictional data, with `TODAY = 2026-10-11`. |
| LLM provider | `paylane/providers.py` | OpenRouter (production), OpenAI, Anthropic, Ollama, and a scripted provider for tests. Per-call timeout, fast backoff, overall deadline, and tolerant parsing of tool JSON. |

## 2. One chat turn

```mermaid
sequenceDiagram
  autonumber
  participant U as Customer (messenger)
  participant API as /api/chat
  participant A as Agent loop
  participant L as gpt-4o-mini (OpenRouter)
  participant G as Gates + policy
  participant T as Mock tools

  U->>API: POST {message, state}
  API->>API: verify HMAC on state (reject if tampered)
  API->>A: rebuild Agent from state, send(message)
  loop up to 8 steps within 42s
    A->>L: system prompt + session note + messages + tool specs
    L-->>A: text or tool_calls
    alt tool call
      A->>G: check (verification, gates, policy)
      G->>T: execute only if allowed
      T-->>A: result (or blocked reason + instruction)
    else final text
      A->>A: sanitize reply (no timelines), record cancellation notice
    end
  end
  A-->>API: reply, tool_calls, new state
  API-->>U: {reply, tool_calls, state: signed}
  Note over U,API: On a provider error the API returns a friendly error and keeps the previous state, so the customer can resend.
```

## 3. Refund gate (`issue_refund`)

Every refund goes through these checks in order. The first one that fails returns a blocked result with an instruction, which the model passes on to the customer.

```mermaid
flowchart TD
  S([issue_refund requested]) --> V{Customer verified?<br/>not locked, no fraud claim}
  V -- no --> X1[Blocked: verify first /<br/>locked / fraud → specialist]
  V -- yes --> R{Charge has a resolution note?<br/>descriptor, hold, duplicate, subscription}
  R -- "yes, fix not yet offered" --> X2[resolution_first:<br/>explain the fix, ask if it solves it]
  R -- "no / fix offered earlier" --> Q{Customer said what went wrong?}
  Q -- "no, first attempt" --> X3[ask_reason_first:<br/>ask once; never blocks twice]
  Q -- yes --> D{Is it an order?}
  D -- yes --> DC{check_delivery_status called?}
  DC -- no --> X4[check_delivery_status_first]
  DC -- in_transit --> X5[No refund: offer to wait]
  DC -- "delivered, no proof described" --> X6[Ask for proof;<br/>none → escalate]
  DC -- "lost / not_shipped / delivered + proof" --> P
  D -- no --> P{Policy engine}
  P -- "> $75 charge, 30+ days old, frozen card,<br/>already refunded, or $75 rolling limit hit" --> X7[Escalate to specialist]
  P -- ok --> PR{Subscription?}
  PR -- yes --> PR2{Amount ≤ prorated max?<br/>day 0 = full, then unused days}
  PR2 -- no --> X8[exceeds_prorated_max]
  PR2 -- yes --> C
  PR -- no --> C{Cancellation notice given in an earlier turn<br/>and customer said yes?}
  C -- "no notice yet" --> X9[confirm_cancellation_first:<br/>'Refunding $X will cancel …. Go ahead?']
  C -- "notice, no clear yes" --> X10[awaiting confirmation]
  C -- yes --> OK([issue_refund executes ✓])
```

## 4. Verification and lockout

```mermaid
stateDiagram-v2
  [*] --> Unverified
  Unverified --> Unverified: missing email or card digits<br/>(asks again, not counted)
  Unverified --> Verified: email + card last 4 match
  Unverified --> Failed1: details don't match
  Failed1 --> Verified: match
  Failed1 --> Failed2: no match
  Failed2 --> Verified: match
  Failed2 --> Locked: 3rd failed attempt
  Locked --> Locked: any details (even correct)<br/>nothing revealed
  Locked --> [*]: auto-escalated:<br/>a specialist follows up by email
  Verified --> FrozenEscalated: card is frozen
  FrozenEscalated --> [*]: reason explained, no refunds,<br/>auto-escalated
  Verified --> [*]: chat continues; identity can't switch mid-chat
```

Before verification the agent reveals nothing: not whether the account exists, not the card status, not any transaction. `get_customer` and `get_transaction` are blocked in code until verification, and `get_customer` never returns `card_last4` to the model.
