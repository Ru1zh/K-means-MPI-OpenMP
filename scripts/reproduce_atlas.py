#!/usr/bin/env python3
"""Verify archived Atlas evidence and rerun its audits without MPI or an HPC login."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parent.parent


def verify_bundle(bundle):
    """Check archived logs, placement records and source packages byte for byte."""
    expected = {}
    for line in (bundle/'checksums.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or name in expected:
            raise ValueError('Invalid checksum entry: '+name)
        expected[name] = digest
        actual = bundle/name
        if not actual.is_file() or actual.is_symlink():
            raise ValueError('Missing or invalid evidence file: '+name)
        if hashlib.sha256(actual.read_bytes()).hexdigest() != digest:
            raise ValueError('Checksum mismatch: '+name)
    actual_names = {p.relative_to(bundle).as_posix() for p in bundle.rglob('*')
                    if p.is_file() and p.name != 'checksums.sha256'
                    and p.name != '.DS_Store' and not p.name.startswith('._')
                    and '__pycache__' not in p.parts}
    if actual_names != set(expected):
        raise ValueError('Evidence inventory differs from checksums: '+
                         ', '.join(sorted(actual_names ^ set(expected))))
    manifest = json.loads((bundle/'manifest.json').read_text())
    for kind, study in manifest['studies'].items():
        raw = bundle/study['directory']/study['raw_file']
        rows = [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]
        if len(rows) != study['records']:
            raise ValueError('Unexpected record count: '+kind)
    if sum(s['records'] for s in manifest['studies'].values()) != manifest['formal_records']:
        raise ValueError('Formal record total differs from manifest')
    return manifest, len(expected)


def audit_study(bundle, output, kind, study):
    """Restore the old flat layout in a new directory; originals stay intact."""
    work = output/kind
    work.mkdir()
    source = bundle/study['directory']
    result = work/source.name
    shutil.copytree(source, result)
    package = bundle/study['source_package']
    shutil.copy2(package, work/package.name)
    # Historical helpers keep these audits independent of later algorithm edits.
    helpers = ['atlas-hybrid-launch.py'] if kind == 'hybrid' else []
    if kind in ('threads', 'communication'):
        helpers = ['atlas-hybrid-launch.py', 'atlas-strategy-study.py', 'atlas-data-spec.json']
    with tarfile.open(package) as tar:
        for name in helpers:
            content = tar.extractfile('project3-atlas-%s/%s'%(kind, name)).read()
            (work/name).write_bytes(content)
    if kind in ('strong', 'hybrid'):
        command = [sys.executable, '-B', str(result/'analyze.py')]
    else:
        analyzer = work/'analyze-atlas-strategy-results.py'
        shutil.copy2(ROOT/'hpc'/analyzer.name, analyzer)
        command = [sys.executable, '-B', str(analyzer), str(result)]
    process = subprocess.run(command, cwd=work, text=True, capture_output=True)
    (work/'audit.stdout.txt').write_text(process.stdout)
    (work/'audit.stderr.txt').write_text(process.stderr)
    if process.returncode:
        raise ValueError('Audit failed for %s; see %s'%(kind, work/'audit.stderr.txt'))
    audit = json.loads((result/'analysis.audit.json').read_text())
    if audit['records'] != study['records'] or audit['numerical_check'] != 'pass':
        raise ValueError('Unexpected audit result: '+kind)
    return dict(study=kind, records=audit['records'], numerical_check=audit['numerical_check'],
                completeness=audit['completeness'], csv_recalculation=audit['csv_recalculation'],
                directory=str(result.relative_to(output)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT/'benchmarks/atlas')
    parser.add_argument('--verify-only', action='store_true', help='Check integrity without writing output')
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/atlas-audit',
                        help='New output directory for regenerated analyses')
    args = parser.parse_args()
    try:
        bundle = args.bundle.resolve()
        manifest, count = verify_bundle(bundle)
        print('Verified %d evidence files; %d formal records.'%(count, manifest['formal_records']))
        if args.verify_only:
            return
        output = args.output.resolve()
        if output == bundle or bundle in output.parents or output in bundle.parents:
            raise ValueError('Output must be outside the evidence bundle')
        if output.exists():
            raise ValueError('Output already exists; choose a new directory: '+str(output))
        output.mkdir(parents=True, exist_ok=False)
        audits = []
        for kind, study in manifest['studies'].items():
            audits.append(audit_study(bundle, output, kind, study))
            print('%s: %d records, audit passed.'%(kind, study['records']))
        (output/'summary.json').write_text(json.dumps(audits, indent=2)+'\n')
        print('Regenerated analyses: '+str(output))
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, 'Error: %s\n'%error)


if __name__ == '__main__':
    main()
