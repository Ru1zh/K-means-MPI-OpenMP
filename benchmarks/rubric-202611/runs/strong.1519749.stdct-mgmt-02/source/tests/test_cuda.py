"""Real GPU acceptance tests; enable only on an allocated GPU with TEST_CUDA=1."""
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('TEST_CUDA') == '1', 'requires real CUDA build/device; TEST_CUDA=1')
class CudaTests(unittest.TestCase):
    def run_binary(self, name, args):
        proc = subprocess.run([str(ROOT / 'build' / name)] + args,
                              text=True, capture_output=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def compare(self, args):
        cpu = self.run_binary('kmeans_serial', args)
        gpu = self.run_binary('kmeans_cuda', args + ['--variant', 'v4'])
        for key in ('data_fingerprint', 'init_indices', 'initial_centers', 'counts', 'labels'):
            self.assertEqual(cpu[key], gpu[key], key)
        for a, b in zip(cpu['centers'], gpu['centers']):
            self.assertTrue(math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-10))
        self.assertTrue(math.isclose(cpu['sse'], gpu['sse'], rel_tol=1e-8, abs_tol=1e-10))
        self.assertEqual(gpu['backend'], 'cuda')
        self.assertTrue(gpu['gpu']['uuid'])
        self.assertGreater(gpu['gpu']['kernel_launches'], 0)
        return gpu

    def test_generated_and_warmup_reset(self):
        args = ['--n', '103', '--d', '3', '--k', '5', '--iterations', '7', '--dump']
        plain = self.compare(args)
        prof = self.compare(args + ['--warmup', '2', '--profile'])
        self.assertEqual(plain['labels'], prof['labels'])
        self.assertGreater(prof['gpu']['phase_seconds']['assignment'], 0)
        self.assertGreater(prof['gpu']['phase_seconds']['merge'], 0)
        self.assertNotIn('phase_seconds', plain['gpu'])

    def test_ties_empty_clusters_and_identical_points(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'points.txt'
            path.write_text('5 1\n0\n2\n1\n2\n2\n')
            self.compare(['--input', str(path), '--k', '3', '--init-indices', '0,1,3',
                          '--iterations', '3', '--dump', '--trace'])

    def test_no_visible_device_fails(self):
        proc = subprocess.run([str(ROOT / 'build/kmeans_cuda'), '--variant', 'v4'],
                              env=dict(os.environ, CUDA_VISIBLE_DEVICES=''),
                              text=True, capture_output=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0)
