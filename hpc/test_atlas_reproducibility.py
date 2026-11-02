"""Exercise portable packaging and offline evidence checks through their CLIs."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless((ROOT/'benchmarks/atlas').is_dir(),
                     'archived evidence bundle is not included in this code-only branch')
class ReproducibilityTests(unittest.TestCase):
    def test_unified_audit_replays_all_five_studies_without_mpi(self):
        with tempfile.TemporaryDirectory(prefix='atlas unified audit ') as temp:
            output = Path(temp)/'audit'
            result = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/reproduce_atlas.py'),
                                     '--output', str(output)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            studies = json.loads((output/'summary.json').read_text())
            self.assertEqual({s['study'] for s in studies},
                             {'strong','hybrid','threads','communication','thread-scaling'})
            self.assertEqual(sum(s['records'] for s in studies), 175)
            self.assertEqual(sum(s.get('profile_records', 0) for s in studies), 50)
            self.assertTrue(all(s['numerical_check']=='pass' for s in studies))
            scaling = json.loads((output/'thread-scaling/summary.json').read_text())
            self.assertTrue(scaling['audit_values_equivalent'])
            self.assertTrue(scaling['generated_outputs_identical']['phase-summary.csv'])

    def test_packages_are_self_contained_and_existing_outputs_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix='atlas package paths ') as temp:
            output = Path(temp) / 'packages'
            command = [sys.executable, str(ROOT/'hpc/build-atlas-strategy-packages.py'),
                       '--output', str(output)]
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            archives = sorted(output.glob('project3-atlas-*.tar.gz'))
            self.assertEqual({p.name for p in archives}, {'project3-atlas-%s.tar.gz'%kind for kind in
                             ['smoke','validation','strong','hybrid','threads','communication','thread-scaling']})
            before = {p.name: p.read_bytes() for p in archives}
            for archive in archives:
                prefix = archive.name[:-7] + '/'
                kind = archive.name[len('project3-atlas-'):-7]
                with tarfile.open(archive) as tar:
                    names = set(tar.getnames())
                    for required in ['Makefile', 'src/main.cpp', 'scripts/benchmark.py',
                                     'atlas-%s.pbs'%kind, 'source-manifest.sha256']:
                        self.assertIn(prefix+required, names)
                    self.assertNotIn(prefix+'build/kmeans_mpi', names)
                    manifest = tar.extractfile(prefix+'source-manifest.sha256').read().decode()
                    for line in manifest.splitlines():
                        digest, name = line.split('  ', 1)
                        self.assertEqual(hashlib.sha256(tar.extractfile(prefix+name).read()).hexdigest(), digest)
                    self.assertEqual(tar.extractfile(prefix+'src/main.cpp').read(),
                                     (ROOT/'src/main.cpp').read_bytes())
            second = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual({p.name:p.read_bytes() for p in archives}, before)

    def test_offline_verification_rejects_changed_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)/'bundle'
            shutil.copytree(ROOT/'benchmarks/atlas', bundle)
            command = [sys.executable, str(ROOT/'scripts/reproduce_atlas.py'),
                       '--bundle', str(bundle), '--verify-only']
            good = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            manifest = json.loads((bundle/'manifest.json').read_text())
            study = manifest['studies']['strong']
            raw = bundle/study['directory']/study['raw_file']
            raw.write_bytes(raw.read_bytes()+b'\n')
            changed = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(changed.returncode, 0)
            self.assertIn('strong.jsonl', changed.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
