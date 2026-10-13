"""Check estimand alignment and published values against frozen source outputs."""
import hashlib
import json
import unittest
from pathlib import Path
import numpy as np
import openpyxl

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


class Comparisons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = json.loads((OUT/'results.json').read_text())
        cls.source = ROOT/'pilot/b1_fourteen_no_mean_cf/results.json'
        cls.original = {r['specification']['name']: r for r in json.loads(cls.source.read_text())['runs']}
        cls.manifest = json.loads((ROOT/'pilot/b1_fourteen/manifest.json').read_text())

    def test_frozen_parameters_and_samples(self):
        self.assertEqual(self.results['source_results_sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(len(self.results['runs']), 4)
        for name, run in self.results['runs'].items():
            self.assertEqual(run['sample'], self.original[name]['sample'])
            self.assertFalse(run['verification']['model_reestimated'])
            sample = self.original[name]['specification']['sample']
            self.assertEqual(run['sample_hash'], self.manifest['sample'][sample]['sample_hash'])

    def test_weights_use_original_counts_equal_for_both_models(self):
        for sample in ('All', 'B'):
            years = self.manifest['sample'][sample]['by_year']
            counts = [sum(n for y, n in years.items() if lo <= int(y) <= hi)
                      for lo, hi in [(1392, 1396), (1397, 1398), (1399, 1403)]]
            for model in ('common', 'history'):
                run = self.results['runs'][f'CS_{sample}_{model}']
                np.testing.assert_allclose(run['period_weights'], np.array(counts)/sum(counts), atol=1e-14)
                self.assertEqual([run['method3'][f'period_{i}']['rows'] for i in range(3)], counts)

    def test_raw_reference_prices_and_expenditure_match_between_models(self):
        for sample in ('All', 'B'):
            common = self.results['runs'][f'CS_{sample}_common']
            history = self.results['runs'][f'CS_{sample}_history']
            for method in ('method1_period_points', 'method2_reference_points'):
                for code in ('0', '1', '2'):
                    for key in ('log_prices', 'log_expenditure'):
                        np.testing.assert_allclose(common[method][code][key], history[method][code][key], rtol=0, atol=1e-12)

    def test_original_points_and_contract_are_reproduced(self):
        for name, run in self.results['runs'].items():
            original = self.original[name]['elasticities']
            for key in ('expenditure', 'marshallian'):
                if name.endswith('common'):
                    np.testing.assert_allclose(run['method2_overall'][key], original['overall'][key], rtol=0, atol=2e-9)
                else:
                    np.testing.assert_allclose(run['method1_overall'][key], original['overall'][key], rtol=0, atol=2e-9)
                    for i in range(3):
                        np.testing.assert_allclose(run['method1_period_points'][str(i)][key], original[f'period_{i}'][key], rtol=0, atol=2e-9)
                        np.testing.assert_allclose(run['method2_reference_points'][str(i)][key], original[f'common_reference_period_{i}'][key], rtol=0, atol=2e-9)

    def test_valid_support_and_period_mean_aggregation(self):
        for name, run in self.results['runs'].items():
            full = run['method3']['overall']
            expected = np.array(self.original[name]['convergence']['prediction_negative_fraction_by_group'])*full['rows']
            np.testing.assert_allclose(full['invalid_share_count'], expected, rtol=0, atol=1e-8)
            for field in ('expenditure', 'own_price'):
                counts = np.array([run['method3'][f'period_{i}'][field]['valid_count'] for i in range(3)])
                means = np.array([run['method3'][f'period_{i}'][field]['mean'] for i in range(3)])
                np.testing.assert_array_equal(counts.sum(axis=0), full[field]['valid_count'])
                np.testing.assert_allclose((means*counts).sum(axis=0)/counts.sum(axis=0), full[field]['mean'], rtol=1e-10, atol=1e-10)
        for sample, comparison in self.results['comparisons'].items():
            for label, pair in comparison['method3_paired_valid'].items():
                for field, stats in pair.items():
                    for model in ('common', 'history'):
                        counts = self.results['runs'][f'CS_{sample}_{model}']['method3'][label][field]['valid_count']
                        self.assertTrue(np.all(np.array(stats['valid_pair_count']) <= counts))
                    np.testing.assert_allclose(np.array(stats['historical_mean'])-stats['common_mean'], stats['mean_difference'], rtol=0, atol=1e-10)

    def test_summary_decomposition_and_numerical_derivatives(self):
        for comparison in self.results['comparisons'].values():
            for key in ('expenditure', 'marshallian'):
                np.testing.assert_allclose(np.array(comparison['method1'][key])+comparison['common_summary_method_effect'][key], comparison['old_comparison'][key], rtol=0, atol=2e-9)
        for run in self.results['runs'].values():
            for audit in run['verification']['individual_derivative_audits']:
                self.assertLess(audit['max_absolute_error'], 1e-7)
                self.assertGreater(audit['observations_checked'], 0)

    def test_excel_observation_comparisons(self):
        book = openpyxl.load_workbook(OUT/'CS_common_history_three_methods.xlsx', data_only=True)
        for sample in ('All', 'B'):
            common = self.results['runs'][f'CS_{sample}_common']['method3']['overall']
            history = self.results['runs'][f'CS_{sample}_history']['method3']['overall']
            for stat in ('mean', 'median'):
                sheet = book[f'{sample}_{stat}']
                for i in range(12):
                    values = [common['expenditure'][stat][i], history['expenditure'][stat][i],
                              history['expenditure'][stat][i]-common['expenditure'][stat][i],
                              common['own_price'][stat][i], history['own_price'][stat][i],
                              history['own_price'][stat][i]-common['own_price'][stat][i]]
                    for j, value in enumerate(values, 2):
                        self.assertAlmostEqual(sheet.cell(i+2, j).value, value, places=12)


if __name__ == '__main__': unittest.main()
