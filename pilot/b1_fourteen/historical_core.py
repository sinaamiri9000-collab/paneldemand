"""Period-specific beta/Gamma/lambda with the existing B1 CF/S&Y core.

All QUAIDS algebra and derivatives remain in pyquaidsce/SpecificationCore.
Normal equations are lifted from the three smaller, exact regime blocks.
"""
import numpy as np
from pilot.common.specification_core import SpecificationCore
from pilot.common.regime_core import RegimeSpec


class HistoricalCore(SpecificationCore):
    def __init__(self, data, Z, regimes, additive_columns=None, nregimes=3):
        super().__init__(data, Z, additive_columns)
        self.regimes = np.asarray(regimes, int)
        self.common_base = self.spec.nbase
        self.slope_indices = np.concatenate([
            np.arange(self.base_slices[b].start, self.base_slices[b].stop)
            for b in ('beta', 'gamma', 'lambda')])
        self.slope_width = len(self.slope_indices)
        self.spec = RegimeSpec(Z.shape[1], data.shares.shape[1], self.common_base,
                               nregimes-1, self.slope_width)
        self.pieces = {}
        for code in np.unique(self.regimes):
            mask = self.regimes == code
            self.pieces[int(code)] = SpecificationCore(data.subset(mask), Z[mask],
                                                       np.flatnonzero(self.additive_columns))

    def local_theta(self, theta, code):
        base = theta[:self.common_base].copy()
        if code:
            base[self.slope_indices] += theta[self.contrast_slice(code)]
        return np.r_[base, theta[self.spec.nbase:]]

    def fitted(self, theta, rows=slice(None)):
        indices = np.arange(self.data.nobs)[rows]
        result = np.empty((len(indices), self.spec.neqn))
        for code in np.unique(self.regimes[rows]):
            mask = self.regimes[rows] == code
            # Partial chunks use a temporary native view, not a dense Jacobian.
            d = self.data.subset(indices[mask])
            c = SpecificationCore(d, self.Z[indices[mask]],
                                  np.flatnonzero(self.additive_columns))
            result[mask] = c.fitted(self.local_theta(theta, int(code)))
        return result

    def jacobian(self, theta, rows=slice(None)):
        indices = np.arange(self.data.nobs)[rows]
        J = np.zeros((len(indices), self.spec.neqn, self.spec.n_free))
        for code in np.unique(self.regimes[rows]):
            mask = self.regimes[rows] == code
            c = SpecificationCore(self.data.subset(indices[mask]), self.Z[indices[mask]],
                                  np.flatnonzero(self.additive_columns))
            j = c.jacobian(self.local_theta(theta, int(code)))
            J[mask, :, :self.common_base] = j[:, :, :self.common_base]
            J[mask, :, self.spec.nbase:] = j[:, :, self.common_base:]
            if code: J[mask, :, self.contrast_slice(int(code))] = j[:, :, self.slope_indices]
        return J

    def normal(self, theta, d, spec, cache, P, chunk, deadline=None):
        G = np.zeros((self.spec.n_free, self.spec.n_free))
        g = np.zeros(self.spec.n_free); objective = 0.
        for code, c in self.pieces.items():
            gl, sl, ol = c.normal(self.local_theta(theta, code), c.data, c.spec,
                                  c.cache, P, chunk, deadline)
            gi = np.r_[np.arange(self.common_base),
                       np.arange(self.spec.nbase, self.spec.n_free)]
            li = np.arange(c.spec.n_free)
            if code:
                gi = np.r_[gi, np.arange(self.contrast_slice(code).start,
                                        self.contrast_slice(code).stop)]
                li = np.r_[li, self.slope_indices]
            G[np.ix_(gi, gi)] += gl[np.ix_(li, li)]
            g[gi] += sl[li]; objective += ol
        return G, g, objective

    def fitted_derivatives(self, theta, tau, layout, selection_index, rows=slice(None)):
        indices = np.arange(self.data.nobs)[rows]
        dx = np.empty((len(indices), self.spec.neqn))
        dp = np.empty((len(indices), self.spec.neqn, self.spec.neqn))
        for code in np.unique(self.regimes[rows]):
            mask = self.regimes[rows] == code
            c = SpecificationCore(self.data.subset(indices[mask]), self.Z[indices[mask]],
                                  np.flatnonzero(self.additive_columns))
            effective_tau = tau[int(code)] if np.asarray(tau).ndim == 3 else tau
            xx, pp = c.fitted_derivatives(self.local_theta(theta, int(code)),
                         effective_tau, layout, selection_index[indices[mask]])
            dx[mask], dp[mask] = xx, pp
        return dx, dp
