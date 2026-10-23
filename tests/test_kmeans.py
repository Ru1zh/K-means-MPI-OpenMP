#!/usr/bin/env python3
"""Black-box numerical tests; Python standard library only."""
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERIAL = Path(os.environ.get('KMEANS_SERIAL', ROOT / 'build/kmeans_serial'))
PARALLEL = Path(os.environ.get('KMEANS_MPI', ROOT / 'build/kmeans_mpi'))
MPI = os.environ.get('TEST_MPI') == '1'


class KMeansTests(unittest.TestCase):
    def run_km(self, args, p=0, variant='v1', comm='allreduce', t=1, ok=True):
        exe = PARALLEL if p else SERIAL
        self.assertTrue(exe.is_file(), f'Executable not built: {exe}')
        cmd = [str(exe)]
        if p:
            cmd = shlex.split(os.environ.get('MPIEXEC', 'mpiexec')) + shlex.split(
                os.environ.get('MPIEXEC_FLAGS', '')) + ['-n', str(p)] + cmd
            cmd += ['--variant', variant, '--comm', comm, '--threads', str(t)]
        env = dict(os.environ, OMP_DYNAMIC='FALSE')
        proc = subprocess.run(cmd + args, text=True, capture_output=True, env=env, timeout=40)
        if not ok:
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            return
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertNotIn('\x00', result['mpi_version'])
        self.assertTrue(math.isfinite(result['sse']))
        self.assertGreaterEqual(result['sse'], 0)
        self.assertEqual(sum(result['counts']), result['n'])
        return result

    def fixture(self, text):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        f.write(text)
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def close_list(self, left, right):
        self.assertEqual(len(left), len(right))
        for a, b in zip(left, right):
            self.assertTrue(math.isclose(a, b, abs_tol=1e-10, rel_tol=1e-8), (a, b))

    def test_hand_computed_one_round_and_final_evaluation(self):
        path = self.fixture('4 2\n0 0\n0 2\n10 10\n10 12\n')
        r = self.run_km(['--input', path, '--k', '2', '--init-indices', '0,2',
                         '--iterations', '1', '--dump', '--trace'])
        self.assertEqual(r['centers'], [0, 1, 10, 11])
        self.assertEqual(r['counts'], [2, 2])
        self.assertEqual(r['labels'], [0, 0, 1, 1])
        self.assertEqual(r['sse'], 4)
        self.assertEqual(r['trace'][0]['sse_before'], 8)

    def test_final_labels_use_new_centers(self):
        path = self.fixture('4 1\n0\n2\n3\n10\n')
        r = self.run_km(['--input', path, '--k', '2', '--init-indices', '0,1',
                         '--iterations', '1', '--dump'])
        self.assertEqual(r['centers'], [0, 5])
        self.assertEqual(r['labels'], [0, 0, 1, 1])
        self.assertEqual(r['counts'], [2, 2])
        self.assertEqual(r['sse'], 33)

    def test_tie_break_and_empty_cluster(self):
        path = self.fixture('3 1\n0\n0\n2\n')
        r = self.run_km(['--input', path, '--k', '3', '--init-indices', '0,1,2',
                         '--iterations', '2', '--dump'])
        self.assertEqual(r['counts'], [2, 0, 1])
        self.assertEqual(r['centers'], [0, 0, 2])
        self.assertEqual(r['labels'], [0, 0, 2])

    def test_k_one_and_k_n(self):
        path = self.fixture('3 1\n0\n3\n6\n')
        r = self.run_km(['--input', path, '--k', '1', '--iterations', '1', '--dump'])
        self.assertEqual(r['centers'], [3])
        self.assertEqual(r['sse'], 18)
        r = self.run_km(['--input', path, '--k', '3', '--iterations', '1'])
        self.assertEqual(r['sse'], 0)

    def test_convergence_and_iteration_limit(self):
        path = self.fixture('2 1\n0\n2\n')
        args = ['--input', path, '--k', '1', '--mode', 'converge', '--tol', '0']
        r = self.run_km(args + ['--iterations', '5'])
        self.assertEqual(r['iterations'], 2)
        self.assertEqual(r['stop_reason'], 'converged')
        r = self.run_km(args + ['--iterations', '1'])
        self.assertEqual(r['stop_reason'], 'max_iterations')

    def test_warmup_resets_state_and_objective_decreases(self):
        args = ['--n', '103', '--d', '3', '--k', '5', '--iterations', '7', '--dump', '--trace']
        a, b = self.run_km(args), self.run_km(args + ['--warmup', '3'])
        self.assertEqual(a['centers'], b['centers'])
        objectives = [x['sse_before'] for x in a['trace']] + [a['sse']]
        self.assertTrue(all(y <= x + 1e-8 * max(1, x) for x, y in zip(objectives, objectives[1:])))
        self.assertEqual(a['iterations'], 7)

    def test_invalid_input(self):
        for args in [['--n', '0'], ['--d', '0'], ['--n', '2', '--k', '3'],
                     ['--n', '-1'], ['--tol', 'nan'], ['--iterations', '0'],
                     ['--threads', '2'], ['--n', '9x'], ['--unknown', '1'],
                     ['--n', '18446744073709551616'], ['--k', '2', '--init-indices', '0,0']]:
            with self.subTest(args=args):
                self.run_km(args, ok=False)
        for text in ['2 1\n0\nnan\n', '2 2\n1 2 3\n', '1 1\ninf\n',
                     '1 1\n0 2\n', '0 1\n', '2 1\n1e308 -1e308\n']:
            with self.subTest(text=text):
                self.run_km(['--input', self.fixture(text), '--k', '1'], ok=False)

    @unittest.skipUnless(MPI, 'set TEST_MPI=1 for real MPI integration tests')
    def test_parallel_variants_each_round_and_uneven_partitions(self):
        args = ['--n', '37', '--d', '3', '--k', '4', '--iterations', '5', '--dump', '--trace']
        ref = self.run_km(args)
        for p, variant, t in [(1, 'v1', 1), (3, 'v1', 1), (3, 'v2', 2), (3, 'v3', 2)]:
            for comm in ['allreduce', 'reduce-bcast']:
                with self.subTest(p=p, variant=variant, comm=comm):
                    r = self.run_km(args, p=p, variant=variant, comm=comm, t=t)
                    self.assertEqual(r['init_indices'], ref['init_indices'])
                    self.assertEqual(r['data_fingerprint'], ref['data_fingerprint'])
                    self.assertEqual(r['counts'], ref['counts'])
                    self.assertEqual(r['labels'], ref['labels'])
                    self.close_list(r['centers'], ref['centers'])
                    self.close_list([r['sse']], [ref['sse']])
                    for x, y in zip(r['trace'], ref['trace']):
                        self.assertEqual(x['counts'], y['counts'])
                        self.close_list(x['centers'], y['centers'])
                        self.close_list([x['sse_before']], [y['sse_before']])

    @unittest.skipUnless(MPI, 'set TEST_MPI=1 for real MPI integration tests')
    def test_zero_sample_ranks_and_collective_failures(self):
        path = self.fixture('2 1\n0\n2\n')
        for variant, t in [('v1', 1), ('v2', 2), ('v3', 2)]:
            for comm in ['allreduce', 'reduce-bcast']:
                r = self.run_km(['--input', path, '--k', '1', '--mode', 'converge',
                                 '--dump'], p=3, variant=variant, t=t, comm=comm)
                self.assertEqual(r['sse'], 2)
                self.assertEqual(r['centers'], [1])
                self.assertEqual(r['stop_reason'], 'converged')
        self.run_km(['--input', path + '.missing', '--k', '1'], p=2, ok=False)
        self.run_km(['--input', self.fixture('2 1\n0 nan\n'), '--k', '1'], p=2, ok=False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
