"""python -m api_test.contracts CURRENT [--baseline BASELINE] [--approvals JSON]."""
import argparse
import json
from pathlib import Path
from . import ContractError, load_file, lint, compare


def main():
    parser = argparse.ArgumentParser(description='Lint OpenAPI and block incompatible or review-required changes')
    parser.add_argument('current', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--approvals', type=Path, help='Reviewed JSON record bound to both document hashes')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        current = load_file(args.current)
        if args.approvals and not args.baseline:
            raise ContractError('--approvals requires --baseline')
        if args.baseline:
            approvals = json.loads(args.approvals.read_text()) if args.approvals else None
            result = compare(load_file(args.baseline), current, approvals)
        else:
            issues = lint(current)
            result = {'compatible': not any(item['severity'] == 'error' for item in issues), 'issues': issues}
        code = 0 if result['compatible'] else 1
    except (ContractError, OSError, ValueError, RecursionError):
        result = {'compatible': False, 'issues': [{'code': 'contract_input_error', 'severity': 'error', 'path': '#'}]}
        code = 2
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
