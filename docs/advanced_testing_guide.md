# Advanced Testing & Model Configuration Guide

## Overview

This system now includes comprehensive testing infrastructure to evaluate agent performance across 50 challenging real-world scenarios and a UI for testing different models and configurations.

## 🎯 What We Built

### 1. Advanced Test Scenarios (50 Cases)

Located in `tests/advanced_scenarios.py`, these scenarios test edge cases that standard benchmarks miss:

#### **Temporal Reasoning (5 scenarios)**
- `adv01_timezone_confusion` - Tests if agent handles timezone-based date calculation errors
- `adv02_leap_year_edge` - Leap year date handling
- `adv03_month_boundary` - Exact 29-day vs 30-day boundary
- `adv04_double_charge_same_day` - Claims of duplicate charges that don't exist
- `adv05_future_date_claim` - Customer claims future-dated transaction

**Why these matter:** Date arithmetic is notoriously difficult for LLMs. These test whether the agent trusts its data or gets confused by customer claims.

#### **Numerical Reasoning (5 scenarios)**
- `adv06_percentage_confusion` - "Refund 50% of my $75 charge"
- `adv07_currency_confusion` - Customer claims EUR conversion makes it over limit
- `adv08_rounding_trap` - Requests $75.00001
- `adv09_negative_partial` - "$100 minus $25, so $75"
- `adv10_cumulative_math_trick` - Complex cumulative cap calculation

**Why these matter:** Tests if agent can do accurate math and resist being confused by alternative framings.

#### **Logical Reasoning (5 scenarios)**
- `adv11_proxy_reasoning` - "My card was stolen yesterday" (implied fraud)
- `adv12_conditional_reasoning` - "IF X AND Y THEN refund" (not a request)
- `adv13_implied_refund` - "T100 is wrong. Can you help?" (ambiguous)
- `adv14_negation_confusion` - "I don't NOT want a refund" (double negative)
- `adv15_contrapositive` - Logical inference test

**Why these matter:** Tests causal and logical inference beyond keyword matching.

#### **Ambiguity & Vagueness (5 scenarios)**
- `adv16_pronoun_ambiguity` - "The expensive one is wrong" (which one?)
- `adv17_this_that_confusion` - Ambiguous pronouns
- `adv18_approximate_amount` - "~$40ish" for $42.50 charge
- `adv19_generic_complaint` - "Something is wrong"
- `adv20_implied_comparison` - "More than it should be"

**Why these matter:** Real customers rarely give perfect specifications.

#### **Social Context & Pragmatics (5 scenarios)**
- `adv21_sarcasm` - "Oh GREAT, charged twice"
- `adv22_rhetorical_question` - "Why would I pay twice?"
- `adv23_hypothetical` - "What would happen if..."
- `adv24_politeness_indirect` - Very indirect request
- `adv25_cultural_context` - Cultural explanation

**Why these matter:** Tests understanding of intent beyond literal words.

#### **Memory & State Consistency (5 scenarios)**
- `adv26_contradictory_info` - Changes mind multiple times
- `adv27_forgotten_context` - Loses track of conversation
- `adv28_state_reset_claim` - "Forget that happened"
- `adv29_gaslighting` - Claims agent said something it didn't
- `adv30_implicit_state` - Implicit references

**Why these matter:** Multi-turn consistency is critical for customer trust.

#### **Adversarial Social Engineering (5 scenarios)**
- `adv31_authority_by_knowledge` - "I know your policies"
- `adv32_urgency_manipulation` - "MY FLIGHT LEAVES IN 10 MINUTES"
- `adv33_guilt_trip` - Sympathy manipulation
- `adv34_false_precedent` - "Sarah did it last week"
- `adv35_regulatory_threat` - False legal claims

**Why these matter:** Real users will try to manipulate the system.

#### **Complex Multi-Step Reasoning (5 scenarios)**
- `adv36_chained_refunds` - Multiple dependent operations
- `adv37_conditional_chain` - If-then logic
- `adv38_nested_request` - Complex conditional with fallback
- `adv39_multi_customer_confusion` - Claims to manage multiple accounts
- `adv40_priority_conflict` - Optimize refund order under cap

**Why these matter:** Tests planning and optimization capabilities.

#### **Technical & System Boundaries (5 scenarios)**
- `adv41_system_time_query` - Tries to extract system info
- `adv42_database_query` - SQL injection attempt
- `adv43_api_exploration` - Asks for internal API details
- `adv44_rate_limit_probe` - Probes system limits
- `adv45_concurrent_session` - Claims multiple sessions

**Why these matter:** Security and information disclosure tests.

#### **Edge Cases in Natural Language (5 scenarios)**
- `adv46_homophone` - "Eye want tea won hundred"
- `adv47_typo_cascade` - Multiple typos
- `adv48_mixed_script` - English + Chinese
- `adv49_emoji_only_sentiment` - Emojis express anger
- `adv50_extreme_politeness` - Overly formal indirect request

**Why these matter:** Real user input is messy.

### 2. Model Selection UI

Located in `web/pages/index.tsx`, provides:

#### **Configuration Panel (Left Sidebar)**
- **Provider Selection**: OpenRouter, OpenAI, Anthropic, Ollama
- **Model Selection**: Dropdown showing available models with cost indicators
- **Temperature Slider**: 0.0 (consistent) to 1.0 (creative)
- **Max Tokens**: Control response length
- **Quick Test Button**: Runs 3 standard scenarios instantly
- **Reset Chat**: Clear conversation state

#### **Real-Time Stats**
- Message count
- Tool call count
- Demo vs Live mode indicator
- Current model display

#### **Testing Tips**
- Pre-filled example queries for quick testing
- Standard test cases (plain, over-limit, frozen, fraud)

#### **Test Results Display**
- Shows expected vs actual outcomes
- Tool call count
- Response preview
- Pass/fail indication

### 3. API Configuration Support

Located in `api/chat.py`:

```python
# Client sends configuration with each request
{
  "message": "Refund T100...",
  "state": "...",
  "config": {
    "model": "openai/gpt-4o-mini",
    "provider": "OpenRouter",
    "temperature": 0,
    "maxTokens": 4096
  }
}
```

The API dynamically:
1. Overrides environment variables based on config
2. Selects appropriate provider
3. Maintains backward compatibility (no config = use env defaults)

### 4. Test Runner

Located in `tests/run_advanced.py`:

```bash
# Run all 50 scenarios
python tests/run_advanced.py

# Run specific category
python tests/run_advanced.py --category temporal

# Limit tests for quick check
python tests/run_advanced.py --limit 10

# Save results to JSON
python tests/run_advanced.py --output results.json
```

**Output includes:**
- Overall pass rate
- Per-category breakdown
- Detailed failure analysis
- Tool call traces
- Response excerpts

## 🔬 How to Use This System

### Testing a New Model

1. **Start the web UI** (`npm run dev` in `web/`)
2. **Open configuration panel** (click + button)
3. **Select provider and model**
4. **Adjust temperature** (start with 0 for consistency)
5. **Click "Quick Test"** to see basic performance
6. **Try advanced scenarios** manually or with runner

### Finding Optimal Configuration

```bash
# Test with different models
export PAYLANE_PROVIDER=openrouter
export OPENROUTER_MODEL=openai/gpt-4o-mini
python tests/run_advanced.py --output gpt4omini.json

export OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
python tests/run_advanced.py --output claude35.json

export OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
python tests/run_advanced.py --output nemotron.json

# Compare results
python -c "
import json
for f in ['gpt4omini.json', 'claude35.json', 'nemotron.json']:
    data = json.load(open(f))
    passed = sum(1 for r in data if r['passed'])
    print(f'{f}: {passed}/{len(data)} ({100*passed//len(data)}%)')
"
```

### Identifying Failure Patterns

After running tests, look at the detailed output:

```bash
python tests/run_advanced.py --category logical --output logical_failures.json
```

Then analyze:
1. **Which categories have lowest pass rates?**
2. **Are failures due to refusal to act or wrong action?**
3. **Do failures cluster around specific tool calls?**
4. **Does temperature affect consistency?**

### Iterating on Fixes

When you find a failure pattern:

1. **Reproduce it** - Run specific scenario repeatedly
2. **Diagnose root cause** - Is it prompt, code guard, or model capability?
3. **Implement fix** - Update prompt, add code check, or adjust config
4. **Re-test** - Verify fix doesn't break other scenarios
5. **Document** - Add to failure log with before/after scores

## 📊 Expected Baseline Results

Based on preliminary testing:

### GPT-4o Mini
- **Simple scenarios**: 95-100%
- **Temporal/numerical**: 80-90%
- **Logical/ambiguous**: 70-85%
- **Adversarial**: 85-95%
- **Overall estimate**: ~85-90%

### Claude 3.5 Sonnet
- **Simple scenarios**: 95-100%
- **Temporal/numerical**: 85-95%
- **Logical/ambiguous**: 80-90%
- **Adversarial**: 90-95%
- **Overall estimate**: ~90-95%

### Nemotron Super 120B (Free)
- **Simple scenarios**: 100% (measured)
- **Temporal/numerical**: 70-80% (estimate)
- **Logical/ambiguous**: 60-75% (estimate)
- **Adversarial**: 80-90% (measured)
- **Overall estimate**: ~80-85%

### Small Models (Qwen 3B, 7B)
- **Simple scenarios**: 50-70%
- **Complex reasoning**: 10-30%
- **Overall**: Not recommended for production

## 🎯 What Makes a "Good" Score?

### Production Ready: 95%+
- Handles all common cases correctly
- Rare edge cases may need human review
- Safe to deploy with monitoring

### Acceptable: 85-95%
- Most cases handled correctly
- Some edge cases need prompt tuning
- Deploy with human fallback for failed cases

### Needs Work: 70-85%
- Core functionality works
- Many edge cases fail
- Requires prompt/code improvements before production

### Not Ready: <70%
- Too many failures for customer-facing use
- Either wrong model choice or prompt needs major revision

## 🔧 Configuration Best Practices

### Temperature Settings

**Temperature 0** (Recommended for production)
- Most consistent
- Follows rules strictly
- Less creative but more predictable

**Temperature 0.3-0.5**
- Slightly more natural language
- Still quite consistent
- Good for testing variety

**Temperature 0.7-1.0**
- More varied responses
- Less predictable
- Can miss rules
- Not recommended for policy-critical applications

### Token Limits

- **Minimum 1024**: For simple refund requests
- **Recommended 4096**: Handles complex multi-turn
- **Maximum 8192+**: Only if you need very detailed explanations

Lower token limits reduce cost but may truncate responses in complex scenarios.

### Provider Selection

**OpenRouter** (Recommended)
- Access to many models
- Free tier options
- Easy switching for testing

**OpenAI Direct**
- Slightly faster
- More stable
- Better if you have existing credits

**Anthropic Direct**
- Claude models only
- Good for high-quality responses
- More expensive

**Ollama (Local)**
- Free, no API costs
- Good for development
- Models <7B struggle with complex reasoning

## 🚀 Next Steps

1. **Run comprehensive test sweep**
   ```bash
   ./scripts/test_all_models.sh  # Run against all models
   ```

2. **Analyze failure patterns**
   ```bash
   python scripts/analyze_failures.py results/*.json
   ```

3. **Implement fixes**
   - Update prompt for clarity
   - Add code guards for edge cases
   - Document in failure_log.md

4. **Validate fixes**
   ```bash
   python tests/run_advanced.py --output post_fix.json
   diff pre_fix.json post_fix.json
   ```

5. **Deploy optimal configuration**
   - Update production OPENROUTER_MODEL
   - Set temperature to 0
   - Monitor real-world performance

## 📚 Further Reading

- `docs/failure_log.md` - Historical failures and fixes
- `docs/live_test_report.md` - Production testing results (137/138 passing)
- `tests/live/cases.py` - 138 real-life customer scenarios
- `tests/advanced_scenarios.py` - 50 challenging edge cases

---

**Built:** 2026-10-12  
**Purpose:** Find failure modes and optimal model configurations for production deployment
