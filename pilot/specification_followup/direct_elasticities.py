"""Direct derivatives of the fitted translated QUAIDS/CF/SY conditional mean.

Means and CF inputs are fixed for current input partials. Reference-point
uncertainty propagates the expenditure/Probit stages; empirical reference inputs
are fixed. Micro distributions and quantity aggregates are descriptive outputs.
"""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import numpy as np
from scipy.stats import norm
from pyquaidsce.model import DemandData, _inner
from pyquaidsce.params import unpack
from pilot.common.specification_core import SpecificationCore


class DirectReference:
    def __init__(self, core, fit, stage, design):
        self.K = core.spec.n_free; self.Q = design.Xs.shape[1]; self.R = design.Xr.shape[1]
        self.stage, self.design = stage, design
        d = core.data
        self.base_z = core.Z.mean(0); self.base_cf = float(d.control_function.mean())
        self.base_k = stage['selection_index'].mean(0)
        self.xr = design.Xr.mean(0); self.xbar = design.Xbar.mean(0)
        self.xs = design.Xs.mean(0)
        tau = stage['tau']
        self.k_rf = -tau[:, design.cf_pos, None]*self.xr[None, :]
        if design.mean_pos >= 0:
            self.k_rf -= tau[:, design.mean_pos, None]*self.xbar[None, :]
        refdata = DemandData(d.lnp.mean(0)[None, :], np.array([d.lnexp.mean()]),
             d.shares.mean(0)[None, :], np.zeros((1, 1)), norm.cdf(self.base_k)[None, :],
             norm.pdf(self.base_k)[None, :], d.a0, np.array([self.base_cf]))
        self.core = SpecificationCore(refdata, self.base_z[None, :].copy(),
                                      np.flatnonzero(core.additive_columns))
        self.point = np.r_[fit.theta, design.tau_std.ravel(), np.zeros(self.R)]

    def inputs(self, parameters):
        ts = parameters[self.K:self.K+12*self.Q].reshape(12, self.Q)
        rf = parameters[self.K+12*self.Q:]
        dt = ts-self.design.tau_std
        tau = np.column_stack([ts[:, :-1]/self.design.sel_scale,
               ts[:, -1]-(ts[:, :-1]/self.design.sel_scale)@self.design.sel_center])
        k = self.base_k+dt@self.xs+self.k_rf@rf
        self.core.Z[0] = self.base_z
        if self.design.mean_z >= 0:
            self.core.Z[0, self.design.mean_z] -= self.xbar@rf/self.design.mean_z_scale
        self.core.data.control_function[0] = self.base_cf-self.xr@rf
        self.core.data.cdf[0] = norm.cdf(k); self.core.data.pdf[0] = norm.pdf(k)
        return parameters[:self.K], tau.ravel(), k[None, :]

    def evaluate(self, parameters):
        theta, tau, k = self.inputs(parameters)
        mu = self.core.fitted(theta)[0]
        if not np.isfinite(mu).all() or np.any(mu <= 0):
            raise ValueError('Direct reference elasticity requires positive fitted shares')
        dx, dp = self.core.fitted_derivatives(theta, tau, self.stage['layout'], k)
        ex = 1+dx[0]/mu
        mar = dp[0]/mu[:, None]-np.eye(12)
        # Diagnostic Slutsky convention only: raw SY is not exact adding-up.
        hick = mar+ex[:, None]*mu[None, :]
        nt, d, translate, additive = self.core.quantities(theta)
        c = unpack(nt, self.core.native); inn = _inner(c, d, self.core.native)
        g = inn.wstar[0]+translate[0]
        if np.any(g <= 0):
            raise ValueError('Latent reference elasticity requires positive QUAIDS shares')
        ga = c.alpha+translate[0]+c.gamma@d.lnp[0]
        gd = c.gamma-inn.S[0, :, None]*ga[None, :]-inn.T[0, :, None]*c.beta[None, :]
        lx = 1+inn.S[0]/g; lm = gd/g[:, None]-np.eye(12)
        return np.r_[ex, mar.ravel(), hick.ravel(), lx, lm.ravel()]

    def jacobian(self, step=1e-5):
        J = np.empty((456, len(self.point)))
        for j in range(len(self.point)):
            h = step*max(1., abs(self.point[j])); e = np.zeros_like(self.point); e[j] = h
            J[:, j] = (self.evaluate(self.point+e)-self.evaluate(self.point-e))/(2*h)
        self.evaluate(self.point)
        return J

    def point_diagnostics(self):
        self.evaluate(self.point)
        return {'predicted_shares': self.core.fitted(self.point[:self.K])[0],
                'predicted_share_sum': float(self.core.fitted(self.point[:self.K]).sum()),
                'mean_log_prices': self.core.data.lnp[0],
                'mean_log_expenditure': float(self.core.data.lnexp[0]),
                'mean_scaled_controls': self.base_z,
                'mean_cf_residual': self.base_cf,
                'fixed_a0': self.core.data.a0,
                'selection_cdf_at_mean_index': self.core.data.cdf[0],
                'selection_pdf_at_mean_index': self.core.data.pdf[0]}


def distribution(values):
    n = values.shape[0]; shape = values.shape[1:]
    cols = values.reshape(n, -1)
    out = {k: np.empty(cols.shape[1]) for k in ('mean', 'median', 'p01', 'p05', 'p95', 'p99', 'min', 'max', 'sd')}
    counts = np.zeros(cols.shape[1], int)
    for j in range(cols.shape[1]):
        a = cols[:, j]; a = a[np.isfinite(a)]; counts[j] = len(a)
        if not len(a): raise ValueError('No valid individual elasticities for a group')
        q = np.quantile(a, [0, .01, .05, .5, .95, .99, 1])
        for key, v in zip(('min','p01','p05','median','p95','p99','max'), q): out[key][j] = v
        out['mean'][j] = a.mean(); out['sd'][j] = a.std()
    out = {k: v.reshape(shape) for k, v in out.items()}
    out['valid_count'] = counts.reshape(shape)
    return out


def micro_direct(core, fit, stage, chunk=3000):
    n, m = core.data.shares.shape
    ee = np.full((n, m), np.nan); ep = np.full((n, m, m), np.nan)
    invalid = np.zeros(m, int); small = np.zeros(m, int); numerical = np.zeros(m, int)
    denominators = np.zeros(m); numx = np.zeros(m); nump = np.zeros((m, m))
    matched_rsum = []
    tau = stage['tau'].ravel(); layout = stage['layout']; k = stage['selection_index']
    for start in range(0, n, chunk):
        rows = slice(start, min(start+chunk,n)); mu = core.fitted(fit.theta, rows)
        dx, dp = core.fitted_derivatives(fit.theta, tau, layout, k, rows)
        positive = mu > 0
        invalid += (~positive).sum(0); small += ((mu > 0)&(mu < 1e-6)).sum(0)
        xe = np.full_like(mu, np.nan); pe = np.full_like(dp, np.nan)
        np.divide(dx, mu, out=xe, where=positive); xe += 1
        np.divide(dp, mu[:, :, None], out=pe, where=positive[:, :, None]); pe -= np.eye(m)[None, :, :]
        numerical += (positive&~np.isfinite(xe)).sum(0)
        ee[rows] = xe; ep[rows] = pe
        # Q_i = sum exp(y)/p_i * mu_i. We retain every fitted entry here.
        xp = np.exp(core.data.lnexp[rows, None]-core.data.lnp[rows])
        denominators += (xp*mu).sum(0); numx += (xp*dx).sum(0)
        nump += (xp[:, :, None]*dp).sum(0)
        matched_rsum.append(mu.sum(1))
    if np.any(denominators <= 0): raise ValueError('Nonpositive aggregate fitted quantity')
    return {'individual_expenditure': distribution(ee), 'individual_marshallian': distribution(ep),
            'nonpositive_fitted_share_count': invalid,
            'positive_share_below_1e_6_count': small,
            'nonfinite_expenditure_elasticity_among_positive_shares': numerical,
            'individual_abs_expenditure_over_100_count': (np.abs(ee)>100).sum(0),
            'aggregate_quantity_expenditure': 1+numx/denominators,
            'aggregate_quantity_marshallian': nump/denominators[:, None]-np.eye(m),
            'fitted_share_sum_quantiles': np.quantile(np.concatenate(matched_rsum),[0,.01,.5,.99,1]),
            'aggregation_definition': 'unweighted household-year total fitted quantity sum exp(y)/p_i * mu_i; fixed household means and CF; positive aggregate denominator; all fitted entries retained',
            'individual_definition': '1 + dmu_i/dlog(x)/mu_i; price dmu_i/dlog(p_j)/mu_i - identity; only mu_i>0 defines log response; no trimming or winsorization'}


def finite_difference_audit(core, fit, stage, rows, step=1e-6):
    """Independently perturb original log inputs and rebuild selection CDF/PDF."""
    local_data = core.data.subset(rows)
    local = SpecificationCore(local_data, core.Z[rows].copy(), np.flatnonzero(core.additive_columns))
    local_data = local.data
    k = stage['selection_index'][rows].copy(); layout = stage['layout']; tau = stage['tau'].ravel()
    dx, dp = local.fitted_derivatives(fit.theta, tau, layout, k)
    L = local_data.lnp.copy(); y = local_data.lnexp.copy()
    absolute = 0.; scaled = 0.
    try:
        for j in range(core.spec.neqn+1):
            slopes = np.array([layout.coefficient(tau, i, layout.price_position(j) if j<core.spec.neqn else layout.expenditure_position)
                               for i in range(core.spec.neqn)])
            preds = []
            for sign in (1,-1):
                local_data.lnp = L.copy(); local_data.lnexp = y.copy()
                if j < core.spec.neqn: local_data.lnp[:,j] += sign*step
                else: local_data.lnexp += sign*step
                local_data.cdf = norm.cdf(k+sign*step*slopes)
                local_data.pdf = norm.pdf(k+sign*step*slopes)
                preds.append(local.fitted(fit.theta))
            fd = (preds[0]-preds[1])/(2*step)
            analytic = dp[:,:,j] if j<core.spec.neqn else dx
            absolute = max(absolute, float(np.abs(fd-analytic).max()))
            scaled = max(scaled, float((np.abs(fd-analytic)/(1+np.abs(fd))).max()))
    finally:
        local_data.lnp = L; local_data.lnexp = y
        local_data.cdf = norm.cdf(k); local_data.pdf = norm.pdf(k)
    return {'observations_checked': len(L), 'step': step, 'max_absolute_error': absolute,
            'max_error_scaled_by_one_plus_derivative': scaled}
