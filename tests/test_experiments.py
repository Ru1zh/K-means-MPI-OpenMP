#!/usr/bin/env python3
"""Exercise real CLI runners and summaries without optional Python packages."""
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ExperimentTests(unittest.TestCase):
    def test_runner_and_median_pipeline(self):
        script = ROOT / 'scripts/benchmark.py'
        self.assertTrue(script.exists(), 'Benchmark runner is not implemented')
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / 'raw.jsonl'
            summary = Path(directory) / 'summary.csv'
            subprocess.run([sys.executable, str(script), '--suite', 'serial', '--n', '23',
                            '--d', '2', '--k', '3', '--iterations', '2', '--repeats', '5',
                            '--output', str(raw)], check=True, capture_output=True)
            rows = [json.loads(x) for x in raw.read_text().splitlines()]
            self.assertEqual(len(rows), 5)
            self.assertEqual(len({r['data_fingerprint'] for r in rows}), 1)
            subprocess.run([sys.executable, str(ROOT / 'scripts/summarize.py'), str(raw),
                            '--output', str(summary)], check=True, capture_output=True)
            with summary.open() as source:
                result = list(csv.DictReader(source))
            self.assertEqual(len(result), 1)
            times = sorted(r['kernel_seconds'] for r in rows)
            self.assertAlmostEqual(float(result[0]['median_seconds']), times[2])
            self.assertEqual(int(result[0]['repeats']), 5)
            # Overlapping raw files must not silently inflate the repeat count.
            duplicate = subprocess.run([sys.executable, str(ROOT / 'scripts/summarize.py'),
                                        str(raw), str(raw), '--output', str(Path(directory) / 'duplicate.csv')],
                                       text=True, capture_output=True)
            self.assertNotEqual(duplicate.returncode, 0)
            # Some MPI libraries include a terminating NUL in their reported length.
            rows[0]['mpi_version'] = 'MPI library\x00'
            legacy = Path(directory) / 'legacy.jsonl'
            legacy.write_text('\n'.join(json.dumps(r) for r in rows))
            portable_csv = Path(directory) / 'portable.csv'
            subprocess.run([sys.executable, str(ROOT / 'scripts/summarize.py'), str(legacy),
                            '--output', str(portable_csv)], check=True, capture_output=True)
            self.assertNotIn('\x00', portable_csv.read_text())

    def test_launch_timer_excludes_metadata_work(self):
        spec = importlib.util.spec_from_file_location('benchmark', ROOT / 'scripts/benchmark.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        state = {'metadata_started': False, 'ticks': 0}

        def clock():
            if state['metadata_started']:
                return 100.0
            value = float(state['ticks'])
            state['ticks'] += 1
            return value

        def metadata():
            state['metadata_started'] = True
            return 'test platform'

        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / 'raw.jsonl'
            argv = ['benchmark.py', '--suite', 'serial', '--n', '10', '--k', '2',
                    '--iterations', '1', '--repeats', '1', '--output', str(raw)]
            # The executable runs for real. Only metadata and its clock cost are controlled.
            with patch.object(sys, 'argv', argv), patch.object(runner.time, 'perf_counter', clock), \
                    patch.object(runner.platform, 'platform', metadata):
                runner.main()
            self.assertEqual(json.loads(raw.read_text())['launch_seconds'], 1.0)

    def test_weak_scaling_dry_run_changes_n_with_p(self):
        script = ROOT / 'scripts/benchmark.py'
        self.assertTrue(script.exists(), 'Benchmark runner is not implemented')
        proc = subprocess.run([sys.executable, str(script), '--suite', 'weak', '--n', '100',
                               '--k', '2', '--processes', '1,2,4', '--threads', '2',
                               '--dry-run'], check=True, text=True, capture_output=True)
        commands = [json.loads(line)['command'] for line in proc.stdout.splitlines()]
        self.assertEqual([int(cmd[cmd.index('--n') + 1]) for cmd in commands], [100, 200, 400])


if __name__ == '__main__':
    unittest.main(verbosity=2)
