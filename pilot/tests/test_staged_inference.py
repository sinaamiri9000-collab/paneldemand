"""Independent score differences for the stacked covariance Jacobian."""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import unittest
import numpy as np
from scipy.stats import norm
from pyquaidsce.probit import _lambda_ratio
from pilot.common.regime_core import RegimeCore
from pilot.common.panel_core import PanelCore
from pilot.common.staged_inference import residual_hessian, input_score_derivatives, probit_components


class StackedTests(unittest.TestCase):
    def setUp(self):
        r = np.random.default_rng(1397); n, m = 18, 4
        self.k = r.normal(.5, .3, (n, m))
        base = PanelCore(r.normal(0, .2, (n, m)), r.normal(3, .2, n),
                         r.dirichlet(np.ones(m), n), norm.cdf(self.k), norm.pdf(self.k),
                         r.normal(0, .2, n), r.normal(0, .2, (n, 2)), 1)
        self.core = RegimeCore(base.data, base.Z, np.repeat([0, 1], 9))
        self.th = r.normal(0, .02, self.core.spec.n_free)
        self.th[self.core.base_slices['alpha']] = [.2, .3, .25]
        a = r.normal(size=(m, m))
        self.W = np.linalg.inv(a@a.T+np.eye(m))
        self.Xr = np.column_stack([np.ones(n), r.normal(size=(n, 2))])
        self.Xbar = np.repeat(self.Xr.reshape(-1, 3, 3).mean(1), 3, axis=0)

    def score(self, theta=None):
        if theta is None: theta = self.th
        J = self.core.jacobian(theta)
        u = self.core.data.shares-self.core.fitted(theta)
        return np.einsum('nik,ni->k', J, u@self.W)

    def test_exact_structural_bread(self):
        J = self.core.jacobian(self.th)
        u = self.core.data.shares-self.core.fitted(self.th)
        G = np.einsum('nik,ij,njl->kl', J, self.W, J)
        A = G-residual_hessian(self.core, self.th, slice(None), u@self.W)
        fd = np.empty_like(A)
        for j in range(len(self.th)):
            e = np.zeros_like(self.th); e[j] = 1e-6
            fd[:, j] = -(self.score(self.th+e)-self.score(self.th-e))/(2e-6)
        np.testing.assert_allclose(A, fd, rtol=3e-5, atol=2e-8)

    def test_input_score_derivatives(self):
        c = self.core; d = c.data
        J, JW, u, Wu, sk, sv, sm, *rest = input_score_derivatives(
            c, self.th, slice(None), self.k, self.W, 1, 1.7)
        eps = 1e-6
        for i in range(c.spec.neqn):
            direction = self.Xr[:, 1]
            results = []
            for sign in [1, -1]:
                kp = self.k.copy(); kp[:, i] += sign*eps*direction
                d.cdf = norm.cdf(kp); d.pdf = norm.pdf(kp)
                results.append(self.score())
            d.cdf = norm.cdf(self.k); d.pdf = norm.pdf(self.k)
            np.testing.assert_allclose(sk[:, i].T@direction,
                                       (results[0]-results[1])/(2*eps), rtol=2e-5, atol=2e-8)
        for name, predicted in [('v', sv), ('mean', sm)]:
            original = d.control_function.copy() if name == 'v' else c.Z[:, 1].copy()
            direction = self.Xr[:, 2]; results = []
            for sign in [1, -1]:
                if name == 'v': d.control_function = original+sign*eps*direction
                else: c.Z[:, 1] = original+sign*eps*direction/1.7
                results.append(self.score())
            if name == 'v': d.control_function = original
            else: c.Z[:, 1] = original
            np.testing.assert_allclose(predicted.T@direction,
                                       (results[0]-results[1])/(2*eps), rtol=2e-5, atol=2e-8)

    def test_probit_rf_cross_jacobian(self):
        r = np.random.default_rng(43); Xs = r.normal(size=(18, 5)); Xs[:, -1] = 1
        tau_std = np.array([.2, -.1, .3, -.2, .4]); scale = np.array([1.1, .8, 1.2, 1.6])
        cf, mean = 2, 3
        tc, tm = tau_std[cf]/scale[cf], tau_std[mean]/scale[mean]
        y = (np.arange(18) % 3 != 1).astype(float); q = 2*y-1
        _, _, cross = probit_components(Xs, Xs@tau_std, y, self.Xr, self.Xbar,
                                         tc, tm, cf, mean, scale)
        for j in range(3):
            values = []; eps = 1e-6
            for sign in [1, -1]:
                xp = Xs.copy()
                xp[:, cf] -= sign*eps*self.Xr[:, j]/scale[cf]
                xp[:, mean] -= sign*eps*self.Xbar[:, j]/scale[mean]
                values.append(xp.T@(q*_lambda_ratio(q*(xp@tau_std))))
            np.testing.assert_allclose(cross[:, j], (values[0]-values[1])/(2*eps),
                                       rtol=2e-5, atol=2e-8)

    def test_ifgnls_covariance_feedback(self):
        c = self.core; J = c.jacobian(self.th)
        u = c.data.shares-c.fitted(self.th); Wu = u@self.W
        JW = np.einsum('ij,njk->nik', self.W, J)
        sigma = np.linalg.inv(self.W); eps = 1e-6
        for a, b in [(0, 0), (1, 3)]:
            e = np.zeros_like(sigma); e[a, b] = 1; e[b, a] = 1
            analytic = -np.einsum('nk,n->k', JW[:, a], Wu[:, b])
            if a != b: analytic -= np.einsum('nk,n->k', JW[:, b], Wu[:, a])
            def score(S): return np.einsum('nik,ni->k', J, u@np.linalg.inv(S))
            fd = (score(sigma+eps*e)-score(sigma-eps*e))/(2*eps)
            np.testing.assert_allclose(analytic, fd, rtol=2e-5, atol=2e-8)
        for j in [0, c.base_slices['gamma'].start, c.spec.nbase+2]:
            analytic = -np.einsum('ni,nj->ij', J[:, :, j], u)
            analytic += analytic.T
            e = np.zeros_like(self.th); e[j] = eps
            up = c.data.shares-c.fitted(self.th+e); um = c.data.shares-c.fitted(self.th-e)
            fd = (up.T@up-um.T@um)/(2*eps)
            np.testing.assert_allclose(analytic, fd, rtol=2e-5, atol=2e-8)


if __name__ == '__main__': unittest.main()
