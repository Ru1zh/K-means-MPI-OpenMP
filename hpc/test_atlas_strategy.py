"""Check paired-study coverage and numerical validation/error reporting."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

spec=importlib.util.spec_from_file_location('strategy',Path(__file__).with_name('atlas-strategy-study.py'))
study=importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.reference=dict(n=4,d=1,k=2,seed=42,iterations=5,warmup=2,
                            data_fingerprint='fixture',init_indices=[0,2],counts=[2,2],
                            sse=4.0,labels=[0,0,1,1],centers=[1.0,11.0])

    def test_thread_study_changes_only_variant_within_each_layout(self):
        configs=study.configurations('threads',[2,4,6])
        self.assertEqual(len(configs),6)
        for p in [2,4,6]:
            pair=[c for c in configs if c['p']==p]
            self.assertEqual({c['variant'] for c in pair},{'v2','v3'})
            self.assertEqual({(c['p']*c['t'],c['communication']) for c in pair},{(12,'allreduce')})

    def test_communication_study_changes_only_collective(self):
        configs=study.configurations('communication',[2,4,6])
        self.assertEqual(len(configs),6)
        for p in [2,4,6]:
            pair=[c for c in configs if c['p']==p]
            self.assertEqual({c['communication'] for c in pair},{'allreduce','reduce-bcast'})
            self.assertEqual({(c['variant'],c['p']*c['t']) for c in pair},{('v3',12)})

    def test_invalid_or_duplicate_processes_rejected(self):
        for processes in [[],[2,2],[5],[0],[24]]:
            with self.subTest(processes=processes),self.assertRaises(ValueError):
                study.configurations('threads',processes)

    def test_default_cli_plan_matches_data_spec(self):
        data=json.loads(Path(__file__).with_name('atlas-data-spec.json').read_text())
        for kind in ['threads','communication']:
            output=subprocess.check_output([sys.executable,str(Path(study.__file__)),
                                            '--kind',kind,'--dry-run'],text=True)
            plan=json.loads(output)
            self.assertEqual(plan['records'],30)
            for field in ['n','d','k','seed','warmup','iterations','repeats']:
                self.assertEqual(plan[field],data[field])

    def test_error_values_are_exported_for_small_reference(self):
        row=copy.deepcopy(self.reference);row['centers'][0]+=1e-9;row['sse']+=1e-11
        result=study.numerical_errors(self.reference,row,dump=True)
        self.assertGreater(result['max_centroid_absolute_error'],0)
        self.assertGreater(result['sse_scaled_error'],0)
        self.assertTrue(result['identical_counts'])

    def test_different_data_or_initialization_rejected(self):
        for field,value in [('data_fingerprint','other'),('init_indices',[1,3]),('iterations',6)]:
            row=copy.deepcopy(self.reference);row[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'reference mismatch'):
                study.numerical_errors(self.reference,row)

    def test_bad_objective_and_cluster_counts_rejected(self):
        for field,value in [('sse',float('nan')),('sse',4.01),('counts',[4]),('counts',[3,0])]:
            row=copy.deepcopy(self.reference);row[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                study.numerical_errors(self.reference,row)

    def test_small_labels_and_large_centroid_error_rejected(self):
        for field,value in [('labels',[0,1,1,1]),('centers',[2.0,11.0])]:
            row=copy.deepcopy(self.reference);row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                study.numerical_errors(self.reference,row,dump=True)


if __name__=='__main__':
    unittest.main(verbosity=2)
