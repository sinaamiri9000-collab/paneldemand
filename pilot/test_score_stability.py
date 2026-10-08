import unittest
import numpy as np
from plain_stability import robust_score_test


class ScoreTests(unittest.TestCase):
    def test_matches_cluster_robust_linear_restricted_residual_test(self):
        r = np.random.default_rng(92); n = 300
        x = r.normal(size=n); z = r.normal(size=n)
        X = np.column_stack([np.ones(n), x]); Z = np.column_stack([X, z])
        y = .2+.4*x+.12*z+r.normal(size=n)*(1+abs(x))
        residual = y-X@np.linalg.lstsq(X, y, rcond=None)[0]
        scores = (Z*residual[:, None]).reshape(-1, 3, 3).sum(1)
        actual = robust_score_test(Z.T@Z, scores, [2])
        z_resid = z-X@np.linalg.lstsq(X, z, rcond=None)[0]
        moment_by_household = (z_resid*residual).reshape(-1, 3).sum(1)
        expected = moment_by_household.sum()**2/(moment_by_household@moment_by_household)*99/100
        self.assertAlmostEqual(actual['statistic'], expected, places=10)
        self.assertEqual(actual['df'], 1)
        # Scaling and sign of the added parameter must not change the test.
        scaled = Z.copy(); scaled[:, 2] *= -4.7
        alternative = robust_score_test(scaled.T@scaled,
            (scaled*residual[:, None]).reshape(-1, 3, 3).sum(1), [2])
        self.assertAlmostEqual(actual['statistic'], alternative['statistic'], places=10)


if __name__ == '__main__': unittest.main()
