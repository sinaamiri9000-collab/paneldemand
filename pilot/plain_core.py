"""QUAIDS stability sensitivity without censoring or control-function stages.

The twelfth equation is omitted because observed shares add exactly to one.
The existing restricted algebra and translated-alpha layer are reused through
an affine parameter selection. This is an uncensored, potentially endogenous
QUAIDS sensitivity, not a replacement for the maintained censored estimator.
"""
from dataclasses import dataclass
import numpy as np
from panel_core import PanelCore
from regime_core import RegimeCore
from pyquaidsce.model import DemandData
from pyquaidsce.params import Spec, unpack


@dataclass
class PlainSpec:
    neqn: int
    nshift: int
    nbase: int
    @property
    def n_free(self): return self.nbase+self.nshift*(self.neqn-1)
    @property
    def n_eq_estimated(self): return self.neqn-1


class PlainCore(PanelCore):
    def __init__(self, stage, regimes, blocks=('beta', 'gamma', 'lambda')):
        original = stage['data']; m = original.lnp.shape[1]
        keep = [i for i, name in enumerate(stage['control_names']) if name != 'mean_cf_residual']
        Z = stage['Z'][:, keep].copy()
        full_data = DemandData(original.lnp, original.lnexp, original.shares,
            np.zeros((original.nobs, 1)), np.ones((original.nobs, m)),
            np.zeros((original.nobs, m)), original.a0, np.zeros(original.nobs))
        self.full = RegimeCore(full_data, Z, regimes, blocks)
        common = self.full.base_slices['lambda'].stop
        base_indices = np.r_[np.arange(common),
                              np.arange(self.full.common_base, self.full.spec.nbase)]
        self.indices = np.r_[base_indices, np.arange(self.full.spec.nbase, self.full.spec.n_free)]
        self.base_indices = base_indices
        self.spec = PlainSpec(m, len(keep), len(base_indices))
        self.native = Spec(m, 1, True, False, False)
        self.Z = Z; self.B = self.full.B
        self.base_slices = {key: self.full.base_slices[key] for key in ['alpha','beta','gamma','lambda']}
        self.common_base = common
        self.blocks = self.full.blocks; self.slope_width = self.full.slope_width
        self.regimes = self.full.regimes
        self.control_names = [stage['control_names'][i] for i in keep]
        self.centers = stage['centers'][keep]; self.scales = stage['scales'][keep]
        self.data = DemandData(original.lnp, original.lnexp, original.shares[:, :-1],
            np.zeros((original.nobs, 1)), np.ones((original.nobs, m)),
            np.zeros((original.nobs, m)), original.a0, np.zeros(original.nobs))

    def expand(self, theta):
        th = np.zeros(self.full.spec.n_free); th[self.indices] = theta
        return th

    def fitted(self, theta, rows=slice(None)):
        return self.full.fitted(self.expand(theta), rows)[:, :-1]

    def derivative_blocks(self, theta, rows):
        J, H = self.full.derivative_blocks(self.expand(theta), rows)
        return J[:, :-1, self.base_indices], H[:, :-1]

    def jacobian(self, theta, rows=slice(None)):
        J, H = self.derivative_blocks(theta, rows)
        shifts = (self.Z[rows, None, :, None]*H[:, :, None, :]).reshape(
            len(J), self.spec.n_eq_estimated, -1)
        return np.concatenate([J, shifts], axis=2)

    def coefs(self, theta, regime=0):
        nt, eta = self.full.unpack(self.expand(theta), regime)
        return unpack(nt, self.full.native), eta

    def warm_from_cohort(self, cohort_fit, stage):
        # The original last translation was mean CF, now absent.
        assert stage['control_names'][-1] == 'mean_cf_residual'
        th = np.zeros(self.spec.n_free)
        th[:self.common_base] = cohort_fit.theta[:self.common_base]
        old_base = self.full.common_base
        th[self.spec.nbase:] = cohort_fit.theta[old_base:].reshape(-1, self.spec.neqn-1)[:-1].ravel()
        return th

    def warm_from_plain(self, common_theta):
        th = np.zeros(self.spec.n_free)
        th[:self.common_base] = common_theta[:self.common_base]
        th[self.spec.nbase:] = common_theta[self.common_base:]
        return th
