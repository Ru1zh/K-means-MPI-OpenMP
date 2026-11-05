#!/usr/bin/env python3
"""Offline completeness/checksum audit, exact tables, and optional rubric plots."""
import argparse
import hashlib
import json
from pathlib import Path
from rubric_analysis import ROOT, SUITES, read_runs, audit_records, tables


def verify_manifest(root):
    manifest_path = root / 'evidence-sha256.json'
    if not manifest_path.is_file():
        raise ValueError('Missing evidence-sha256.json: seal the complete evidence archive first')
    expected = json.loads(manifest_path.read_text())
    actual = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (root / 'runs').rglob('*') if p.is_file()}
    if expected != actual or not actual:
        raise ValueError('Evidence checksum mismatch (missing, altered or additional files)')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, default=ROOT / 'benchmarks/rubric-202611')
    p.add_argument('--output', type=Path, default=ROOT / 'artifacts/rubric-analysis')
    p.add_argument('--status', action='store_true')
    p.add_argument('--seal', action='store_true', help='audit before creating immutable evidence checksums')
    p.add_argument('--verify-only', action='store_true')
    p.add_argument('--tables-only', action='store_true')
    a = p.parse_args()
    if a.status:
        for suite in SUITES:
            files = list((a.input / 'runs').rglob('raw.jsonl'))
            count = 0
            for file in files:
                count += sum(json.loads(line).get('suite') == suite for line in file.read_text().splitlines() if line.strip())
            print('%s: %d ordinary records' % (suite, count))
        print('Expected: 275 ordinary + 75 independent profile records; zero means pending HPC.')
        return
    if not a.seal:
        verify_manifest(a.input)
    rows, layouts = read_runs(a.input / 'runs')
    groups = audit_records(rows, layouts)
    if a.seal:
        evidence = {str(p.relative_to(a.input)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (a.input / 'runs').rglob('*') if p.is_file()}
        with (a.input / 'evidence-sha256.json').open('x') as f:
            json.dump(evidence, f, indent=2, sort_keys=True)
            f.write('\n')
    if not a.verify_only:
        ordinary, profiles = tables(a.output, groups)
        if not a.tables_only:
            from plot_rubric import plot
            plot(a.output, ordinary, profiles)
    print('Verified: 275 ordinary records + 75 independent diagnostics; six complete same-job comparisons.')


if __name__ == '__main__':
    main()
