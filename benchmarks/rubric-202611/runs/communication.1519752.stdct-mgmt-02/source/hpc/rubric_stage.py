#!/usr/bin/env python3
"""Snapshot only implementation/acceptance sources, then build per PBS job."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rubric_campaign import source_manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    expected = source_manifest()
    a.output.mkdir(parents=True, exist_ok=False)
    for name in expected:
        source = ROOT / name
        if source.is_symlink():
            raise ValueError('Source snapshots cannot contain symbolic links')
        target = a.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if source_manifest() != expected or source_manifest(a.output) != expected:
        raise ValueError('Source changed while staging; discard this snapshot and retry')
    (a.output / 'source-manifest.json').write_text(json.dumps(expected, indent=2) + '\n')
    print('Staged %d source/acceptance files; no shared binaries copied' % len(expected))


if __name__ == '__main__':
    main()
