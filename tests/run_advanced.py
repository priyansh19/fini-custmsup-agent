"""Run advanced challenging scenarios and identify failures."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests.advanced_scenarios import ADVANCED_CASES
from paylane.agent import Agent
from paylane.providers import from_env
from paylane.data import Store
import json

def run_scenario(case, provider_name="default"):
    """Run one scenario and return pass/fail with details."""
    store = Store()
    provider = from_env()
    agent = Agent(provider, store)
    
    turns = case.get('turns', [])
    if not isinstance(turns, list):
        turns = [turns]
    
    failures = []
    responses = []
    
    try:
        for turn in turns:
            response = agent.send(turn)
            responses.append(response)
        
        # Format result for check functions (same as live harness)
        result = {
            'replies': responses,
            'tool_calls': [
                {
                    'name': c[0],
                    'arguments': c[1],
                    'result': c[2]
                }
                for c in store.calls
            ]
        }
        
        # Run checks
        for check_fn in case.get('checks', []):
            passed, msg = check_fn(result)
            if not passed:
                failures.append(msg)
        
        return {
            'id': case['id'],
            'category': case['cat'],
            'passed': len(failures) == 0,
            'failures': failures,
            'tool_calls': [(c[0], c[1], c[2]) for c in store.calls],
            'responses': responses,
        }
    except Exception as e:
        import traceback
        return {
            'id': case['id'],
            'category': case['cat'],
            'passed': False,
            'failures': [f'Exception: {str(e)}', traceback.format_exc()],
            'tool_calls': [],
            'responses': responses,
        }

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Run advanced test scenarios')
    parser.add_argument('--category', help='Run only specific category')
    parser.add_argument('--limit', type=int, help='Limit number of tests')
    parser.add_argument('--output', help='Output JSON file')
    args = parser.parse_args()
    
    cases = ADVANCED_CASES
    if args.category:
        cases = [c for c in cases if c['cat'] == args.category]
    if args.limit:
        cases = cases[:args.limit]
    
    print(f"Running {len(cases)} advanced test cases...")
    print(f"Model: {os.getenv('OPENROUTER_MODEL', os.getenv('PAYLANE_MODEL', 'default'))}")
    print(f"Provider: {os.getenv('PAYLANE_PROVIDER', 'openrouter')}")
    print()
    
    results = []
    passed = 0
    failed = 0
    
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']} ({case['cat']})...", end=' ')
        result = run_scenario(case)
        results.append(result)
        
        if result['passed']:
            print("✓ PASS")
            passed += 1
        else:
            print(f"✗ FAIL: {', '.join(result['failures'])}")
            failed += 1
    
    print()
    print(f"Results: {passed}/{len(cases)} passed ({100*passed//len(cases)}%)")
    print(f"Failed: {failed}")
    
    # Group failures by category
    by_category = {}
    for r in results:
        cat = r['category']
        if cat not in by_category:
            by_category[cat] = {'total': 0, 'passed': 0, 'failed': 0}
        by_category[cat]['total'] += 1
        if r['passed']:
            by_category[cat]['passed'] += 1
        else:
            by_category[cat]['failed'] += 1
    
    print()
    print("By Category:")
    for cat, stats in sorted(by_category.items()):
        pct = 100 * stats['passed'] // stats['total'] if stats['total'] > 0 else 0
        print(f"  {cat:20s}: {stats['passed']}/{stats['total']} ({pct}%)")
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to {args.output}")
    
    # Print detailed failures
    print("\n" + "="*80)
    print("DETAILED FAILURES")
    print("="*80)
    for r in results:
        if not r['passed']:
            print(f"\n{r['id']} ({r['category']})")
            print(f"Failures: {r['failures']}")
            print(f"Tool calls: {len(r['tool_calls'])}")
            if r['tool_calls']:
                for name, args, result in r['tool_calls'][:3]:
                    print(f"  - {name}({args}) → {result}")
            if r['responses']:
                print(f"Last response: {r['responses'][-1][:200]}")

if __name__ == '__main__':
    main()
