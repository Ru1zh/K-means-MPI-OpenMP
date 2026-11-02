"""Audit real JSON study fixtures without MPI, sockets, or cluster access."""
import csv
import importlib.util
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HPC = Path(__file__).resolve().parent
ANALYZER = HPC / 'analyze-atlas-thread-scaling.py'
PHASES = ('accumulate', 'thread_merge', 'mpi_reduce', 'centroid_update', 'control_bcast')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n')


def create_study(folder):
    workload = dict(n=1000000, d=32, k=32, seed=42, iterations=20, warmup=2)
    plan = dict(study='thread-scaling', p=2, threads=[1, 2, 3, 4, 6], workload=workload,
                repeats=5, expected_timing_records=50, expected_profile_records=50)
    allocation = dict(host='node', job_id='123.cluster', allowed_cpus=list(range(12)),
                      topology={str(c): dict(socket=c // 6, core=c) for c in range(12)})
    layout = dict(schema_version=1, p=2, max_threads=6, threads=plan['threads'], allocation=allocation,
                  reserved_ranks=[list(range(6)), list(range(6, 12))],
                  configurations={str(t): dict(p=2, t=t, ranks=[list(range(t)), list(range(6, 6+t))])
                                  for t in plan['threads']})
    write_json(folder / 'study-plan.json', plan)
    write_json(folder / 'layout-plan.json', layout)
    reference = dict(workload, variant='v0', p=1, t=1, diagnostic=False, mode='fixed',
                     stop_reason='fixed_iterations', requested_iterations=20, data_fingerprint='abc123',
                     init_indices=list(range(32)), counts=[31250]*32, sse=50.0, kernel_seconds=99999.0)
    write_json(folder / 'reference-large.json', reference)
    modes = {}
    for mode in ('timing', 'profile'):
        rows = []
        for variant in ('v2', 'v3'):
            for t in plan['threads']:
                for repeat in range(5):
                    identifier = 'launch-%s-%s-%d-%d' % (mode, variant, t, repeat)
                    seconds = ((12 if variant == 'v2' else 6) + repeat) / t
                    if mode == 'profile':
                        seconds = 100.0 + repeat
                    row = dict(workload, p=2, t=t, variant=variant, communication='allreduce', mode='fixed',
                               diagnostic=mode == 'profile', stop_reason='fixed_iterations',
                               job_id='123.cluster', host='node', compiler='GCC 9.2', mpi_version='OpenMPI 4.1',
                               requested_iterations=20, counts=[31250]*32, init_indices=list(range(32)),
                               data_fingerprint='abc123', sse=50.0, kernel_seconds=seconds, repeat=repeat,
                               measurement_mode=mode, placement_id=identifier, placement_check='pass')
                    if mode == 'profile':
                        row['profile_ranks'] = [
                            dict(rank=0, kernel_seconds=seconds-10, phase_seconds=dict(zip(PHASES, [60, 2, 1, 1, 1]))),
                            dict(rank=1, kernel_seconds=seconds, phase_seconds=dict(zip(PHASES, [20, 3, 4, 2, 1]))) ]
                        row['profile_critical_rank'] = 1
                        # Legacy independent maxima deliberately differ from the critical rank.
                        row['phase_seconds'] = dict(zip(PHASES, [60, 3, 4, 2, 1]))
                    directory = folder / 'placements' / identifier
                    command = ['build/kmeans_mpi', '--variant', variant, '--threads', str(t)]
                    write_json(directory / 'launch.json', dict(p=2, t=t, algorithm_command=command, command=['mpirun']))
                    records = []
                    for rank, cpus in enumerate(layout['configurations'][str(t)]['ranks']):
                        record = dict(rank=rank, p=2, t=t, host='node', rank_cpus=layout['reserved_ranks'][rank], active_cpus=cpus,
                                      omp_places=','.join('{%d}' % c for c in cpus), command=command,
                                      thread_probe=dict(openmp=201511, threads=[dict(tid=i, cpus=[c], current_cpu=c)
                                                                             for i, c in enumerate(cpus)]))
                        records.append(record)
                        write_json(directory / ('rank-%d.json' % rank), record)
                    # The verifier's genuine output is saved, matching launcher behavior.
                    helper = HPC / 'atlas-thread-scaling-launch.py'
                    if helper.exists():
                        spec = importlib.util.spec_from_file_location('scaling_fixture_launch', helper)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        check = module.verify_records(layout, t, records)
                    else:
                        check = dict(p=2, t=t, placement_check='pass')
                    write_json(directory / 'check.json', check)
                    rows.append(row)
        modes[mode] = rows
        save_rows(folder, mode, rows)
    small_workload = dict(n=37, d=3, k=4, seed=42, iterations=5, warmup=2)
    small_reference = dict(small_workload, variant='v0', p=1, t=1, diagnostic=False,
                           mode='fixed', stop_reason='fixed_iterations', requested_iterations=5,
                           data_fingerprint='small123', init_indices=[0, 1, 2, 3], counts=[10, 9, 9, 9],
                           sse=5.0, labels=[0]*10+[1]*9+[2]*9+[3]*9, centers=[float(i) for i in range(12)])
    write_json(folder / 'reference-small.json', small_reference)
    for mode, rows in modes.items():
        for source in rows:
            if source['repeat'] != 0:
                continue
            row = json.loads(json.dumps(source))
            row.update(small_workload)
            for key in ('data_fingerprint', 'init_indices', 'counts', 'sse', 'labels', 'centers'):
                row[key] = small_reference[key]
            row['requested_iterations'] = 5
            row['placement_id'] = 'launch-preflight-' + source['placement_id'][7:]
            for key in ('repeat', 'measurement_mode', 'job_id', 'host'):
                row.pop(key)
            shutil.copytree(folder / 'placements' / source['placement_id'],
                            folder / 'preflight-placements' / row['placement_id'])
            write_json(folder / ('preflight-%s-%s-t%d.json' % (mode, row['variant'], row['t'])), row)
    write_json(folder / 'preflight-check.json', dict(numerical_check='pass', configurations=20))
    return modes


def save_rows(folder, mode, rows):
    (folder / (mode + '.jsonl')).write_text(''.join(json.dumps(r) + '\n' for r in rows))


class ThreadScalingAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.rows = create_study(self.folder)

    def run_analysis(self):
        return subprocess.run([sys.executable, str(ANALYZER), str(self.folder)],
                              capture_output=True, text=True)

    def assert_rejected(self):
        result = self.run_analysis()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.folder / 'thread-scaling-summary.csv').exists(), result.stderr)
        self.assertFalse((self.folder / 'analysis.audit.json').exists(), result.stderr)

    def test_correct_statistics_use_timing_only_and_same_variant_t1(self):
        before = {p.relative_to(self.folder): p.read_bytes() for p in self.folder.rglob('*') if p.is_file()}
        result = self.run_analysis()
        self.assertEqual(result.returncode, 0, result.stderr)
        with (self.folder / 'thread-scaling-summary.csv').open() as source:
            summaries = {(r['variant'], int(r['t'])): r for r in csv.DictReader(source)}
        self.assertEqual(len(summaries), 10)
        self.assertEqual(float(summaries['v2', 2]['median_seconds']), 7.0)
        self.assertEqual(float(summaries['v3', 2]['median_seconds']), 4.0)
        self.assertEqual(float(summaries['v3', 2]['min_seconds']), 3.0)
        self.assertEqual(float(summaries['v3', 2]['max_seconds']), 5.0)
        self.assertEqual(float(summaries['v3', 2]['speedup_vs_same_variant_t1']), 2.0)
        self.assertEqual(float(summaries['v3', 2]['thread_efficiency']), 1.0)
        audit = json.loads((self.folder / 'analysis.audit.json').read_text())
        self.assertEqual((audit['records'], audit['timing_records'], audit['profile_records']), (100, 50, 50))
        self.assertEqual(audit['preflight_records'], 20)
        self.assertEqual(audit['preflight_check'], 'pass')
        for field in ('completeness', 'numerical_check', 'placement_check'):
            self.assertEqual(audit[field], 'pass')
        for name in ('analysis.md',):
            text = (self.folder / name).read_text()
            self.assertIn('123.cluster', text)
            self.assertIn('14.000000', text)
        self.assertEqual(before, {p: (self.folder / p).read_bytes() for p in before})
        self.assertEqual(self.run_analysis().returncode, 0)

    def test_phase_contributions_use_one_critical_rank_per_sample(self):
        result = self.run_analysis()
        self.assertEqual(result.returncode, 0, result.stderr)
        with (self.folder / 'phase-summary.csv').open() as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(len(rows), 10)
        first = rows[0]
        self.assertEqual(float(first['accumulate_median_seconds']), 20.0)
        self.assertAlmostEqual(float(first['accumulate_median_pct']), 100 * 20 / 102)
        self.assertEqual(float(first['critical_rank_residual_median_seconds']), 72.0)
        self.assertAlmostEqual(float(first['critical_rank_residual_median_pct']), 100 * 72 / 102)

    def test_invalid_measurement_matrix_and_environment_rejected(self):
        cases = [ ('missing row', lambda rows: rows.pop()),
                  ('duplicate repeat', lambda rows: rows[0].update(repeat=1)),
                  ('different job', lambda rows: rows[0].update(job_id='other')),
                  ('different host', lambda rows: rows[0].update(host='other')),
                  ('different compiler', lambda rows: rows[0].update(compiler='other')),
                  ('different MPI', lambda rows: rows[0].update(mpi_version='other')),
                  ('wrong mode', lambda rows: rows[0].update(mode='convergence')),
                  ('profile in timing', lambda rows: rows[0].update(diagnostic=True)),
                  ('wrong measurement', lambda rows: rows[0].update(measurement_mode='profile')),
                  ('nonfinite', lambda rows: rows[0].update(kernel_seconds=float('nan'))),
                  ('zero kernel', lambda rows: rows[0].update(kernel_seconds=0)),
                  ('different workload', lambda rows: rows[0].update(n=21)),
                  ('different fingerprint', lambda rows: rows[0].update(data_fingerprint='other')),
                  ('different initialization', lambda rows: rows[0].update(init_indices=[1, 2])),
                  ('different counts', lambda rows: rows[0].update(counts=[10, 10])),
                  ('bad SSE', lambda rows: rows[0].update(sse=51)),
                  ('nan SSE', lambda rows: rows[0].update(sse=float('nan'))),
                  ('nonfixed iterations', lambda rows: rows[0].update(requested_iterations=4)),
                  ('duplicate placement', lambda rows: rows[0].update(placement_id=rows[1]['placement_id'])) ]
        original = json.dumps(self.rows['timing'])
        for name, mutate in cases:
            with self.subTest(name=name):
                rows = json.loads(original)
                mutate(rows)
                save_rows(self.folder, 'timing', rows)
                self.assert_rejected()

    def test_invalid_rank_profiles_rejected(self):
        cases = [ ('false critical rank', lambda row: row.update(profile_critical_rank=0)),
                  ('missing rank', lambda row: row['profile_ranks'].pop()),
                  ('duplicate rank', lambda row: row['profile_ranks'][0].update(rank=1)),
                  ('max disagrees', lambda row: row.update(kernel_seconds=1000)),
                  ('negative phase', lambda row: row['profile_ranks'][0]['phase_seconds'].update(accumulate=-1)),
                  ('nan phase', lambda row: row['profile_ranks'][0]['phase_seconds'].update(accumulate=float('nan'))),
                  ('excessive sum', lambda row: row['profile_ranks'][0]['phase_seconds'].update(accumulate=90)),
                  ('negative rank kernel', lambda row: row['profile_ranks'][0].update(kernel_seconds=-1)) ]
        original = json.dumps(self.rows['profile'])
        for name, mutate in cases:
            with self.subTest(name=name):
                rows = json.loads(original)
                mutate(rows[0])
                save_rows(self.folder, 'profile', rows)
                self.assert_rejected()

    def test_missing_or_forged_placement_evidence_rejected(self):
        directory = self.folder / 'placements' / self.rows['timing'][0]['placement_id']
        path = directory / 'rank-1.json'
        original = path.read_text()
        path.unlink()
        self.assert_rejected()
        path.write_text(original)
        record = json.loads(original)
        record['rank_cpus'] = [0]
        write_json(path, record)
        self.assert_rejected()

    def test_fixed_formal_workload_cannot_be_replaced_consistently(self):
        path = self.folder / 'study-plan.json'
        plan = json.loads(path.read_text())
        plan['workload']['d'] = 16
        write_json(path, plan)
        reference_path = self.folder / 'reference-large.json'
        reference = json.loads(reference_path.read_text())
        reference['d'] = 16
        write_json(reference_path, reference)
        for mode in ('timing', 'profile'):
            for row in self.rows[mode]:
                row['d'] = 16
            save_rows(self.folder, mode, self.rows[mode])
        self.assert_rejected()

    def test_preflight_files_and_checks_are_required(self):
        for name in ('reference-small.json', 'preflight-check.json', 'preflight-timing-v2-t1.json',
                     'preflight-profile-v3-t6.json'):
            with self.subTest(name=name):
                path = self.folder / name
                original = path.read_text()
                path.unlink()
                self.assert_rejected()
                path.write_text(original)

    def test_preflight_numerical_configuration_and_profile_tampering_rejected(self):
        path = self.folder / 'preflight-profile-v2-t1.json'
        original = path.read_text()
        cases = [dict(labels=[0]*37), dict(centers=[1.0]*12), dict(counts=[9,10,9,9]),
                 dict(sse=7.0), dict(init_indices=[4,5,6,7]), dict(data_fingerprint='wrong'),
                 dict(diagnostic=False), dict(mode='convergence'), dict(variant='v3'),
                 dict(p=1), dict(t=2), dict(profile_critical_rank=0), dict(requested_iterations=6)]
        for change in cases:
            with self.subTest(change=change):
                row = json.loads(original)
                row.update(change)
                write_json(path, row)
                self.assert_rejected()
        path.write_text(original)
        row = json.loads(original)
        evidence = self.folder / 'preflight-placements' / row['placement_id'] / 'rank-0.json'
        evidence.unlink()
        self.assert_rejected()

    def test_v0_references_must_be_serial_and_nondiagnostic(self):
        for name in ('reference-small.json', 'reference-large.json'):
            path = self.folder / name
            original = path.read_text()
            for change in (dict(p=2), dict(t=2), dict(diagnostic=True), dict(variant='v2')):
                with self.subTest(name=name, change=change):
                    row = json.loads(original)
                    row.update(change)
                    write_json(path, row)
                    self.assert_rejected()
            path.write_text(original)

    def test_rank_kernel_ties_choose_smaller_rank(self):
        for row in self.rows['profile']:
            row['profile_ranks'][0]['kernel_seconds'] = row['kernel_seconds']
            row['profile_critical_rank'] = 0
        save_rows(self.folder, 'profile', self.rows['profile'])
        result = self.run_analysis()
        self.assertEqual(result.returncode, 0, result.stderr)
        for row in self.rows['profile']:
            row['profile_critical_rank'] = 1
        save_rows(self.folder, 'profile', self.rows['profile'])
        self.assertNotEqual(self.run_analysis().returncode, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
