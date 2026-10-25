"""Catch wrong baselines, pooling across jobs and lost repeat evidence in figures."""
import csv
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


def plotting_module():
    sys.path.insert(0, str(ROOT/'scripts'))
    try:
        spec = importlib.util.spec_from_file_location('atlas_plots', ROOT/'scripts/plot_atlas.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class AtlasPlotTests(unittest.TestCase):
    def test_median_and_observed_ranges_are_not_means_or_confidence_intervals(self):
        self.assertTrue((ROOT/'scripts/plot_atlas.py').exists(), 'Plotting entry point is missing')
        plots = plotting_module()
        result = plots.describe_times([9.0, 1.0, 3.0, 2.0, 4.0])
        self.assertEqual(result['median_seconds'], 3.0)
        self.assertEqual(result['min_seconds'], 1.0)
        self.assertEqual(result['max_seconds'], 9.0)
        self.assertEqual(result['repeats'], 5)

    def test_speedup_efficiency_and_time_change_use_the_selected_reference(self):
        self.assertTrue((ROOT/'scripts/plot_atlas.py').exists(), 'Plotting entry point is missing')
        plots = plotting_module()
        result = plots.compare(12.0, plots.describe_times([2, 3, 3, 3, 4]), cores=4)
        self.assertEqual(result['speedup'], 4.0)
        self.assertEqual(result['efficiency'], 1.0)
        self.assertEqual(result['time_change_pct'], -75.0)
        self.assertEqual(result['speedup_min'], 3.0)
        self.assertEqual(result['speedup_max'], 6.0)

    def test_mixed_jobs_and_duplicate_repeats_are_rejected(self):
        self.assertTrue((ROOT/'scripts/plot_atlas.py').exists(), 'Plotting entry point is missing')
        plots = plotting_module()
        bundle = ROOT/'benchmarks/atlas'
        manifest = json.loads((bundle/'manifest.json').read_text())
        study = manifest['studies']['strong']
        rows = [json.loads(line) for line in (bundle/study['directory']/study['raw_file']).read_text().splitlines()]
        mixed = copy.deepcopy(rows)
        mixed[0]['job_id'] = 'another-job'
        with self.assertRaisesRegex(ValueError, 'job'):
            plots.summarize_study('strong', mixed, manifest['workload'])
        duplicated = copy.deepcopy(rows)
        group = [r for r in duplicated if r['variant']=='v0']
        group[0]['repeat'] = group[1]['repeat']
        with self.assertRaisesRegex(ValueError, 'repeat'):
            plots.summarize_study('strong', duplicated, manifest['workload'])

    def test_tables_only_cli_preserves_all_configurations_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='atlas plot paths ') as directory:
            output = Path(directory)/'report'
            command = [sys.executable, str(ROOT/'scripts/plot_atlas.py'),
                       '--tables-only', '--output', str(output)]
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with (output/'configuration_summary.csv').open() as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 25)
            self.assertEqual(sum(int(r['repeats']) for r in rows), 125)
            with (output/'comparison_summary.csv').open() as source:
                comparisons = list(csv.DictReader(source))
            target = next(r for r in comparisons if r['study']=='strong' and r['p']=='12')
            self.assertAlmostEqual(float(target['speedup']), 11.82441896500566)
            self.assertAlmostEqual(float(target['efficiency']), 0.9853682470838051)
            before = (output/'configuration_summary.csv').read_bytes()
            second = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual((output/'configuration_summary.csv').read_bytes(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
