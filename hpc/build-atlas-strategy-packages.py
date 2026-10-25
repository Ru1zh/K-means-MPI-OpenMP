#!/usr/bin/env python3
"""Build standalone Atlas job packages from this checkout; never replace outputs."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile


HPC = Path(__file__).resolve().parent
CODE = HPC.parent
STUDIES = ('smoke', 'validation', 'strong', 'hybrid', 'threads', 'communication')


def package_files(kind):
    """Flatten HPC helpers because PBS scripts run from PBS_O_WORKDIR."""
    files = {'Makefile': (CODE/'Makefile').read_bytes()}
    for pattern in ('README*.md', 'hpc/ATLAS_RUN_GUIDE*.md', 'src/*.cpp', 'src/*.hpp',
                    'tests/*.py', 'examples/*.txt'):
        for path in sorted(CODE.glob(pattern)):
            files[path.relative_to(CODE).as_posix()] = path.read_bytes()
    for name in ('benchmark.py', 'summarize.py'):
        files['scripts/'+name] = (CODE/'scripts'/name).read_bytes()
    helpers = ['atlas-%s.pbs'%kind]
    if kind in ('strong', 'hybrid', 'threads', 'communication'):
        helpers.append('atlas-affinity.py')
    if kind in ('hybrid', 'threads', 'communication'):
        helpers += ['atlas-hybrid-launch.py', 'atlas-thread-probe.cpp',
                    'test_atlas_affinity.py', 'test_atlas_hybrid.py']
    if kind in ('threads', 'communication'):
        helpers += ['atlas-strategies-common.sh', 'atlas-strategy-study.py',
                    'atlas-data-spec.json', 'test_atlas_strategy.py']
        files['study-default-plan.json'] = subprocess.check_output([
            sys.executable, str(HPC/'atlas-strategy-study.py'), '--kind', kind, '--dry-run'])
    for name in helpers:
        files[name] = (HPC/name).read_bytes()
    # Syntax checks run locally; Linux/MPI execution belongs to PBS.
    for name, content in files.items():
        if name.endswith('.py'):
            ast.parse(content.decode(), filename=name, feature_version=(3, 8))
        elif name.endswith(('.pbs', '.sh')):
            subprocess.run(['bash', '-n'], input=content, check=True)
    files['source-manifest.sha256'] = ''.join(
        '%s  %s\n'%(hashlib.sha256(content).hexdigest(), name)
        for name, content in sorted(files.items())).encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--studies', nargs='+', choices=STUDIES, default=list(STUDIES))
    parser.add_argument('--output', type=Path, default=CODE/'artifacts/atlas-packages',
                        help='New output directory (must not already exist)')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('Output already exists; choose a new directory: '+str(output))
    if len(set(args.studies)) != len(args.studies):
        parser.error('Duplicate studies are not allowed')
    prepared = {kind: package_files(kind) for kind in args.studies}
    output.mkdir(parents=True, exist_ok=False)
    report = []
    for kind, files in prepared.items():
        target = output/('project3-atlas-%s.tar.gz'%kind)
        prefix = 'project3-atlas-'+kind
        with tarfile.open(target, 'w:gz') as tar:
            for name, content in sorted(files.items()):
                member = tarfile.TarInfo(prefix+'/'+name)
                member.size = len(content)
                member.mode = 0o644
                tar.addfile(member, io.BytesIO(content))
        report.append(dict(study=kind, file=target.name, files=len(files),
                           sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    (output/'packages.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(output=str(output), packages=report), indent=2))


if __name__ == '__main__':
    main()
