#!/usr/bin/env python3
"""Verify retained P=2 evidence and rerun its frozen analyzer on a new copy."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from reproduce_atlas import verify_bundle

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ('thread-scaling-summary.csv', 'phase-summary.csv', 'analysis.audit.json',
           'analysis.md')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(bundle):
    inventory, count = verify_bundle(bundle)
    manifest = inventory['studies']['thread-scaling']
    run = bundle / manifest['directory']
    package = bundle / manifest['source_package']
    if digest(package) != manifest['source_package_sha256']:
        raise ValueError('Source package checksum differs')
    if (run / 'status.txt').read_text().strip() != 'exit_status=0':
        raise ValueError('Recorded in-job exit status is not zero')
    with tarfile.open(package) as tar:
        prefix = 'project3-atlas-thread-scaling/'
        for line in (run / 'source-manifest.sha256').read_text().splitlines():
            checksum, name = line.split('  ', 1)
            member = tar.getmember(prefix + name)
            if not member.isfile() or hashlib.sha256(tar.extractfile(member).read()).hexdigest() != checksum:
                raise ValueError('Submitted source differs: ' + name)
        if tar.extractfile(prefix + 'source-manifest.sha256').read() != (run / 'source-manifest.sha256').read_bytes():
            raise ValueError('Source manifest differs from submitted package')
    for mode in ('timing', 'profile'):
        rows = [json.loads(x) for x in (run / (mode + '.jsonl')).read_text().splitlines() if x.strip()]
        if len(rows) != manifest[mode + '_records']:
            raise ValueError('Unexpected record count: ' + mode)
        binary_hashes = dict((name, checksum) for checksum, name in
                             (line.split('  ', 1) for line in (run / 'binaries.sha256').read_text().splitlines()))
        if any(row['binary_sha256'] != binary_hashes['build/kmeans_mpi'] for row in rows):
            raise ValueError('Measurement executable hash differs from recorded build hash')
    return manifest, run, package, count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'benchmarks/atlas')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/atlas-thread-scaling-audit')
    args = parser.parse_args()
    try:
        bundle = args.bundle.resolve()
        manifest, run, package, count = verify(bundle)
        print('Verified %d evidence files; 50 timing + 50 profile records.' % count)
        if args.verify_only:
            return
        output = args.output.resolve()
        if output == bundle or bundle in output.parents or output in bundle.parents:
            raise ValueError('Output must be outside the evidence bundle')
        output.mkdir(parents=True, exist_ok=False)
        result = output / run.name
        shutil.copytree(run, result)
        with tarfile.open(package) as tar:
            for name in ('analyze-atlas-thread-scaling.py', 'atlas-thread-scaling-launch.py',
                         'atlas-hybrid-launch.py', 'atlas-affinity.py'):
                (output / name).write_bytes(tar.extractfile('project3-atlas-thread-scaling/' + name).read())
        proc = subprocess.run([sys.executable, '-B', str(output / 'analyze-atlas-thread-scaling.py'),
                               str(result)], text=True, capture_output=True)
        (output / 'audit.stdout.txt').write_text(proc.stdout)
        (output / 'audit.stderr.txt').write_text(proc.stderr)
        if proc.returncode:
            raise ValueError('Frozen analyzer failed; see audit.stderr.txt')
        matches = {name: (run / name).read_bytes() == (result / name).read_bytes() for name in OUTPUTS}
        received_audit = json.loads((run / 'analysis.audit.json').read_text())
        audit = json.loads((result / 'analysis.audit.json').read_text())
        # PBS writes status.txt in the exit trap, after the original analysis.
        # A later local analysis therefore inventories one additional input file.
        def english_only(inventory):
            return {name: value for name, value in inventory.items()
                    if not name.endswith(('.zh-CN.md', '.ko.md'))}
        received_inputs = english_only(received_audit.pop('source_sha256'))
        regenerated_inputs = english_only(audit['source_sha256'])
        added_status = ('status.txt' not in received_inputs
                        and regenerated_inputs.pop('status.txt', None) == digest(run / 'status.txt'))
        equivalent_audit = (received_audit == {k: v for k, v in audit.items() if k != 'source_sha256'}
                            and (received_inputs == english_only(audit['source_sha256'])
                                 or (added_status and received_inputs == regenerated_inputs)))
        if not all(value for name, value in matches.items() if name != 'analysis.audit.json') or not equivalent_audit:
            raise ValueError('Regenerated output differs: ' + str(matches))
        if any(audit[key] != 'pass' for key in ('completeness', 'numerical_check', 'placement_check', 'preflight_check')):
            raise ValueError('Audit did not pass')
        summary = dict(job_id=manifest['job_id'], archived_files=count, generated_outputs_identical=matches,
                       audit_values_equivalent=equivalent_audit,
                       audit_inventory_note=('Only added status.txt, written after the original analyzer by the PBS exit trap.'
                                             if added_status else 'No inventory difference.'),
                       timing_records=50, profile_records=50, preflight_records=20,
                       missing_optional_evidence=manifest['missing_optional_evidence'])
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print('Frozen audit passed; both CSVs and three reports match byte for byte.')
        print('Audit values match; status.txt added to the later input inventory by the PBS exit trap.')
        print('Analyses: ' + str(output))
    except (ValueError, OSError, KeyError, tarfile.TarError) as error:
        parser.exit(1, 'Error: %s\n' % error)


if __name__ == '__main__':
    main()
