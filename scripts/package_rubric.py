#!/usr/bin/env python3
"""Create/verify a source submission or a complete local source-and-evidence ZIP."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def submission_files():
    """Explicit source allowlist: no generated results or duplicate guides."""
    files = [Path(name) for name in ('Makefile', 'README.md', 'README.zh-CN.md', 'README.ko.md',
                                     'analysis/rubric-202611/render_paper_figures.py')]
    for folder, patterns in (('src', ('*.cpp', '*.hpp', '*.cu')),
                             ('scripts', ('*.py',)), ('hpc', ('*.py', '*.pbs')),
                             ('tests', ('*.py',))):
        for pattern in patterns:
            files.extend(p.relative_to(ROOT) for p in (ROOT / folder).glob(pattern))
    if any(not (ROOT / path).is_file() for path in files):
        raise ValueError('Missing required source or README')
    return sorted(set(files))


def submission_bytes(relative):
    path = ROOT / relative
    if path.is_symlink():
        raise ValueError('Do not package symbolic links: ' + str(relative))
    data = path.read_bytes()
    if relative.name.startswith('README'):
        # The local figure/evidence index belongs in the repository README,
        # but would leave dangling links in a source-only submission.
        text = data.decode('utf-8')
        start, end = '<!-- LOCAL_ARCHIVE_START -->', '<!-- LOCAL_ARCHIVE_END -->'
        if start in text:
            before, local = text.split(start, 1)
            _, after = local.split(end, 1)
            text = before.rstrip() + '\n' + after
        data = text.encode('utf-8')
    return data


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts for n in names):
            raise ValueError('Unsafe or duplicate archive paths')
        if 'PACKAGE-SHA256.json' not in names:
            expected = {p.as_posix(): submission_bytes(p) for p in submission_files()}
            if set(names) != set(expected) or any(archive.read(n) != data for n, data in expected.items()):
                raise ValueError('Source submission differs from current source/README files')
            return len(expected)
        expected = json.loads(archive.read('PACKAGE-SHA256.json'))
        actual = {n: hashlib.sha256(archive.read(n)).hexdigest() for n in names if n != 'PACKAGE-SHA256.json'}
        if expected != actual:
            raise ValueError('Package checksum mismatch')
    return len(actual)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    p.add_argument('--verify', type=Path)
    p.add_argument('--submission', action='store_true',
                   help='include only source code, Makefile and three language READMEs')
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
    if a.submission:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(a.output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for relative in submission_files():
                archive.writestr(relative.as_posix(), submission_bytes(relative))
        print('Created and verified %d source/README files: %s' % (verify(a.output), a.output))
        return
    status = dict(status='verified_full_campaign' if has_measurements else 'implementation_only_pending_hpc',
                  real_gpu_and_256_core_acceptance=has_measurements,
                  package_kind='submission' if a.submission else 'local_reproducibility_archive',
                  raw_evidence_included=has_measurements and not a.submission)
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
