"""Rubric campaign contracts: workload boundaries, baselines and placement safety."""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RubricTests(unittest.TestCase):
    def test_matrix_counts_and_real_mpi_workload(self):
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/rubric_campaign.py'),
                               '--suite', 'all', '--cores-per-node', '64', '--dry-run'],
                              text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = [json.loads(x) for x in proc.stdout.splitlines()]
        ordinary = [x for x in rows if not x['profile']]
        diagnostic = [x for x in rows if x['profile']]
        self.assertEqual(len(ordinary), 55)
        self.assertEqual(len(diagnostic), 15)
        counts = {s: sum(r['suite'] == s for r in ordinary)
                  for s in ('serial', 'strong', 'weak', 'hybrid', 'communication', 'gpu')}
        self.assertEqual(counts, dict(serial=14, strong=10, weak=9, hybrid=9, communication=4, gpu=9))
        strong = [r for r in ordinary if r['suite'] == 'strong' and r['variant'] != 'v0']
        self.assertEqual([r['p'] for r in strong], [1, 2, 4, 8, 16, 32, 64, 128, 256])
        self.assertTrue(all(r['variant'] == 'v1' and r['t'] == 1 and r['n'] == 4000000 for r in strong))
        weak = [r for r in ordinary if r['suite'] == 'weak']
        self.assertTrue(all(r['n'] == r['p'] * 100000 for r in weak))
        self.assertTrue(all('--profile' in r['command'] for r in diagnostic))
        gpu = [r for r in ordinary if r['suite'] == 'gpu' and r['variant'] == 'v4']
        self.assertTrue(all('kmeans_cuda' in ' '.join(r['command']) for r in gpu))

    def test_explicit_serial_sensitivity(self):
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/benchmark.py'),
                               '--suite', 'sensitivity', '--variant', 'v0', '--processes', '1',
                               '--threads', '1', '--dry-run'], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = [json.loads(x) for x in proc.stdout.splitlines()]
        self.assertTrue(rows)
        self.assertTrue(all(r['variant'] == 'v0' and r['p'] == r['t'] == 1 for r in rows))

    def test_placement_rejects_overlap_and_smt(self):
        m = load('rubric_placement', 'hpc/rubric_placement.py')
        layout = {'hosts': {'a': {'cpus': [0, 2], 'core_ids': ['0:0', '0:1']}}}
        records = [dict(host='a', rank=0, threads=[dict(cpu=0, mask=[0])]),
                   dict(host='a', rank=1, threads=[dict(cpu=2, mask=[2])])]
        m.verify_placement(records, layout, 2, 1)
        records[1]['threads'][0] = dict(cpu=0, mask=[0])
        with self.assertRaises(ValueError):
            m.verify_placement(records, layout, 2, 1)
        layout['hosts']['a']['core_ids'] = ['0:0', '0:0']
        with self.assertRaises(ValueError):
            m.verify_placement(records, layout, 2, 1)

    def test_actual_backend_and_rank_placement_are_reported(self):
        r = subprocess.run([str(ROOT / 'build/kmeans_serial'), '--n', '13', '--k', '2',
                            '--iterations', '1'], text=True, capture_output=True, check=True)
        data = json.loads(r.stdout)
        self.assertEqual(data.get('backend'), 'cpu')
        self.assertEqual(len(data['placement']), 1)
        self.assertEqual(data['placement'][0]['rank'], 0)
        self.assertEqual(len(data['placement'][0]['threads']), 1)

    def test_generated_jobs_request_real_nodes_and_fail_without_environment(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'jobs'
            proc = subprocess.run([sys.executable, str(ROOT / 'hpc/rubric_jobs.py'),
                                   '--cores-per-node', '64', '--cpu-queue', 'parallel',
                                   '--gpu-queue', 'gpu', '--output', str(out)],
                                  text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(list(out.glob('*.pbs'))), 6)
            # Inspect the scheduler-facing resource contract, not arbitrary source strings.
            resources = [line for line in (out / 'strong.pbs').read_text().splitlines()
                         if line.startswith('#PBS -l')]
            self.assertIn('#PBS -l select=4:ncpus=64:mpiprocs=64:mem=8gb', resources)
            self.assertIn('#PBS -l place=scatter:excl', resources)
            gpu_resources = [line for line in (out / 'gpu.pbs').read_text().splitlines()
                             if line.startswith('#PBS -l')]
            self.assertIn('#PBS -l select=1:ncpus=8:mpiprocs=8:ngpus=1:mem=8gb', gpu_resources)

    def test_scaling_uses_declared_baselines_and_weak_throughput(self):
        m = load('rubric_analysis', 'scripts/rubric_analysis.py')
        strong = m.scaling_metrics('strong', p=4, seconds=25, serial=100, mpi_one=80)
        self.assertAlmostEqual(strong['speedup_serial'], 4)
        self.assertAlmostEqual(strong['efficiency_serial'], 1)
        self.assertAlmostEqual(strong['speedup_mpi'], 3.2)
        weak = m.scaling_metrics('weak', p=4, seconds=12, mpi_one=10)
        self.assertAlmostEqual(weak['weak_efficiency'], 5 / 6)
        self.assertAlmostEqual(weak['throughput_speedup'], 10 / 3)
        self.assertNotIn('speedup_serial', weak)

    def test_archive_rejects_missing_experiments(self):
        m = load('rubric_analysis', 'scripts/rubric_analysis.py')
        with self.assertRaises(ValueError):
            m.audit_records([], {})

    def test_complete_audit_rejects_duplicate_and_changed_input(self):
        import copy
        m = load('rubric_analysis', 'scripts/rubric_analysis.py')
        campaign = load('rubric_campaign', 'scripts/rubric_campaign.py')
        layout = dict(cores_per_node=64, hosts={
            'n%d' % h: dict(cpus=list(range(64)), core_ids=['0:%d' % i for i in range(64)])
            for h in range(4)})
        rows = []
        for suite in ('serial', 'strong', 'weak', 'hybrid', 'communication', 'gpu'):
            for profile in (False, True):
                for config in campaign.matrix(suite, 64, profile):
                    for repeat in range(5):
                        row = dict(config, repeat=repeat, run_id=suite, job_id=suite,
                                   development=False, campaign='rubric-202611', cores_per_node=64,
                                   source_manifest={'src/main.cpp': 'fixture'}, binary_sha256='fixture',
                                   backend='cuda' if config['variant'] == 'v4' else 'cpu',
                                   mode='fixed', iterations=20, warmup=2, seed=42, diagnostic=profile,
                                   skew=False, input='', counts=[config['n']] + [0] * (config['k'] - 1), init_indices=list(range(config['k'])),
                                   data_fingerprint='unit-test-fixture', kernel_seconds=1., total_seconds=2., sse=1.)
                        p, t = config['p'], config['t']
                        row['nodes'] = max(1, p * t // 64)
                        row['placement'] = [dict(host='n%d' % (r // (64 // t)), rank=r,
                            threads=[dict(cpu=(r % (64 // t)) * t + i,
                                          mask=[(r % (64 // t)) * t + i]) for i in range(t)]) for r in range(p)]
                        if profile:
                            row['profile_ranks'] = [dict(rank=r, kernel_seconds=1., phase_seconds={
                                'accumulate': .5, 'thread_merge': .1, 'mpi_reduce': .2,
                                'centroid_update': .01, 'control_bcast': .01}) for r in range(p)]
                            row['profile_critical_rank'] = 0
                        if config['variant'] == 'v4':
                            row['gpu'] = dict(uuid='unit-test-device', kernel_launches=40,
                                              phase_seconds=dict(h2d=.01, assignment=.4, merge=.1, d2h=.01))
                        rows.append(row)
        layouts = {suite: layout for suite in campaign.SUITES}
        self.assertEqual(len(m.audit_records(rows, layouts)), 70)
        with self.assertRaises(ValueError):
            m.audit_records(rows + [rows[0]], layouts)
        altered = copy.deepcopy(rows)
        altered[1]['data_fingerprint'] = 'changed'
        with self.assertRaises(ValueError):
            m.audit_records(altered, layouts)
        tables, profiles = m.summarize(m.audit_records(rows, layouts))
        self.assertEqual((len(tables), len(profiles)), (55, 15))
        import os
        if os.environ.get('TEST_PLOTS') == '1':
            from plot_rubric import plot
            output = ROOT / 'artifacts/rubric-implementation/plot-qa-unit-fixtures'
            output.mkdir(parents=True, exist_ok=True)
            plot(output, tables, profiles)
            for extension in ('png', 'pdf', 'svg'):
                self.assertEqual(len(list(output.glob('*.' + extension))), 6)
            self.assertTrue((output / 'captions.txt').is_file())

    def test_staged_source_is_isolated_and_midrun_edits_fail(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / 'source'
            proc = subprocess.run([sys.executable, str(ROOT / 'hpc/rubric_stage.py'),
                                   '--output', str(stage)], text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse((stage / 'build').exists())
            self.assertTrue((stage / 'src/cuda_backend.cu').is_file())
            (stage / 'build').mkdir()
            shutil.copy2(ROOT / 'build/kmeans_serial', stage / 'build/kmeans_serial')
            wrapper = Path(directory) / 'mutate.py'
            wrapper.write_text('import os,sys\nfrom pathlib import Path\n'
                               'p=Path(sys.argv[1]);p.write_text(p.read_text()+"\\n// concurrent edit\\n")\n'
                               'os.execv(sys.argv[2],sys.argv[2:])\n')
            import shlex
            launcher = shlex.join([sys.executable, str(wrapper), str(stage / 'src/main.cpp')])
            proc = subprocess.run([sys.executable, str(stage / 'scripts/rubric_campaign.py'),
                                   '--suite', 'serial', '--development', '--kind', 'ordinary',
                                   '--launcher', launcher, '--output', str(Path(directory) / 'run')],
                                  text=True, capture_output=True)
            self.assertNotEqual(proc.returncode, 0, 'Concurrent source edits were accepted')
            self.assertIn('changed', proc.stderr.lower())
            self.assertEqual((Path(directory) / 'run/raw.jsonl').read_text(), '')

    def test_offline_audit_requires_logs_and_actual_preserved_source(self):
        import hashlib
        import shutil
        import tempfile
        m = load('rubric_analysis', 'scripts/rubric_analysis.py')
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / 'runs/serial.fixture'
            probe, measurement, source = job / 'probe', job / 'measurements', job / 'source'
            probe.mkdir(parents=True); measurement.mkdir(); source.mkdir()
            manifest = m.source_manifest()
            for name in manifest:
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
            (job / 'job.pbs').write_text('unit test fixture, not a real job')
            (job / 'job.stdout').write_text('unit test fixture, not measured data')
            allocation = dict(cores_per_node=64, hosts={'a': dict(cpus=[0], core_ids=['0:0'])})
            allocation_text = json.dumps(allocation)
            (measurement / 'allocation.json').write_text(allocation_text)
            (probe / 'allocation.json').write_text(allocation_text)
            for name in ('PBS_NODEFILE', 'job.txt', 'queues.txt', 'mpi-launcher.txt',
                         'host-compiler.txt', 'mpi-flags.txt', 'inventory.txt', 'ties.txt',
                         'check-00.stdout', 'check-00.stderr'):
                (probe / name).write_text('unit test fixture')
            row = dict(run_id='fixture', suite='serial', variant='v0', invocation_id=0,
                       diagnostic=False, source_manifest=manifest, job_id='fixture', binary_sha256='fixture')
            (measurement / 'raw.jsonl').write_text(json.dumps(row) + '\n')
            (measurement / 'profiles.jsonl').write_text('')
            (measurement / 'source-manifest.json').write_text(json.dumps(manifest))
            (measurement / '000.stdout').write_text(json.dumps({}))
            (measurement / '000.stderr').write_text('')
            def hashes(path):
                return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in path.iterdir() if f.is_file()}
            ready = dict(source_manifest=manifest, allocation_sha256=hashlib.sha256(allocation_text.encode()).hexdigest(),
                         binary_manifest={'kmeans_serial': 'fixture'}, gpu_verified=False, verified_256=False,
                         checks=1, job_id='fixture', evidence_manifest=hashes(probe))
            (probe / 'preflight.json').write_text(json.dumps(ready))
            completion = dict(source_manifest=manifest, records=1, files=hashes(measurement))
            (measurement / 'completion.json').write_text(json.dumps(completion))
            self.assertEqual(len(m.read_runs(Path(directory) / 'runs')[0]), 1)
            old = (probe / 'inventory.txt').read_text()
            (probe / 'inventory.txt').unlink()
            with self.assertRaises(ValueError):
                m.read_runs(Path(directory) / 'runs')
            (probe / 'inventory.txt').write_text(old)
            changed = source / 'src/main.cpp'
            changed.write_text(changed.read_text() + '\n// changed preserved source\n')
            with self.assertRaises(ValueError):
                m.read_runs(Path(directory) / 'runs')

    def test_cpu_binary_rejects_v4_instead_of_falling_back(self):
        r = subprocess.run([str(ROOT / 'build/kmeans_serial'), '--variant', 'v4'],
                           text=True, capture_output=True)
        self.assertNotEqual(r.returncode, 0)
