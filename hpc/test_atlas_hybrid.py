"""Audit fixed-core placement, rejection paths, and launcher output association."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('hybrid', Path(__file__).with_name('atlas-hybrid-launch.py'))
hybrid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hybrid)


class HybridTests(unittest.TestCase):
    def setUp(self):
        cpus = list(range(40,46)) + list(range(86,92))
        self.allocation = dict(host='node', allowed_cpus=cpus,
                               topology={str(c):dict(socket=i//6,core=i%6) for i,c in enumerate(cpus)})
        self.plan = hybrid.build_plan(self.allocation)

    def records(self, p):
        config = self.plan['configurations'][str(p)]
        return [dict(rank=rank, p=p, t=config['t'], host='node', rank_cpus=cpus,
                     omp_places=','.join('{%d}'%c for c in cpus),
                     thread_probe=dict(openmp=201511, threads=[dict(tid=i,cpus=[c],current_cpu=c) for i,c in enumerate(cpus)]))
                for rank,cpus in enumerate(config['ranks'])]

    def test_socket_aware_fixed_core_partitions(self):
        for p,t in hybrid.PAIRS:
            self.assertEqual(hybrid.verify_records(self.plan,p,t,self.records(p))['placement_check'],'pass')
        self.assertEqual(self.plan['configurations']['3']['cross_socket_ranks'],[1])
        self.assertEqual(self.plan['configurations']['1']['cross_socket_ranks'],[0])
        for p in [2,4,6,12]:
            self.assertEqual(self.plan['configurations'][str(p)]['cross_socket_ranks'],[])

    def test_layout_uses_allocation_not_hardcoded_cpu_numbers(self):
        allocation=dict(host='node',allowed_cpus=list(range(12)),
                        topology={str(c):dict(socket=0,core=c) for c in range(12)})
        plan=hybrid.build_plan(allocation)
        self.assertTrue(all(not c['cross_socket_ranks'] for c in plan['configurations'].values()))
        self.assertEqual(plan['configurations']['2']['ranks'],[list(range(6)),list(range(6,12))])

    def test_sibling_hardware_threads_rejected(self):
        self.allocation['topology']['41']=dict(socket=0,core=0)
        with self.assertRaisesRegex(ValueError,'physical cores'):
            hybrid.build_plan(self.allocation)

    def test_thread_overlap_and_missing_core_rejected(self):
        records=self.records(6)
        records[0]['thread_probe']['threads'][1].update(cpus=[40],current_cpu=40)
        with self.assertRaisesRegex(ValueError,'overlap'):
            hybrid.verify_records(self.plan,6,2,records)

    def test_unbound_thread_rejected(self):
        records=self.records(6)
        records[0]['thread_probe']['threads'][0]['cpus']=[40,41]
        with self.assertRaisesRegex(ValueError,'one planned CPU'):
            hybrid.verify_records(self.plan,6,2,records)

    def test_outside_rank_cpu_and_wrong_host_rejected(self):
        for field,value in [('rank_cpus',[0,1]),('host','other-node')]:
            records=self.records(6);records[0][field]=value
            with self.assertRaises(ValueError):
                hybrid.verify_records(self.plan,6,2,records)

    def test_duplicate_rank_and_wrong_team_size_rejected(self):
        records=self.records(6);records[1]['rank']=0
        with self.assertRaisesRegex(ValueError,'MPI ranks'):
            hybrid.verify_records(self.plan,6,2,records)
        records=self.records(6);records[0]['thread_probe']['threads'].pop()
        with self.assertRaisesRegex(ValueError,'thread IDs'):
            hybrid.verify_records(self.plan,6,2,records)

    def test_parent_links_result_to_exact_placement_directory(self):
        with tempfile.TemporaryDirectory(prefix='hybrid paths ') as directory:
            folder=Path(directory); plan=folder/'plan.json';plan.write_text(json.dumps(self.plan))
            args=SimpleNamespace(output=folder/'placements',plan=plan,p=6,t=2,nodefile=folder/'node file',
                                 probe=folder/'probe',command=['/example/program','--n','100'])
            def launch(command,**kwargs):
                record_dir=Path(command[command.index('--directory')+1])
                for record in self.records(6):
                    (record_dir/('rank-%d.json'%record['rank'])).write_text(json.dumps(record))
                self.assertIn(str(args.nodefile),command)
                return subprocess.CompletedProcess(command,0,'{"kernel_seconds": 1.25}\n','')
            output=io.StringIO()
            with patch.object(hybrid.subprocess,'run',side_effect=launch),contextlib.redirect_stdout(output):
                hybrid.run(args)
            result=json.loads(output.getvalue())
            self.assertEqual(result['kernel_seconds'],1.25)
            self.assertEqual(result['placement_check'],'pass')
            check=json.loads((args.output/result['placement_id']/'check.json').read_text())
            self.assertEqual(check['t'],2)

    def test_rank_applies_mask_and_explicit_places_before_exec(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);plan=folder/'plan.json';plan.write_text(json.dumps(self.plan))
            args=SimpleNamespace(plan=plan,p=6,t=2,probe=folder/'probe',directory=folder,
                                 command=['/example/program','--threads','2'])
            probe=json.dumps(self.records(6)[0]['thread_probe'])
            with patch.dict(os.environ,{'OMPI_COMM_WORLD_RANK':'0','OMPI_COMM_WORLD_SIZE':'6'}), \
                    patch.object(hybrid.socket,'gethostname',return_value='node'), \
                    patch.object(hybrid.os,'sched_getaffinity',side_effect=[set(self.allocation['allowed_cpus']),{40,41}],create=True), \
                    patch.object(hybrid.os,'sched_setaffinity',create=True) as set_mask, \
                    patch.object(hybrid.subprocess,'run',return_value=subprocess.CompletedProcess([],0,probe,'')) as run_probe, \
                    patch.object(hybrid.os,'execvpe') as execute:
                hybrid.rank_launch(args)
                set_mask.assert_called_once_with(0,[40,41])
                self.assertEqual(run_probe.call_args.kwargs['env']['OMP_PLACES'],'{40},{41}')
                self.assertEqual(execute.call_args.args[2]['OMP_NUM_THREADS'],'2')
                self.assertEqual(json.loads((folder/'rank-0.json').read_text())['rank_cpus'],[40,41])


if __name__=='__main__':
    unittest.main(verbosity=2)
