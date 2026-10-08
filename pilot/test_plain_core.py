import unittest
import numpy as np
from scipy.stats import norm
from panel_core import PanelCore
from plain_core import PlainCore


class PlainTests(unittest.TestCase):
    def setUp(self):
        r = np.random.default_rng(107); n, m = 18, 4
        panel = PanelCore(r.normal(0, .15, (n, m)), r.normal(3, .2, n),
            r.dirichlet(np.ones(m), n), norm.cdf(np.ones((n, m))), norm.pdf(np.ones((n, m))),
            r.normal(0, .1, n), r.normal(size=(n, 3)), 1)
        self.stage = {'data': panel.data, 'Z': panel.Z, 'control_names': ['age','mean_age','mean_cf_residual'],
                      'centers': np.zeros(3), 'scales': np.ones(3)}
        self.core = PlainCore(self.stage, np.repeat([0, 1], 9))
        self.th = r.normal(0, .015, self.core.spec.n_free)
        self.th[:3] = [.2, .3, .25]

    def test_fitted_jacobian_restrictions_and_gram(self):
        c = self.core; th = self.th
        f = c.full.fitted(c.expand(th))
        np.testing.assert_allclose(f.sum(1), 1, atol=2e-15)
        for reg in range(2):
            co, eta = c.coefs(th, reg)
            np.testing.assert_allclose(co.gamma.sum(1), 0, atol=2e-15)
            self.assertAlmostEqual(co.beta.sum(), 0)
            self.assertAlmostEqual(co.lam.sum(), 0)
            np.testing.assert_allclose(co.cfcoef, 0, atol=2e-15)
        J = c.jacobian(th)
        for j in range(len(th)):
            e = np.zeros_like(th); e[j] = 1e-6
            fd = (c.fitted(th+e)-c.fitted(th-e))/(2e-6)
            np.testing.assert_allclose(J[:, :, j], fd, rtol=2e-5, atol=2e-8)
        flat = J.reshape(-1, len(th)); res = (c.data.shares-c.fitted(th)).ravel()
        G, g, obj = c.normal(th, c.data, c.spec, None, np.eye(3), 6)
        np.testing.assert_allclose(G, flat.T@flat, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(g, flat.T@res, rtol=1e-12, atol=1e-12)
        self.assertAlmostEqual(obj, res@res)


if __name__ == '__main__': unittest.main()
