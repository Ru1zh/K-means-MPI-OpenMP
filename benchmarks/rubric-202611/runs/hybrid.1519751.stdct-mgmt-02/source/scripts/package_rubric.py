#!/usr/bin/env python3
"""Create/verify a portable source-and-evidence ZIP without local build outputs, caches or secrets."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts for n in names):
            raise ValueError('Unsafe or duplicate archive paths')
        expected = json.loads(archive.read('PACKAGE-SHA256.json'))
        actual = {n: hashlib.sha256(archive.read(n)).hexdigest() for n in names if n != 'PACKAGE-SHA256.json'}
        if expected != actual:
            raise ValueError('Package checksum mismatch')
    return len(actual)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    p.add_argument('--verify', type=Path)
    a = p.parse_args()
    if a.verify:
        print('Verified %d source/evidence files' % verify(a.verify))
        return
    if not a.output:
        p.error('--output or --verify is required')
    evidence = ROOT / 'benchmarks/rubric-202611'
    has_measurements = any((evidence / 'runs').rglob('raw.jsonl'))
    if has_measurements:
        from reproduce_rubric import verify_manifest
        from rubric_analysis import read_runs, audit_records
        verify_manifest(evidence)
        audit_records(*read_runs(evidence / 'runs'))
    status = dict(status='verified_full_campaign' if has_measurements else 'implementation_only_pending_hpc',
                  real_gpu_and_256_core_acceptance=has_measurements)
    # Respect project ignore rules (including credentials/data/caches), and include
    # new untracked implementation files so a reviewable working tree can be packed.
    proc = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                          cwd=ROOT, capture_output=True, check=True)
    paths = [Path(name.decode()) for name in proc.stdout.split(b'\0') if name]
    manifests = {}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a.output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(set(paths)):
            path = ROOT / relative
            if path.resolve() == a.output.resolve() or not path.is_file():
                continue
            if path.is_symlink():
                raise ValueError('Do not package symbolic links: ' + str(relative))
            data = path.read_bytes()
            manifests[relative.as_posix()] = hashlib.sha256(data).hexdigest()
            archive.writestr(relative.as_posix(), data)
        data = (json.dumps(status, indent=2) + '\n').encode()
        archive.writestr('PACKAGE_STATUS.json', data)
        manifests['PACKAGE_STATUS.json'] = hashlib.sha256(data).hexdigest()
        archive.writestr('PACKAGE-SHA256.json', json.dumps(manifests, indent=2, sort_keys=True) + '\n')
    print('Created and verified %d files: %s' % (verify(a.output), a.output))


if __name__ == '__main__':
    main()
