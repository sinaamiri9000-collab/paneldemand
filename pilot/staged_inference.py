"""Stacked estimating-equation covariance for the actual three-stage pilot.

Murphy--Topel/Hardin sandwich, clustered on complete households. Includes WLS
expenditure, all marginal Probits, nonlinear IFGNLS scores and its estimated
error covariance. Uses the observed score Jacobian, including residual-times-
second-derivative terms. Price construction and reference covariates are fixed.
The native estimator and its point estimates are not changed.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.stats import norm
from pyquaidsce.probit import _lambda_ratio
from pyquaidsce.params import unpack
from pyquaidsce.model import _inner


@dataclass
class StageDesign:
    Xr: np.ndarray
    Xbar: np.ndarray
    weights: np.ndarray
    Xs: np.ndarray
    tau_std: np.ndarray
    sel_center: np.ndarray
    sel_scale: np.ndarray
    cf_pos: int
    mean_pos: int
    mean_z: int
    mean_z_scale: float
    rf_scale: np.ndarray
    rf_names: list


def recover_design(stage, baseline, root):
    """Reproduce, rather than approximate, both previous-stage designs."""
    d = stage['data']; n = d.nobs
    names = stage['control_names']
    mean_z = names.index('mean_cf_residual')
    original = stage['Z']*stage['scales']+stage['centers']
    raw_controls = np.delete(original, mean_z, axis=1)
    b = pd.read_parquet(root/'priced_panel_106.parquet',
                       columns=['panel_id', 'year', 'weight', 'total_income_real'])
    b = b[b.panel_id.isin(stage['panel_ids'])].sort_values(['panel_id', 'year'])
    np.testing.assert_array_equal(b.panel_id, stage['panel_ids'])
    np.testing.assert_array_equal(b.year, stage['year'])
    ids = np.asarray(stage['panel_ids']).reshape(-1, 3)
    assert np.all(ids == ids[:, :1]) and len(np.unique(ids)) == len(ids)
    weights = b.weight.to_numpy(copy=True); weights /= weights.mean()
    inc = np.log(b.total_income_real.to_numpy())-baseline['CRE']['first_stage']['income_center']
    X = np.column_stack([np.ones(n), d.lnp, raw_controls, inc, inc**2])
    rf_names = ['constant']+[f'lnp_{i+1}' for i in range(d.shares.shape[1])]
    rf_names += [name for name in names if name != 'mean_cf_residual']
    rf_names += ['ln_income_centered', 'ln_income_centered_squared']
    coeff = baseline['CRE']['first_stage']['coefficients']
    np.testing.assert_allclose(d.control_function, d.lnexp-X@np.array([coeff[v] for v in rf_names]),
                               atol=2e-10, rtol=2e-10)
    rf_scale = X.std(0); rf_scale[0] = 1
    Xr = X/rf_scale
    Xbar = np.repeat(Xr.reshape(-1, 3, Xr.shape[1]).mean(1), 3, axis=0)
    Xsel = np.column_stack([d.lnp, d.lnexp, original, d.control_function])
    center = Xsel.mean(0); scale = Xsel.std(0)
    Xs = np.column_stack([(Xsel-center)/scale, np.ones(n)])
    tau = stage['tau']
    tau_std = np.column_stack([tau[:, :-1]*scale, tau[:, -1]+tau[:, :-1]@center])
    np.testing.assert_allclose(Xs@tau_std.T, stage['selection_index'], atol=2e-11, rtol=2e-11)
    return StageDesign(Xr, Xbar, weights, Xs, tau_std, center, scale,
                       Xsel.shape[1]-1, d.shares.shape[1]+1+mean_z,
                       mean_z, float(stage['scales'][mean_z]), rf_scale, rf_names)


def probit_components(Xs, k, y, Xr, Xbar, tau_cf, tau_mean,
                      cf_pos, mean_pos, sel_scale):
    q = 2*y-1; lam = _lambda_ratio(q*k)
    g = q*lam; h = lam*(lam+q*k)
    bread = Xs.T@(h[:, None]*Xs)
    # Derivative of the complete score, including dX times the residual score.
    cross = Xs.T@(h[:, None]*(tau_cf*Xr+tau_mean*Xbar))
    cross[cf_pos] -= g@Xr/sel_scale[cf_pos]
    cross[mean_pos] -= g@Xbar/sel_scale[mean_pos]
    return bread, Xs*g[:, None], cross


def latent_quantities(core, theta, rows):
    n = len(core.regimes[rows]); m = core.spec.neqn
    values = {key: np.zeros((n, m)) for key in ['latent', 'S']}
    for key in ['D', 'q']:
        values[key] = np.zeros(n)
    for code, mask, nt, d, shift in core._pieces(theta, rows):
        c = unpack(nt, core.native); inn = _inner(c, d, core.native)
        values['latent'][mask] = inn.wstar+shift+d.control_function[:, None]*c.cfcoef
        values['S'][mask] = inn.S
        values['D'][mask] = inn.D; values['q'][mask] = inn.q
    nt, eta = core.unpack(theta)
    c = unpack(nt, core.native)
    values['delta'] = c.delta; values['kappa'] = c.cfcoef; values['eta'] = eta
    return values


def linear_gradients(core, rows):
    """Gradients of ln A, beta'ln p and equation beta/lambda (linear in theta)."""
    L = core.data.lnp[rows]@core.B
    n, h = L.shape; K = core.spec.n_free
    GA = np.zeros((n, K)); Gb = np.zeros_like(GA)
    GA[:, core.base_slices['alpha']] = L
    j, k = np.triu_indices(h)
    gamma = L[:, j]*L[:, k]*np.where(j == k, .5, 1.)
    GA[:, core.base_slices['gamma']] = gamma
    Gb[:, core.base_slices['beta']] = L
    GA[:, core.spec.nbase:] = (core.Z[rows, :, None]*L[:, None, :]).reshape(n, -1)
    beta = np.zeros((core.spec.neqn, K)); lam = np.zeros_like(beta)
    beta[:, core.base_slices['beta']] = core.B
    lam[:, core.base_slices['lambda']] = core.B
    codes = core.regimes[rows]
    # Regime-specific gradients are observation dependent; weighted coefficient
    # sums are constructed below without allocating N x equation x parameter.
    for code in range(1, core.spec.ncontrast+1):
        mask = codes == code; start = core.contrast_slice(code).start; off = 0
        for block in core.blocks:
            width = core.base_slices[block].stop-core.base_slices[block].start
            sl = slice(start+off, start+off+width)
            if block == 'gamma': GA[mask, sl] = gamma[mask]
            if block == 'beta': Gb[mask, sl] = L[mask]
            off += width
    return GA, Gb, beta, lam


def residual_hessian(core, theta, rows, Wu, latent=None):
    """Sum_i,t (W u)_it d2 fitted_it/dtheta dtheta', analytically."""
    if latent is None: latent = latent_quantities(core, theta, rows)
    GA, Gb, beta, lam = linear_gradients(core, rows)
    R = core.data.cdf[rows]*Wu
    Cb = R@beta; Cl = R@lam
    D = latent['D']; q = latent['q']; codes = core.regimes[rows]
    Rlam = np.zeros(len(R))
    for code in range(core.spec.ncontrast+1):
        mask = codes == code
        c = unpack(core.unpack(theta, code)[0], core.native)
        Rlam[mask] = R[mask]@c.lam
        if code:
            start = core.contrast_slice(code).start; off = 0
            for block in core.blocks:
                width = core.base_slices[block].stop-core.base_slices[block].start
                sl = slice(start+off, start+off+width)
                if block == 'beta': Cb[mask, sl] = R[mask]@core.B
                if block == 'lambda': Cl[mask, sl] = R[mask]@core.B
                off += width
    # Small supports avoid multiplying the many zero beta/lambda columns.
    def sym_product(A, B):
        ia = np.flatnonzero(np.any(A != 0, axis=0))
        ib = np.flatnonzero(np.any(B != 0, axis=0))
        out = np.zeros((core.spec.n_free, core.spec.n_free))
        cross = A[:, ia].T@B[:, ib]
        out[np.ix_(ia, ib)] += cross
        out[np.ix_(ib, ia)] += cross.T
        return out
    H = -sym_product(Cb, GA)
    H -= sym_product((q*D**2)[:, None]*Cl, Gb)
    H -= 2*sym_product((q*D)[:, None]*Cl, GA)
    H += Gb.T@((Rlam*q*D**2)[:, None]*Gb)
    H += 2*sym_product((Rlam*q*D)[:, None]*Gb, GA)
    H += 2*GA.T@((Rlam*q)[:, None]*GA)
    return H


def input_score_derivatives(core, theta, rows, k, W, mean_z, mean_scale,
                            mean_step=1e-5):
    """Exact score sensitivity to Probit indices and current/mean CF inputs.

    Only dJ/d(mean CF) uses a centered numerical input derivative. It is tested
    against independent score differences; all other derivatives are analytic.
    """
    J = core.jacobian(theta, rows)
    u = core.data.shares[rows]-core.fitted(theta, rows)
    Wu = u@W
    JW = np.einsum('ij,njk->nik', W, J, optimize=True)
    lat = latent_quantities(core, theta, rows)
    phi = core.data.pdf[rows]; Phi = core.data.cdf[rows]
    dfdk = phi*(lat['latent']-lat['delta']*k)
    # dJ/dk for all non-delta parameters: J * phi/Phi.
    sk = J*_lambda_ratio(k)[:, :, None]*Wu[:, :, None]-JW*dfdk[:, :, None]
    ds = core.base_slices['delta']
    sk[:, :, ds] = -JW[:, :, ds]*dfdk[:, :, None]
    for i in range(core.spec.neqn):
        sk[:, i, ds.start+i] += -k[:, i]*phi[:, i]*Wu[:, i]
    f_v = Phi*lat['kappa']
    sv = -np.einsum('nik,ni->nk', JW, f_v, optimize=True)
    sv[:, core.base_slices['cfcoef']] += (Phi*Wu)@core.B
    t = lat['eta'][mean_z]/mean_scale
    f_mean = Phi*(t-lat['S']*(core.data.lnp[rows]@t)[:, None])
    original = core.Z[rows, mean_z].copy()
    try:
        core.Z[rows, mean_z] = original+mean_step/mean_scale
        Jp = core.jacobian(theta, rows)
        core.Z[rows, mean_z] = original-mean_step/mean_scale
        Jm = core.jacobian(theta, rows)
    finally:
        core.Z[rows, mean_z] = original
    sm = np.einsum('nik,ni->nk', (Jp-Jm)/(2*mean_step), Wu, optimize=True)
    sm -= np.einsum('nik,ni->nk', JW, f_mean, optimize=True)
    return J, JW, u, Wu, sk, sv, sm, dfdk, f_v, f_mean, lat


def scaled_solve(A, b):
    scale = np.sqrt(np.maximum(np.abs(np.diag(A)), 1e-300))
    return np.linalg.solve(A/scale[:, None]/scale[None, :], b/scale[:, None])/scale[:, None]


def stacked_covariance(core, fit, stage, design, chunk=1500, log=print):
    """Observed-Jacobian household sandwich, with all generated stages included."""
    n = core.data.nobs; m = core.spec.neqn; K = core.spec.n_free
    assert n % 3 == 0 and chunk % 3 == 0
    H = n//3; Q = design.Xs.shape[1]; R = design.Xr.shape[1]
    Xr, Xbar, Xs = design.Xr, design.Xbar, design.Xs
    tau = stage['tau']; k = stage['selection_index']
    A_rf = Xr.T@(design.weights[:, None]*Xr)
    score_rf = (Xr*(design.weights*core.data.control_function)[:, None]).reshape(H, 3, R).sum(1)
    I_rf = scaled_solve(A_rf, score_rf.T).T
    I_tau = np.empty((H, m, Q)); probit_bread = []
    for i in range(m):
        B, score, cross = probit_components(
            Xs, k[:, i], (core.data.shares[:, i] > 0).astype(float), Xr, Xbar,
            tau[i, design.cf_pos], tau[i, design.mean_pos],
            design.cf_pos, design.mean_pos, design.sel_scale)
        score = score.reshape(H, 3, Q).sum(1)
        I_tau[:, i] = scaled_solve(B, (score+I_rf@cross.T).T).T
        probit_bread.append(B)
        log(f'STACK Probit influence {i+1}/{m}')
    W = np.linalg.inv(fit.sigma)
    P = np.linalg.inv(np.linalg.cholesky(fit.sigma))
    G, grad, obj = core.normal(fit.theta, core.data, core.spec, None, P, 3000)
    A = G.copy()
    Dta = np.zeros((K, R)); Dtt = np.zeros((m, K, Q))
    a, b = np.triu_indices(m); V = len(a)
    DtS = np.zeros((K, V)); DSt = np.zeros((V, K))
    DSa = np.zeros((V, R)); DSp = np.zeros((m, V, Q))
    scores = np.zeros((H, K)); sigma_scores = np.zeros((H, V))
    for start in range(0, n, chunk):
        end = min(start+chunk, n); rows = slice(start, end); hs = slice(start//3, end//3)
        J, JW, u, Wu, sk, sv, sm, dk, fv, fm, lat = input_score_derivatives(
            core, fit.theta, rows, k[rows], W, design.mean_z, design.mean_z_scale)
        A -= residual_hessian(core, fit.theta, rows, Wu, lat)
        score = np.einsum('nik,ni->nk', J, Wu, optimize=True)
        scores[hs] = score.reshape(-1, 3, K).sum(1)
        sigma_scores[hs] = (u[:, a]*u[:, b]-fit.sigma[a, b]).reshape(-1, 3, V).sum(1)
        rc = fv+dk*tau[:, design.cf_pos]
        rm = fm+dk*tau[:, design.mean_pos]
        rcscore = sv+np.einsum('nik,i->nk', sk, tau[:, design.cf_pos], optimize=True)
        rmscore = sm+np.einsum('nik,i->nk', sk, tau[:, design.mean_pos], optimize=True)
        Dta -= rcscore.T@Xr[rows]+rmscore.T@Xbar[rows]
        for i in range(m):
            Dtt[i] += sk[:, i].T@Xs[rows]
            part = -(dk[:, i, None]*u).T@Xs[rows]
            for v, (aa, bb) in enumerate(zip(a, b)):
                if aa == i: DSp[i, v] += part[bb]
                if bb == i: DSp[i, v] += part[aa]
        DSa += (rc[:, a]*u[:, b]+rc[:, b]*u[:, a]).T@Xr[rows]
        DSa += (rm[:, a]*u[:, b]+rm[:, b]*u[:, a]).T@Xbar[rows]
        # Derivatives of J' W u w.r.t vech(Sigma), and of uu' w.r.t theta.
        weighted_cross = np.einsum('nak,nb->abk', JW, Wu, optimize=True)
        raw_cross = np.einsum('nak,nb->abk', J, u, optimize=True)
        for v, (aa, bb) in enumerate(zip(a, b)):
            DtS[:, v] -= weighted_cross[aa, bb]
            if aa != bb: DtS[:, v] -= weighted_cross[bb, aa]
            DSt[v] -= raw_cross[aa, bb]+raw_cross[bb, aa]
        if start % (chunk*10) == 0 or end == n:
            log(f'STACK demand score/Jacobian {end}/{n}')
    # Eliminate Sigma from the joint Jacobian (its diagonal block is -N I).
    rhs = scores+I_rf@Dta.T
    srhs = sigma_scores+I_rf@DSa.T
    for i in range(m):
        rhs += I_tau[:, i]@Dtt[i].T
        srhs += I_tau[:, i]@DSp[i].T
    effective = A-DtS@DSt/n
    rhs += srhs@DtS.T/n
    I_theta = scaled_solve(effective, rhs.T).T
    log('STACK forming full covariance (demand + 12 Probits + expenditure)')
    IF = np.column_stack([I_theta, I_tau.reshape(H, -1), I_rf])
    # HC1-style cluster correction only; no equation-specific degrees of freedom.
    covariance = (IF.T@IF)*(H/(H-1))
    covariance = (covariance+covariance.T)/2
    conditional_if = scaled_solve(G, scores.T).T
    conditional = conditional_if.T@conditional_if*(H/(H-1))
    scale = np.sqrt(np.abs(np.diag(effective)))
    ev = np.linalg.eigvalsh(effective/scale[:, None]/scale[None, :])
    from run import solver_direction
    direction = solver_direction(G, grad)
    diagnostics = {
        'clusters': H, 'observations': n, 'demand_parameters': K,
        'probit_parameters_each': Q, 'expenditure_parameters': R,
        'joint_parameters_reported': len(covariance), 'sigma_nuisance_parameters': V,
        'bread_scaled_min_eigenvalue': float(ev.min()),
        'bread_scaled_condition': float(np.linalg.cond(effective/scale[:, None]/scale[None, :])),
        'covariance_finite': bool(np.isfinite(covariance).all()),
        'gradient_scaled_gn_ratio': abs(float(direction@grad))/obj,
        'mean_cf_input_difference_step': 1e-5,
        'sigma_moment_max_error': float(np.max(np.abs(sigma_scores.sum(0)/n))),
        'rf_score_max_abs': float(np.max(np.abs(score_rf.sum(0)))),
        'cluster_correction': H/(H-1),
        'corrected_to_conditional_se_ratio': np.sqrt(np.diag(covariance[:K, :K])/np.diag(conditional))}
    if ev.min() <= 0 or not diagnostics['covariance_finite']:
        raise RuntimeError('Invalid observed bread/covariance: inspect diagnostics')
    return covariance, conditional, diagnostics
