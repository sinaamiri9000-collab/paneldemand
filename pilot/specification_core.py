"""Common-slope native QUAIDS with distinct alpha and additive CF shifters.

An additive column enters Phi_i * loading_i * control; it never changes the
translog price index. All shifter/loadings sum to zero across latent equations.
No claim of joint random-effects likelihood or global demand regularity is made.
"""
import numpy as np
from regime_core import RegimeCore
from pyquaidsce.params import unpack
from pyquaidsce.model import _inner, fitted_shares
from pyquaidsce.jacfree import jacobian_free
from pyquaidsce.elasticities import fitted_share_derivatives
from pyquaidsce._timing import check_deadline


class SpecificationCore(RegimeCore):
    def __init__(self, data, Z, additive_columns=None):
        super().__init__(data, Z, np.zeros(data.nobs, int))
        self.additive_columns = np.zeros(Z.shape[1], bool)
        if additive_columns is not None:
            self.additive_columns[np.asarray(additive_columns, int)] = True

    def quantities(self, theta, rows=slice(None)):
        nt, eta = self.unpack(theta)
        d = self.data.subset(rows)
        translate = self.Z[rows][:, ~self.additive_columns]@eta[~self.additive_columns]
        additive = self.Z[rows][:, self.additive_columns]@eta[self.additive_columns]
        d.lnexp = d.lnexp-np.einsum('ni,ni->n', d.lnp, translate)
        return nt, d, translate, additive

    def fitted(self, theta, rows=slice(None)):
        nt, d, translate, additive = self.quantities(theta, rows)
        return fitted_shares(nt, d, self.native)+d.cdf*(translate+additive)

    def derivative_blocks(self, theta, rows):
        nt, d, translate, additive = self.quantities(theta, rows)
        J = jacobian_free(nt, d, self.native, self.cache)@self.T
        inn = _inner(unpack(nt, self.native), d, self.native)
        Ht = d.cdf[:, :, None]*(self.B[None, :, :]-
             inn.S[:, :, None]*(d.lnp@self.B)[:, None, :])
        Ha = d.cdf[:, :, None]*self.B[None, :, :]
        return J, Ht, Ha

    def jacobian(self, theta, rows=slice(None)):
        J, Ht, Ha = self.derivative_blocks(theta, rows)
        H = np.where(self.additive_columns[None, None, :, None],
                     Ha[:, :, None, :], Ht[:, :, None, :])
        controls = (self.Z[rows, None, :, None]*H).reshape(len(J), self.spec.neqn, -1)
        return np.concatenate([J, controls], axis=2)

    def fitted_derivatives(self, theta, tau, layout, selection_index, rows=slice(None)):
        """Exact current price/expenditure partials, means and CF inputs fixed."""
        tau = np.asarray(tau, float).ravel()
        nt, d, translate, additive = self.quantities(theta, rows)
        dx, dp = fitted_share_derivatives(nt, d, self.native, tau=tau, layout=layout,
                                        selection_index=selection_index[rows])
        inn = _inner(unpack(nt, self.native), d, self.native)
        # Only alpha translations change ln a(p); additive CF does not.
        dp -= d.cdf[:, :, None]*inn.S[:, :, None]*translate[:, None, :]
        tm = np.array([layout.coefficient(tau, i, layout.expenditure_position)
                       for i in range(self.spec.neqn)])
        tp = np.array([[layout.coefficient(tau, i, layout.price_position(j))
                       for j in range(self.spec.neqn)] for i in range(self.spec.neqn)])
        extra = translate+additive
        dx += d.pdf*extra*tm
        dp += d.pdf[:, :, None]*extra[:, :, None]*tp[None, :, :]
        return dx, dp

    def normal(self, theta, d, spec, cache, P, chunk, deadline=None):
        """Structured exact Gram for the two kinds of shifter; native solver."""
        k0, m, h = self.spec.nbase, self.spec.neqn, self.spec.neqn-1
        K = self.spec.n_free
        G = np.zeros((K, K)); g = np.zeros(K); objective = 0.
        groups = [np.flatnonzero(~self.additive_columns), np.flatnonzero(self.additive_columns)]
        for start in range(0, d.nobs, chunk):
            check_deadline(deadline)
            rows = slice(start, min(start+chunk, d.nobs)); z = self.Z[rows]
            u = (d.shares[rows]-self.fitted(theta, rows))@P.T
            J, Ht, Ha = self.derivative_blocks(theta, rows)
            J = np.matmul(P, J); HH = [np.matmul(P, Ht), np.matmul(P, Ha)]
            J2 = J.reshape(-1, k0)
            G[:k0, :k0] += J2.T@J2; g[:k0] += J2.T@u.ravel()
            active = []
            for cols, H in zip(groups, HH):
                if not len(cols): continue
                zz = z[:, cols]; q = len(cols)
                indices = (k0+cols[:, None]*h+np.arange(h)[None, :]).ravel()
                cross = np.einsum('nik,nij->nkj', J, H, optimize=True)
                cross = (zz.T@cross.reshape(len(z), -1)).reshape(q, k0, h).transpose(1, 0, 2).reshape(k0, q*h)
                G[:k0, indices] += cross; G[indices, :k0] += cross.T
                hs = np.einsum('nik,ni->nk', H, u, optimize=True)
                g[indices] += (zz.T@hs).ravel()
                active.append((zz, H, indices))
            for aa, (za, HA, ia) in enumerate(active):
                for bb in range(aa, len(active)):
                    zb, HB, ib = active[bb]
                    hh = np.einsum('nik,nij->nkj', HA, HB, optimize=True)
                    zz = np.einsum('nr,ns->nrs', za, zb, optimize=True)
                    block = (zz.reshape(len(z), -1).T@hh.reshape(len(z), -1))
                    block = block.reshape(za.shape[1], zb.shape[1], h, h).transpose(0, 2, 1, 3).reshape(len(ia), len(ib))
                    G[np.ix_(ia, ib)] += block
                    if aa != bb: G[np.ix_(ib, ia)] += block.T
            objective += float(np.sum(u*u))
        return G, g, objective

    def inference_latent_quantities(self, theta, rows):
        nt, d, translate, additive = self.quantities(theta, rows)
        c = unpack(nt, self.native); inn = _inner(c, d, self.native)
        return {'latent': inn.wstar+translate+additive+d.control_function[:, None]*c.cfcoef,
                'S': inn.S, 'D': inn.D, 'q': inn.q, 'delta': c.delta,
                'kappa': c.cfcoef, 'eta': self.unpack(theta)[1]}

    def inference_linear_gradients(self, rows):
        L = self.data.lnp[rows]@self.B
        n, h = L.shape; K = self.spec.n_free
        GA = np.zeros((n, K)); Gb = np.zeros_like(GA)
        GA[:, self.base_slices['alpha']] = L
        j, k = np.triu_indices(h)
        GA[:, self.base_slices['gamma']] = L[:, j]*L[:, k]*np.where(j == k, .5, 1.)
        Gb[:, self.base_slices['beta']] = L
        translate_z = self.Z[rows].copy(); translate_z[:, self.additive_columns] = 0
        GA[:, self.spec.nbase:] = (translate_z[:, :, None]*L[:, None, :]).reshape(n, -1)
        beta = np.zeros((self.spec.neqn, K)); lam = np.zeros_like(beta)
        beta[:, self.base_slices['beta']] = self.B
        lam[:, self.base_slices['lambda']] = self.B
        return GA, Gb, beta, lam
