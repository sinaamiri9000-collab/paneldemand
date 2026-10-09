"""Independent input perturbations of the fitted S&Y function, not native ratios."""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import unittest
from types import SimpleNamespace
import numpy as np
from scipy.stats import norm
from pyquaidsce.model import DemandData
from pyquaidsce.selection import FirstStageLayout
from pilot.common.specification_core import SpecificationCore
from pilot.specification_suite.specification_suite import inference_design
from pilot.specification_followup.direct_elasticities import DirectReference, finite_difference_audit, micro_direct


class DirectTests(unittest.TestCase):
    def setUp(self):
        r = np.random.default_rng(209); n, m, q = 24, 12, 3
        L = r.normal(0, .15, (n, m)); y = r.normal(3, .2, n)
        raw = r.normal(0, .15, (n, q)); cf = r.normal(0, .15, n)
        names = ['household_size', 'mean_head_age', 'mean_cf_residual']
        xsel = np.column_stack([L, y, raw, cf])
        tau = r.normal(0, .025, (m, xsel.shape[1]+1)); tau[:, -1] = .9
        k = xsel@tau[:, :-1].T+tau[:, -1]
        d = DemandData(L, y, r.dirichlet(np.ones(m)*4, n), np.zeros((n, 1)),
                       norm.cdf(k), norm.pdf(k), 1., cf)
        self.core = SpecificationCore(d, raw, [2])
        theta = r.normal(0, .002, self.core.spec.n_free)
        theta[self.core.base_slices['alpha']] = 1/m
        self.fit = SimpleNamespace(theta=theta)
        ordered = tuple([f'lnp_{j+1}' for j in range(m)]+['ln_expenditure']+names+['cf_residual'])
        layout = FirstStageLayout(ordered, ordered[:m], {c:j for j,c in enumerate(ordered[:m])}, m,
                                  {c:m+1+j for j,c in enumerate(names)}, len(ordered)-1, len(ordered))
        self.stage = {'data':d, 'Z':raw, 'centers':np.zeros(q), 'scales':np.ones(q),
                      'control_names':names, 'additive_columns':[2], 'tau':tau,
                      'selection_index':k, 'layout':layout,
                      'Xrf':np.column_stack([np.ones(n), r.normal(size=(n,2))]),
                      'rf_names':['constant','z','z2'], 'weights':np.ones(n)}
        self.design = inference_design(self.stage)

    def test_actual_share_derivatives_against_independent_current_input_changes(self):
        audit = finite_difference_audit(self.core, self.fit, self.stage, np.arange(24))
        self.assertLess(audit['max_absolute_error'], 3e-9)
        flat = self.core.fitted_derivatives(self.fit.theta, self.stage['tau'].ravel(),
                                           self.stage['layout'], self.stage['selection_index'])
        shaped = self.core.fitted_derivatives(self.fit.theta, self.stage['tau'],
                                             self.stage['layout'], self.stage['selection_index'])
        for a, b in zip(flat, shaped): np.testing.assert_array_equal(a, b)

    def test_direct_reference_and_generated_cf_channel(self):
        ref = DirectReference(self.core, self.fit, self.stage, self.design)
        ex = ref.evaluate(ref.point)
        theta, tau, k = ref.inputs(ref.point)
        mu = ref.core.fitted(theta)[0]
        dx, dp = ref.core.fitted_derivatives(theta, tau, self.stage['layout'], k)
        np.testing.assert_allclose(ex[:12], 1+dx[0]/mu, atol=1e-13)
        np.testing.assert_allclose(ex[12:156].reshape(12,12), dp[0]/mu[:,None]-np.eye(12), atol=1e-13)
        np.testing.assert_allclose(ref.core.data.cdf[0], norm.cdf(self.stage['selection_index'].mean(0)))
        J = ref.jacobian()
        # Reconstruct the RF perturbation in every observation before averaging:
        # this independently verifies its current-CF, mean-CF and Probit channels.
        oldcf = self.core.data.control_function.copy(); oldz = self.core.Z.copy()
        oldk = self.stage['selection_index'].copy(); h = 3e-6
        for j in range(self.design.Xr.shape[1]):
            val = []
            for sign in (1, -1):
                self.core.data.control_function = oldcf-sign*h*self.design.Xr[:,j]
                self.core.Z[:,2] = oldz[:,2]-sign*h*self.design.Xbar[:,j]
                newk = oldk-sign*h*(self.stage['tau'][:,self.design.cf_pos][None,:]*self.design.Xr[:,j,None]
                       +self.stage['tau'][:,self.design.mean_pos][None,:]*self.design.Xbar[:,j,None])
                ss = dict(self.stage); ss['selection_index'] = newk
                rr = DirectReference(self.core, self.fit, ss, self.design)
                val.append(rr.evaluate(rr.point))
            np.testing.assert_allclose(J[:,-self.design.Xr.shape[1]+j], (val[0]-val[1])/(2*h), rtol=2e-5, atol=3e-9)
        self.core.data.control_function = oldcf; self.core.Z[:] = oldz

    def test_aggregate_quantity_derivative_independently(self):
        summary = micro_direct(self.core, self.fit, self.stage, chunk=7)
        d = self.core.data; L = d.lnp.copy(); y = d.lnexp.copy(); k = self.stage['selection_index']; tau = self.stage['tau']
        values = []; h = 1e-6
        for sign in (1,-1):
            d.lnexp = y+sign*h
            d.cdf = norm.cdf(k+sign*h*tau[:,12]); d.pdf = norm.pdf(k+sign*h*tau[:,12])
            values.append(np.sum(np.exp(d.lnexp[:,None]-L)*self.core.fitted(self.fit.theta), axis=0))
        fd = (np.log(values[0])-np.log(values[1]))/(2*h)
        np.testing.assert_allclose(summary['aggregate_quantity_expenditure'], fd, rtol=2e-6, atol=2e-9)
        d.lnexp = y; d.cdf = norm.cdf(k); d.pdf = norm.pdf(k)


if __name__ == '__main__': unittest.main()
