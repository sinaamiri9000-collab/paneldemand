"""Uncensored/no-CF Mundlak sensitivity: suitable pooling and stability Walds.

No ordinary Chow F or iid Gaussian LR is reported for the panel-correlated,
heteroskedastic nonlinear system. Prices/sample/controls match the cohort pilot.
"""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import os
for key in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[key] = '1'
import argparse
import json
import pickle
import time
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from pyquaidsce.elasticities import elasticities, Means
from pilot.common.plain_core import PlainCore
from pilot.common.staged_inference import residual_hessian, scaled_solve
from pilot.preliminary_stability.stability import robust_wald, index_R
from pilot.common.frame_results import unpack_e, economic_comparison
from pilot.common.run import dump, solver_direction


def robust_score_test(bread, scores, tested):
    """Nuisance-adjusted restricted-score LM for regular estimating equations."""
    tested = np.asarray(tested)
    nuisance = np.setdiff1d(np.arange(bread.shape[0]), tested)
    cnn = bread[np.ix_(nuisance, nuisance)]
    cn = bread[np.ix_(tested, nuisance)]
    projection = scaled_solve(cnn.T, cn.T).T
    efficient = scores[:, tested]-scores[:, nuisance]@projection.T
    moment = efficient.sum(0)
    meat = efficient.T@efficient*(len(scores)/(len(scores)-1))
    test = robust_wald(moment, meat, np.eye(len(tested)))
    test['qualification'] = 'restricted-score LM; observed estimating-equation Jacobian; household-cluster meat; Sigma nuisance included; constructed prices fixed'
    test['nuisance_demand_parameters'] = len(nuisance)
    test['restricted_nuisance_score_max_abs'] = float(np.max(np.abs(scores[:, nuisance].sum(0))))
    return test


def plain_covariance(core, fit, chunk=1500, score_test=False):
    n = core.data.nobs; m = core.spec.n_eq_estimated; K = core.spec.n_free
    W = np.linalg.inv(fit.sigma); P = np.linalg.inv(np.linalg.cholesky(fit.sigma))
    G, g, objective = core.normal(fit.theta, core.data, core.spec, None, P, 3000)
    A = G.copy(); a, b = np.triu_indices(m); V = len(a); H = n//3
    DtS = np.zeros((K, V)); DSt = np.zeros((V, K))
    scores = np.empty((H, K)); sigma_scores = np.empty((H, V))
    expanded = core.expand(fit.theta)
    for start in range(0, n, chunk):
        end = min(start+chunk, n); rows = slice(start, end); hs = slice(start//3, end//3)
        u = core.data.shares[rows]-core.fitted(fit.theta, rows)
        J = core.jacobian(fit.theta, rows); Wu = u@W
        JW = np.einsum('ij,njk->nik', W, J, optimize=True)
        full_Wu = np.column_stack([Wu, np.zeros(len(u))])
        Hess = residual_hessian(core.full, expanded, rows, full_Wu)
        A -= Hess[np.ix_(core.indices, core.indices)]
        scores[hs] = np.einsum('nik,ni->nk', J, Wu, optimize=True).reshape(-1, 3, K).sum(1)
        sigma_scores[hs] = (u[:, a]*u[:, b]-fit.sigma[a, b]).reshape(-1, 3, V).sum(1)
        weighted = np.einsum('nak,nb->abk', JW, Wu, optimize=True)
        raw = np.einsum('nak,nb->abk', J, u, optimize=True)
        for v, (aa, bb) in enumerate(zip(a, b)):
            DtS[:, v] -= weighted[aa, bb]
            if aa != bb: DtS[:, v] -= weighted[bb, aa]
            DSt[v] -= raw[aa, bb]+raw[bb, aa]
        if start % (chunk*20) == 0 or end == n:
            print(f'PLAIN covariance {end}/{n}', flush=True)
    effective = A-DtS@DSt/n
    adjusted_scores = scores+sigma_scores@DtS.T/n
    if score_test:
        return robust_score_test(effective, adjusted_scores,
                                np.arange(core.common_base, core.spec.nbase))
    influence = scaled_solve(effective, adjusted_scores.T).T
    cov = influence.T@influence*(H/(H-1)); cov = (cov+cov.T)/2
    scales = np.sqrt(np.abs(np.diag(effective)))
    ev = np.linalg.eigvalsh(effective/scales[:, None]/scales[None, :])
    diag = {'clusters': H, 'observed_bread_scaled_min_eigenvalue': ev.min(),
        'observed_bread_scaled_condition': ev.max()/ev.min(),
        'gradient_scaled_gn_ratio': abs(float(solver_direction(G, g)@g))/objective,
        'sigma_moment_max_error': np.max(np.abs(sigma_scores.sum(0)/n)),
        'covariance_finite': bool(np.isfinite(cov).all()),
        'sigma_nuisance_parameters_included': V, 'cluster_correction': H/(H-1)}
    if ev.min() <= 0 or not diag['covariance_finite']:
        raise RuntimeError('Plain observed bread invalid')
    return cov, diag


def elasticity_vector(core, theta, count):
    d = core.full.data
    means = Means(d.shares.mean(0), d.lnp.mean(0), float(d.lnexp.mean()),
                  np.zeros(1), np.ones(core.spec.neqn), np.zeros(core.spec.neqn),
                  np.zeros(core.spec.neqn), 0.)
    out = []
    for code in range(count):
        c, eta = core.coefs(theta, code); c.alpha += core.Z.mean(0)@eta
        e = elasticities(c, core.native, means, d.a0)
        out.append(np.r_[e.income, e.uncompensated.ravel(), e.compensated.ravel(),
                         e.income_latent, e.uncompensated_latent.ravel()])
    return np.concatenate(out)


def analyze(core, fit, cov, diag, labels, baseline, elapsed):
    contrast = list(range(core.common_base, core.spec.nbase)); tests = {}
    if contrast:
        tests['all_selected_slopes_equal'] = robust_wald(fit.theta, cov, index_R(core, contrast))
        offset = 0
        for block in core.blocks:
            width = core.base_slices[block].stop-core.base_slices[block].start
            ids = [core.common_base+r*core.slope_width+j
                   for r in range(len(labels)-1) for j in range(offset, offset+width)]
            tests[f'{block}_equal'] = robust_wald(fit.theta, cov, index_R(core, ids))
            offset += width
        for code in range(1, len(labels)):
            sl = slice(core.common_base+(code-1)*core.slope_width, core.common_base+code*core.slope_width)
            tests[f'{labels[code]}_vs_{labels[0]}'] = robust_wald(fit.theta, cov, index_R(core, list(range(sl.start, sl.stop))))
        if len(labels) == 3:
            indices1 = list(range(core.common_base, core.common_base+core.slope_width))
            indices2 = list(range(core.common_base+core.slope_width, core.spec.nbase))
            tests[f'{labels[2]}_vs_{labels[1]}'] = robust_wald(fit.theta, cov, index_R(core, indices2)-index_R(core, indices1))
    means_idx = [j for j, name in enumerate(core.control_names) if name.startswith('mean_')]
    mean_params = [core.spec.nbase+j*11+i for j in means_idx for i in range(11)]
    tests['mundlak_means_zero'] = robust_wald(fit.theta, cov, index_R(core, mean_params))
    for test in tests.values():
        test['qualification'] = 'household-cluster observed-Jacobian sandwich including IFGNLS Sigma; no CF or Probit stages; prices fixed'
    point = elasticity_vector(core, fit.theta, len(labels)); width = len(point)//len(labels)
    J = np.empty((len(point), core.spec.n_free))
    for j in range(core.spec.n_free):
        h = 1e-5*max(1., abs(fit.theta[j])); e = np.zeros_like(fit.theta); e[j] = h
        J[:, j] = (elasticity_vector(core, fit.theta+e, len(labels))-
                    elasticity_vector(core, fit.theta-e, len(labels)))/(2*h)
    es = {}; ses = {}; differences = {}; dses = {}; comparisons = {}
    for code, label in enumerate(labels):
        rows = slice(code*width, (code+1)*width); jj = J[rows]
        es[label] = unpack_e(point[rows], 12)
        ses[label] = unpack_e(np.sqrt(np.maximum(np.einsum('ij,ij->i', jj@cov, jj), 0)), 12)
        if code:
            jd = jj-J[:width]; key = label+'_minus_'+labels[0]
            differences[key] = unpack_e(point[rows]-point[:width], 12)
            dses[key] = unpack_e(np.sqrt(np.maximum(np.einsum('ij,ij->i', jd@cov, jd), 0)), 12)
            comparisons[key] = economic_comparison(differences[key], dses[key])
    coefficients = []; restrictions = []
    for code, label in enumerate(labels):
        c, eta = core.coefs(fit.theta, code)
        coefficients.append({'label': label, 'alpha_at_center': c.alpha, 'beta': c.beta,
                             'gamma': c.gamma, 'lambda': c.lam})
        restrictions.append({'label': label, 'alpha_sum': c.alpha.sum(), 'beta_sum': c.beta.sum(),
            'lambda_sum': c.lam.sum(), 'gamma_row_sum_max': np.max(np.abs(c.gamma.sum(1))),
            'gamma_symmetry_max': np.max(np.abs(c.gamma-c.gamma.T))})
    c, eta = core.coefs(fit.theta)
    f = core.full.fitted(core.expand(fit.theta))
    return {'labels': labels, 'counts': {label: int((core.regimes == code).sum()) for code, label in enumerate(labels)},
        'blocks_allowed_to_vary': core.blocks if len(labels) > 1 else [],
        'free_parameters': core.spec.n_free, 'extra_parameters': len(contrast),
        'convergence': {'success': bool(fit.converged), 'outer_iterations': fit.n_outer,
            'gn_iterations': fit.n_gn, 'log_likelihood': fit.llf, 'objective': fit.obj,
            'unweighted_share_sse_11_equations': np.sum((core.data.shares-f[:, :-1])**2),
            'sigma_condition': np.linalg.cond(fit.sigma), 'elapsed_seconds': elapsed},
        'numerical_settings': fit.pilot_numerical_settings, 'inference_diagnostics': diag,
        'tests': tests, 'restrictions': restrictions,
        'coefficients_by_regime': coefficients,
        'translation_names': core.control_names, 'translations_original_units': eta/core.scales[:, None],
        'translations_standardized': eta, 'translation_centers': core.centers, 'translation_scales': core.scales,
        'free_coefficients': fit.theta, 'free_standard_errors': np.sqrt(np.diag(cov)),
        'error_covariance_11_equations': fit.sigma,
        'elasticities_common_point': es, 'elasticity_standard_errors': ses,
        'elasticity_differences': differences, 'elasticity_difference_standard_errors': dses,
        'economic_comparisons': comparisons,
        'predictions': {'fitted_adding_up_rmse': np.sqrt(np.mean((f.sum(1)-1)**2)),
            'negative_fraction': (f < 0).mean(0), 'over_one_fraction': (f > 1).mean(0)}}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--only', nargs='+', choices=['frame', 'temporal', 'cohort'],
                   default=['frame', 'temporal', 'cohort'])
    p.add_argument('--output', type=Path, default=Path(__file__).parent/'results_plain_stability.json')
    args = p.parse_args(); root = args.inputs
    with (root/'frame_stage.pkl').open('rb') as f: stage = pickle.load(f)
    with (root/'cohort_cre_point.pkl').open('rb') as f: cohort_fit = pickle.load(f)
    baseline = json.loads((root/'frame_base.json').read_text())
    result = {'sample': baseline['sample'], 'input_hashes': baseline['input_hashes'],
        'a0': baseline['a0'], 'specification': baseline['specification'],
        'pyquaidsce_commit': baseline['pyquaidsce_commit'],
        'estimator_label': 'Mundlak translated-alpha QUAIDS without S&Y or CF; no education/curvature',
        'note': 'same 137814 rows retained, including zero group expenditures; income remains potentially endogenous; constructed prices/reference covariates fixed'}
    previous = None
    for kind in ['common']+args.only:
        start = time.time()
        if kind == 'common': regimes = np.zeros(len(stage['year']), dtype=int); labels = ['common']; blocks = ('beta','gamma','lambda')
        elif kind == 'frame': regimes = (stage['year'] >= 1397).astype(int); labels = ['1392–1396','1397–1403']; blocks = ('beta','gamma','lambda')
        elif kind == 'temporal':
            regimes = np.select([stage['year'] <= 1396, stage['year'] <= 1399], [0, 1], default=2)
            labels = ['1392–1396','1397–1399','1400–1403']; blocks = ('beta','gamma','lambda')
        else:
            values = np.sort(np.unique(stage['cohort'])); regimes = np.searchsorted(values, stage['cohort'])
            labels = [f'{c}–{c+2}' for c in values]; blocks = ('beta','lambda')
        core = PlainCore(stage, regimes, blocks)
        cache = root/f'plain_{kind}_point.pkl'
        key = {'version': 'plain-noSY-noCF-v1', 'sample_hash': baseline['sample']['sample_hash'],
               'blocks': blocks, 'labels': labels, 'controls': core.control_names}
        if cache.exists():
            with cache.open('rb') as f: fit = pickle.load(f)
            assert fit.pilot_plain_key == key
        else:
            init = core.warm_from_cohort(cohort_fit, stage) if previous is None else core.warm_from_plain(previous.theta)
            # Project the raw observed residual covariance onto the 11 equations.
            u = core.data.shares-core.fitted(init); sigma = u.T@u/len(u)
            def log(msg):
                with (root/f'plain_{kind}_solver.log').open('a') as f: f.write(msg+'\n')
                print(kind, msg, flush=True)
            fit = core.fit(init, sigma, log)
            fit.pilot_plain_key = key; fit.pilot_point_seconds = time.time()-start
            with cache.open('wb') as f: pickle.dump(fit, f)
        if not fit.converged or not np.isfinite(fit.theta).all():
            raise RuntimeError(f'Plain {kind} failed convergence')
        cov_path = root/f'plain_{kind}_covariance.npz'
        with threadpool_limits(limits=3):
            if cov_path.exists():
                saved = np.load(cov_path); np.testing.assert_array_equal(saved['theta'], fit.theta)
                cov = saved['covariance']; diag = json.loads((root/f'plain_{kind}_diagnostics.json').read_text())
            else:
                cov, diag = plain_covariance(core, fit)
                np.savez_compressed(cov_path, covariance=cov, theta=fit.theta)
                dump(root/f'plain_{kind}_diagnostics.json', diag)
            result[kind] = analyze(core, fit, cov, diag, labels, baseline, time.time()-start)
            result[kind]['convergence']['point_fit_seconds'] = fit.pilot_point_seconds
        dump(args.output, result)
        print('PLAIN RESULT', kind, result[kind]['tests'], flush=True)
        if kind == 'common': previous = fit


if __name__ == '__main__': main()
