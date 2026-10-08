"""Economic equivalence must not be inferred from a nonsignificant difference."""
import unittest
import numpy as np
from frame_results import economic_comparison, holm


class EconomicTests(unittest.TestCase):
    def test_distinguishes_small_significant_large_and_imprecise(self):
        diff = {'expenditure': np.array([.03, 0., .4]), 'marshallian': np.diag([.03, 0., .4])}
        se = {'expenditure': np.array([.01, .2, .01]), 'marshallian': np.diag([.01, .2, .01])}
        rows = economic_comparison(diff, se)
        small, uncertain, large = rows[:3]
        self.assertLess(small['pvalue_zero_holm_24'], .05)
        self.assertTrue(small['margin_results']['0.1']['equivalent_after_holm'])
        self.assertGreater(uncertain['pvalue_zero_holm_24'], .05)
        self.assertFalse(uncertain['margin_results']['0.1']['equivalent_after_holm'])
        self.assertTrue(large['margin_results']['0.1']['difference_beyond_margin_after_holm'])
        self.assertAlmostEqual(small['quantity_response_gap_pp_for_10pct_shock'], .3)

    def test_holm_known_ordered_example(self):
        np.testing.assert_allclose(holm([.04, .01, .03]), [.06, .03, .06])


if __name__ == '__main__': unittest.main()
