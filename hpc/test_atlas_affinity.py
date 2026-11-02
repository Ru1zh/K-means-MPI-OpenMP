"""Reject placement that would invalidate a controlled scaling experiment."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('atlas_affinity',Path(__file__).with_name('atlas-affinity.py'))
affinity=importlib.util.module_from_spec(spec)
spec.loader.exec_module(affinity)


class AffinityTests(unittest.TestCase):
    def setUp(self):
        self.allocation=dict(host='node',allowed_cpus=[40,41,86,87])
        self.audits={p:[dict(rank=r,host='node',cpus=[self.allocation['allowed_cpus'][r]])
                        for r in range(p)] for p in [1,2,4]}

    def test_valid_disjoint_os_cpu_ids_and_baseline(self):
        result=affinity.verify(self.allocation,self.audits)
        self.assertEqual(result['baseline_cpu'],40)
        self.assertEqual(set(result['audits']),{'1','2','4'})

    def test_outside_allocation_rejected(self):
        self.audits[4][3]['cpus']=[88]
        with self.assertRaisesRegex(ValueError,'allocated OS CPU'):
            affinity.verify(self.allocation,self.audits)

    def test_overlapping_rank_cpu_rejected(self):
        self.audits[4][3]['cpus']=[86]
        with self.assertRaisesRegex(ValueError,'overlap'):
            affinity.verify(self.allocation,self.audits)

    def test_unbound_rank_rejected(self):
        self.audits[4][3]['cpus']=[86,87]
        with self.assertRaisesRegex(ValueError,'exactly one'):
            affinity.verify(self.allocation,self.audits)

    def test_missing_rank_rejected(self):
        self.audits[4].pop()
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            affinity.verify(self.allocation,self.audits)

    def test_baseline_cpu_drift_rejected(self):
        self.audits[2][0]['cpus']=[86]
        with self.assertRaisesRegex(ValueError,'changed CPU'):
            affinity.verify(self.allocation,self.audits)


if __name__=='__main__':
    unittest.main(verbosity=2)
