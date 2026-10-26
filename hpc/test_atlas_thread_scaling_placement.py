"""Fixed P=2 placement contracts; Linux and process boundaries are simulated only."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('atlas-thread-scaling-launch.py')
if SCRIPT.exists():
    spec = importlib.util.spec_from_file_location('thread_scaling', SCRIPT)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
else:
    launcher = None


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(launcher, 'The fixed P=2 placement launcher is missing')
        cpus = list(range(40, 46)) + list(range(86, 92))
        self.allocation = dict(host='node', allowed_cpus=list(reversed(cpus)),
                               topology={str(c): dict(socket=i // 6, core=i % 6)
                                         for i, c in enumerate(cpus)})
        self.plan = launcher.build_plan(self.allocation)

    def records(self, t):
        result = []
        for rank, reserved in enumerate([list(range(40, 46)), list(range(86, 92))]):
            active = reserved[:t]
            result.append(dict(rank=rank, p=2, t=t, host='node', rank_cpus=reserved,
                               active_cpus=active, omp_places=','.join('{%d}' % c for c in active),
                               thread_probe=dict(openmp=201511, threads=[
                                   dict(tid=i, cpus=[c], current_cpu=c) for i, c in enumerate(active)]),
                               command=['/example/algorithm', '--threads', str(t)]))
        return result

    def args(self, folder, t=2):
        plan = folder / 'plan.json'
        plan.write_text(json.dumps(self.plan))
        return SimpleNamespace(plan=plan, t=t, probe=folder / 'probe', output=folder / 'placements',
                               directory=folder, nodefile=folder / 'node file',
                               command=['/example/algorithm', '--threads', str(t)])

    def test_plan_reserves_socket_local_masks_and_nested_active_prefixes(self):
        self.assertEqual(self.plan['schema_version'], 1)
        self.assertEqual(self.plan['p'], 2)
        self.assertEqual(self.plan['max_threads'], 6)
        self.assertEqual(self.plan['threads'], [1, 2, 3, 4, 6])
        self.assertEqual(self.plan['allocation'], self.allocation)
        reserved = [list(range(40, 46)), list(range(86, 92))]
        self.assertEqual(self.plan['reserved_ranks'], reserved)
        for t in [1, 2, 3, 4, 6]:
            self.assertEqual(self.plan['configurations'][str(t)],
                             dict(p=2, t=t, ranks=[reserved[0][:t], reserved[1][:t]]))
            self.assertEqual(launcher.verify_records(self.plan, t, self.records(t))['placement_check'], 'pass')

    def test_twelve_cores_on_one_socket_form_two_groups_of_six(self):
        allocation = dict(host='node', allowed_cpus=list(reversed(range(12))),
                          topology={str(c): dict(socket=7, core=c) for c in range(12)})
        self.assertEqual(launcher.build_plan(allocation)['reserved_ranks'],
                         [list(range(6)), list(range(6, 12))])

    def test_eight_plus_four_topology_cannot_cross_socket(self):
        for i, cpu in enumerate(self.allocation['allowed_cpus']):
            self.allocation['topology'][str(cpu)] = dict(socket=i // 8, core=i % 8)
        with self.assertRaisesRegex(ValueError, 'socket'):
            launcher.build_plan(self.allocation)

    def test_duplicate_core_cpu_and_wrong_cpu_count_are_rejected(self):
        for mutation in ['physical', 'cpu', 'count']:
            allocation = copy.deepcopy(self.allocation)
            if mutation == 'physical':
                allocation['topology']['41'] = dict(socket=0, core=0)
            elif mutation == 'cpu':
                allocation['allowed_cpus'][0] = allocation['allowed_cpus'][1]
            else:
                allocation['allowed_cpus'].pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                launcher.build_plan(allocation)

    def test_unbound_outside_duplicate_and_missing_threads_are_rejected(self):
        for failure in ['unbound', 'outside', 'duplicate', 'missing', 'tid']:
            records = self.records(2)
            threads = records[0]['thread_probe']['threads']
            if failure == 'unbound':
                threads[0]['cpus'] = [40, 41]
            elif failure == 'outside':
                threads[0].update(cpus=[42], current_cpu=42)
            elif failure == 'duplicate':
                threads[1].update(cpus=[40], current_cpu=40)
            elif failure == 'missing':
                threads.pop()
            else:
                threads[1]['tid'] = 0
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                launcher.verify_records(self.plan, 2, records)

    def test_wrong_rank_host_mask_active_places_and_configuration_are_rejected(self):
        for field, value in [('rank', 1), ('host', 'other'), ('rank_cpus', [40, 41]),
                             ('active_cpus', [40, 42]), ('omp_places', '{40},{42}'),
                             ('p', 3), ('t', 3)]:
            records = self.records(2)
            records[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                launcher.verify_records(self.plan, 2, records)
        with self.assertRaises(ValueError):
            launcher.verify_records(self.plan, 2, self.records(2)[:1])
        with self.assertRaises(ValueError):
            launcher.verify_records(self.plan, 5, self.records(2))
        tampered = copy.deepcopy(self.plan)
        tampered['reserved_ranks'][1] = list(range(40, 46))
        with self.assertRaises(ValueError):
            launcher.verify_records(tampered, 2, self.records(2))

    def test_rank_applies_reserved_mask_active_places_then_probe_then_exec(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            args = self.args(folder)
            events = []
            state = set(self.allocation['allowed_cpus'])
            def set_mask(pid, cpus):
                nonlocal state
                self.assertEqual((pid, cpus), (0, list(range(40, 46))))
                state = set(cpus)
                events.append('mask')
            def probe(command, **kwargs):
                self.assertEqual(state, set(range(40, 46)))
                self.assertEqual(command, [str(args.probe), '2'])
                env = kwargs['env']
                self.assertEqual({k: env[k] for k in ['OMP_NUM_THREADS', 'OMP_DYNAMIC', 'OMP_PLACES', 'OMP_PROC_BIND']},
                                 dict(OMP_NUM_THREADS='2', OMP_DYNAMIC='FALSE', OMP_PLACES='{40},{41}', OMP_PROC_BIND='close'))
                for key in ['GOMP_CPU_AFFINITY', 'KMP_AFFINITY', 'KMP_HW_SUBSET', 'OMP_THREAD_LIMIT']:
                    self.assertNotIn(key, env)
                events.append('probe')
                return subprocess.CompletedProcess(command, 0, json.dumps(self.records(2)[0]['thread_probe']), 'probe diagnostic\n')
            def execute(executable, command, env):
                self.assertEqual(events, ['mask', 'probe'])
                self.assertEqual(executable, args.command[0])
                self.assertEqual(command, args.command)
                self.assertEqual(env['OMP_PLACES'], '{40},{41}')
                self.assertEqual(json.loads((folder / 'rank-0.json').read_text()), self.records(2)[0])
                events.append('exec')
            environment = dict(OMPI_COMM_WORLD_RANK='0', OMPI_COMM_WORLD_SIZE='2',
                               GOMP_CPU_AFFINITY='0', KMP_AFFINITY='scatter', KMP_HW_SUBSET='1c', OMP_THREAD_LIMIT='1')
            stderr = io.StringIO()
            with patch.dict(os.environ, environment), \
                    patch.object(launcher.socket, 'gethostname', return_value='node'), \
                    patch.object(launcher.os, 'sched_getaffinity', side_effect=lambda pid: state, create=True), \
                    patch.object(launcher.os, 'sched_setaffinity', side_effect=set_mask, create=True), \
                    patch.object(launcher.subprocess, 'run', side_effect=probe), \
                    patch.object(launcher.os, 'execvpe', side_effect=execute), contextlib.redirect_stderr(stderr):
                launcher.rank_launch(args)
            self.assertEqual(events, ['mask', 'probe', 'exec'])
            self.assertIn('probe diagnostic', stderr.getvalue())

    def test_rank_rejects_incomplete_inherited_mask_and_preserves_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            args = self.args(folder)
            evidence = folder / 'rank-0.json'
            evidence.write_text('original')
            with patch.dict(os.environ, dict(OMPI_COMM_WORLD_RANK='0', OMPI_COMM_WORLD_SIZE='2')), \
                    patch.object(launcher.socket, 'gethostname', return_value='node'), \
                    patch.object(launcher.os, 'sched_getaffinity', return_value={40}, create=True):
                with self.assertRaisesRegex(ValueError, 'complete PBS'):
                    launcher.rank_launch(args)
            with patch.dict(os.environ, dict(OMPI_COMM_WORLD_RANK='0', OMPI_COMM_WORLD_SIZE='2')), \
                    patch.object(launcher.socket, 'gethostname', return_value='node'), \
                    patch.object(launcher.os, 'sched_getaffinity', side_effect=[set(self.allocation['allowed_cpus']), set(range(40, 46))], create=True), \
                    patch.object(launcher.os, 'sched_setaffinity', create=True), \
                    patch.object(launcher.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(self.records(2)[0]['thread_probe']), '')), \
                    patch.object(launcher.os, 'execvpe') as execute:
                with self.assertRaises(FileExistsError):
                    launcher.rank_launch(args)
                execute.assert_not_called()
            self.assertEqual(evidence.read_text(), 'original')

    def test_plan_cli_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            allocation = folder / 'allocation.json'
            allocation.write_text(json.dumps(self.allocation))
            plan = folder / 'plan.json'
            command = [sys.executable, str(SCRIPT), 'plan', str(allocation), str(plan)]
            first = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            content = plan.read_text()
            self.assertEqual(json.loads(content), self.plan)
            second = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(plan.read_text(), content)

    def test_run_failure_retains_diagnostics_and_emits_no_measurement(self):
        for failure in ['exit', 'probe', 'json', 'timeout']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                args = self.args(folder)
                def launch(command, **kwargs):
                    destination = Path(command[command.index('--directory') + 1])
                    for record in self.records(2):
                        if failure == 'probe':
                            record['active_cpus'] = [0, 1]
                        (destination / ('rank-%d.json' % record['rank'])).write_text(json.dumps(record))
                    if failure == 'timeout':
                        raise subprocess.TimeoutExpired(command, 240, output='partial', stderr='timeout diagnostic\n')
                    return subprocess.CompletedProcess(command, 3 if failure == 'exit' else 0,
                                                       'not json', 'command diagnostic\n')
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(launcher.subprocess, 'run', side_effect=launch), \
                        contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises((ValueError, SystemExit, subprocess.TimeoutExpired)):
                        launcher.run(args)
                self.assertEqual(stdout.getvalue(), '')
                destinations = list(args.output.iterdir())
                self.assertEqual(len(destinations), 1)
                check = json.loads((destinations[0] / 'check.json').read_text())
                self.assertEqual(check['placement_check'], 'fail')
                self.assertIn('diagnostic', (destinations[0] / 'stderr.txt').read_text())
                self.assertIn('diagnostic', stderr.getvalue())

    def test_run_links_unique_evidence_directories_without_claiming_hpc_results(self):
        # Synthetic stdout tests JSON association only; this is not an HPC measurement.
        with tempfile.TemporaryDirectory(prefix='thread placement paths ') as directory:
            folder = Path(directory)
            args = self.args(folder)
            def launch(command, **kwargs):
                self.assertEqual(command[:8], ['mpirun', '--hostfile', str(args.nodefile), '-n', '2', '--bind-to', 'none', '--nooversubscribe'])
                self.assertEqual(command[command.index('--') + 1:], args.command)
                destination = Path(command[command.index('--directory') + 1])
                for record in self.records(2):
                    (destination / ('rank-%d.json' % record['rank'])).write_text(json.dumps(record))
                return subprocess.CompletedProcess(command, 0, '{"fixture_marker": "process-boundary-only"}\n', '')
            identities = []
            with patch.object(launcher.subprocess, 'run', side_effect=launch):
                for _ in range(2):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        launcher.run(args)
                    measurement = json.loads(stdout.getvalue())
                    self.assertEqual(measurement['fixture_marker'], 'process-boundary-only')
                    self.assertEqual(measurement['placement_check'], 'pass')
                    check = json.loads((args.output / measurement['placement_id'] / 'check.json').read_text())
                    self.assertEqual((check['p'], check['t']), (2, 2))
                    identities.append(measurement['placement_id'])
            self.assertNotEqual(*identities)

    def test_empty_command_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(Path(directory))
            args.command = []
            with self.assertRaisesRegex(ValueError, 'executable'):
                launcher.run(args)
            self.assertFalse(args.output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
