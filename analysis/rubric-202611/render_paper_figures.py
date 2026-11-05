#!/usr/bin/env python3
"""Regenerate report-size figures from the audited Vanda records (no new timing)."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from reproduce_rubric import verify_manifest
from rubric_analysis import read_runs, audit_records, summarize
from plot_rubric import plot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'paper-figures')
    parser.add_argument('--from-tables', type=Path,
                        help='redraw submitted aggregate CSV tables without claiming a raw-evidence audit')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; use a fresh directory')
    if args.from_tables:
        import csv
        def read_table(name):
            # CSV identity columns stay strings; all other nonempty columns are
            # the numeric summaries written by rubric_analysis.tables().
            strings = {'suite', 'variant', 'communication', 'run_id', 'job_id'}
            with (args.from_tables / name).open(newline='') as source:
                return [{key: (value if key in strings or value == '' else float(value))
                         for key, value in row.items()} for row in csv.DictReader(source)]
        rows, profiles = read_table('statistics.csv'), read_table('profiles.csv')
        print('Redrawing aggregate tables; raw-evidence audit not performed.')
    else:
        evidence = ROOT / 'benchmarks/rubric-202611'
        verify_manifest(evidence)
        rows, profiles = summarize(audit_records(*read_runs(evidence / 'runs')))
    plot(args.output, rows, profiles)
    print('Saved six report figures in PNG/PDF/SVG:', args.output)


if __name__ == '__main__':
    main()
