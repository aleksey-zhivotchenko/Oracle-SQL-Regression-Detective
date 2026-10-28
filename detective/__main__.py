import argparse
import json
import sys
import time
from pathlib import Path
from . import analyzer, fixtures, oracle, report
from .model import InputError, read_json, write_json


def parser():
    p = argparse.ArgumentParser(description='Oracle SQL Regression Detective — local, read-only capture and analysis')
    commands = p.add_subparsers(dest='command', required=True)
    f = commands.add_parser('fixtures', help='Generate explicitly synthetic baseline/comparison/recovery captures')
    f.add_argument('--output', required=True)
    a = commands.add_parser('analyze', help='Compare two saved workload windows')
    a.add_argument('--captures', required=True)
    a.add_argument('--comparison-label', choices=['comparison', 'recovery'], default='comparison')
    a.add_argument('--output', required=True)
    a.add_argument('--min-executions', type=int, default=10)
    a.add_argument('--min-slowdown-ratio', type=float, default=2.0)
    a.add_argument('--min-avg-increase-s', type=float, default=0.05)
    a.add_argument('--top-n', type=int, default=5)
    for name in ('preflight', 'capture'):
        c = commands.add_parser(name, help='Verify Oracle access' if name == 'preflight' else 'Capture one workload boundary')
        c.add_argument('--schema', required=True)
        c.add_argument('--sql-id', required=True, action='append', dest='sql_ids')
        c.add_argument('--non-interactive', action='store_true')
        if name == 'capture':
            c.add_argument('--label', required=True, choices=['baseline', 'comparison', 'recovery'])
            c.add_argument('--edge', required=True, choices=['start', 'end'])
            c.add_argument('--output', required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    start = time.perf_counter()
    try:
        if args.command == 'fixtures':
            fixtures.generate(args.output)
            print('Generated 6 SYNTHETIC fixture snapshots. No Oracle connection was used.')
        elif args.command == 'analyze':
            root = Path(args.captures)
            snapshots = [read_json(root / f'{label}-{edge}.json')
                         for label in ('baseline', args.comparison_label) for edge in ('start', 'end')]
            result = analyzer.analyze(snapshots, **{k: getattr(args, k) for k in analyzer.DEFAULTS})
            report.save(result, args.output)
            print(json.dumps(dict(source=result['source'], summary=result['summary'],
                                  elapsed_seconds=round(time.perf_counter() - start, 4),
                                  output=str(Path(args.output).resolve()))))
        else:
            oracle.selection(args.schema, args.sql_ids)
            destination = None
            if args.command == 'capture':
                destination = Path(args.output) / f'{args.label}-{args.edge}.json'
                if destination.exists():
                    raise InputError('Capture already exists; use a new output directory to preserve evidence.')
            with oracle.connect(non_interactive=args.non_interactive) as connection:
                if args.command == 'preflight':
                    print(json.dumps(oracle.preflight(connection, args.schema, args.sql_ids), indent=2))
                else:
                    snapshot = oracle.capture(connection, args.schema, args.sql_ids, args.label, args.edge)
                    write_json(destination, snapshot)
                    print(f'Captured {len(snapshot["rows"])} child cursors to {destination}.')
                    if not snapshot['rows']:
                        print('Warning: no selected SQL found; analysis will report insufficient data.')
        return 0
    except (InputError, oracle.OracleError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 2
    except OSError:
        print('Error: local file operation failed. Check paths and permissions.', file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print('Cancelled; no credentials saved.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
