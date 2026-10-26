"""Runner contracts; launch results are fixtures, never Atlas measurements."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import io
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def runner():
    spec = importlib.util.spec_from_file_location('thread_study', HERE/'atlas-thread-scaling.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ThreadStudyTests(unittest.TestCase):
    def test_dry_run_complete_separate_matrix_and_deterministic_order(self):
        proc = subprocess.run([sys.executable, str(HERE/'atlas-thread-scaling.py'), '--dry-run'],
                              text=True, capture_output=True, check=True)
        plan = json.loads(proc.stdout)
        self.assertEqual((plan['p'], plan['threads'], plan['repeats']), (2, [1,2,3,4,6], 5))
        self.assertEqual(plan['expected_timing_records'], 50)
        self.assertEqual(plan['expected_profile_records'], 50)
        for mode in ['timing', 'profile']:
            cells = {(r['variant'], r['t'], r['repeat']) for r in plan['execution_order'][mode]}
            self.assertEqual(cells, {(v,t,r) for v in ['v2','v3'] for t in [1,2,3,4,6] for r in range(5)})
        self.assertEqual(plan, runner().study_plan())

    def test_runner_separates_streams_and_preserves_reference_and_preflight(self):
        module = runner()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder/'layout-plan.json').write_text(json.dumps({'reserved_ranks': [[0,1,2,3,4,5],[6,7,8,9,10,11]]}))
            args = argparse.Namespace(directory=folder, nodefile=folder/'nodefile')
            def fixture(command, path):
                def option(name, default):
                    return command[command.index(name)+1] if name in command else default
                n = int(option('--n', '1000000'))
                row = dict(n=n,d=int(option('--d','32')),k=int(option('--k','32')),seed=42,
                           iterations=int(option('--iterations','20')),warmup=2,
                           data_fingerprint='fixture',init_indices=list(range(int(option('--k','32')))),
                           counts=[n]+[0]*(int(option('--k','32'))-1),sse=1.,kernel_seconds=1.,
                           p=2 if '--variant' in command else 1,t=int(option('--threads','1')),
                           variant=option('--variant','v0'),communication='allreduce',mode='fixed',
                           diagnostic='--profile' in command,stop_reason='fixed_iterations',
                           requested_iterations=int(option('--iterations','20')),
                           placement_id='launch-'+path.stem,placement_check='pass',
                           compiler='fixture',mpi_version='fixture',labels=[0]*n if n==37 else [],
                           centers=[0.]*(int(option('--k','32'))*int(option('--d','32'))))
                path.write_text(json.dumps(row))
                return row
            with patch.object(module, 'run_json', side_effect=fixture), patch.dict('os.environ', PBS_JOBID='fixture'), patch('sys.stdout', new_callable=io.StringIO):
                result = module.run(args)
            self.assertEqual(result['timing_records'], 50)
            self.assertEqual(result['profile_records'], 50)
            for mode in ['timing','profile']:
                rows = [json.loads(s) for s in (folder/(mode+'.jsonl')).read_text().splitlines()]
                self.assertEqual(len(rows), 50)
                self.assertTrue(all(r['diagnostic'] == (mode=='profile') and r['measurement_mode']==mode for r in rows))
                self.assertTrue(all(r['job_id']=='fixture' for r in rows))
            self.assertTrue((folder/'reference-large.json').exists())
            self.assertEqual(json.loads((folder/'preflight-check.json').read_text())['configurations'], 20)
            with patch.dict('os.environ', PBS_JOBID='fixture'), self.assertRaises(FileExistsError):
                module.run(args)

    def test_reject_nonfinite_or_changed_numerical_reference(self):
        module = runner()
        ref = dict(n=37,d=3,k=4,seed=42,iterations=5,warmup=2,data_fingerprint='x',
                   init_indices=[0,1,2,3],counts=[37,0,0,0],sse=1.)
        for change in [dict(sse=float('nan')), dict(counts=[36,1,0,0]),dict(data_fingerprint='y')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.check_numerical(ref, dict(ref,**change))

    def test_pbs_restart_refuses_existing_directory_without_truncating_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'results/atlas-thread-scaling.fixture'
            directory.mkdir(parents=True)
            (directory/'status.txt').write_text('original status\n')
            (directory/'environment.txt').write_text('original environment\n')
            with patch.dict('os.environ', PBS_JOBID='fixture', PBS_O_WORKDIR=tmp):
                result = subprocess.run(['bash',str(HERE/'atlas-thread-scaling.pbs')],text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual((directory/'status.txt').read_text(),'original status\n')
            self.assertEqual((directory/'environment.txt').read_text(),'original environment\n')

    def test_package_contains_new_entrypoint_and_all_runtime_dependencies(self):
        spec = importlib.util.spec_from_file_location('package_builder', HERE/'build-atlas-strategy-packages.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        files = builder.package_files('thread-scaling')
        for name in ['atlas-thread-scaling.pbs','atlas-thread-scaling.py','atlas-thread-scaling-launch.py',
                     'analyze-atlas-thread-scaling.py','atlas-affinity.py','atlas-hybrid-launch.py',
                     'atlas-thread-probe.cpp','Makefile','src/main.cpp','study-default-plan.json',
                     'hpc/THREAD_SCALING_GUIDE.md','hpc/THREAD_SCALING_GUIDE.zh-CN.md','hpc/THREAD_SCALING_GUIDE.ko.md']:
            self.assertIn(name,files)
        self.assertEqual(json.loads(files['study-default-plan.json'])['expected_profile_records'],50)


if __name__ == '__main__':
    unittest.main()
