"""Aggregate stability results and economic comparisons; no household output."""
import json
import time
from pathlib import Path
import numpy as np
from scipy.stats import norm
from threadpoolctl import threadpool_limits
from pyquaidsce.params import unpack
from pyquaidsce.elasticities import elasticities, Means
from staged_inference import recover_design, stacked_covariance
from stability import robust_wald, index_R
from run import dump, coefficient_output

LABELS = ['1392–1396', '1397–1403']
E_KEYS = ['expenditure', 'marshallian', 'hicksian_slutsky_convention',
          'latent_expenditure', 'latent_marshallian']


def holm(p):
    p = np.asarray(p); order = np.argsort(p); n = len(p)
    answer = np.empty(n)
    answer[order] = np.minimum(1, np.maximum.accumulate(p[order]*(n-np.arange(n))))
    return answer


def unpack_e(v, m):
    sizes = [m, m*m, m*m, m, m*m]; out = {}; start = 0
    for key, size in zip(E_KEYS, sizes):
        value = v[start:start+size]
        out[key] = value.reshape(m, m) if size == m*m else value
        start += size
    assert start == len(v)
    return out


class ReferenceElasticities:
    """Native at-means convention, identical reference inputs in both regimes.

    Empirical reference covariates, centering and scales are conditioning inputs.
    The derivative propagates fitted Probit summaries and generated CF inputs.
    """
    def __init__(self, core, fit, stage, design):
        self.core = core; self.fit = fit; self.stage = stage; self.design = design
        self.m = core.spec.neqn; self.K = core.spec.n_free
        self.Q = design.Xs.shape[1]; self.R = design.Xr.shape[1]
        d = core.data; k = stage['selection_index']; tau = stage['tau']
        self.base_phi = d.cdf.mean(0); self.base_pdf = d.pdf.mean(0)
        self.base_k = k.mean(0); self.base_z = core.Z.mean(0)
        self.base_cf = float(d.control_function.mean())
        self.cf_grad = -design.Xr.mean(0)
        self.mean_grad = -design.Xbar.mean(0)
        self.phi_tau = d.pdf.T@design.Xs/d.nobs
        self.pdf_tau = (-k*d.pdf).T@design.Xs/d.nobs
        self.k_tau = design.Xs.mean(0)
        self.phi_rf = np.empty((self.m, self.R))
        self.pdf_rf = np.empty_like(self.phi_rf); self.k_rf = np.empty_like(self.phi_rf)
        for i in range(self.m):
            ka = -tau[i, design.cf_pos]*design.Xr-tau[i, design.mean_pos]*design.Xbar
            self.phi_rf[i] = d.pdf[:, i]@ka/d.nobs
            self.pdf_rf[i] = (-k[:, i]*d.pdf[:, i])@ka/d.nobs
            self.k_rf[i] = ka.mean(0)
        self.point = np.r_[fit.theta, design.tau_std.ravel(), np.zeros(self.R)]

    def evaluate(self, parameters):
        K, Q, m = self.K, self.Q, self.m
        th = parameters[:K]; ts = parameters[K:K+m*Q].reshape(m, Q)
        rf = parameters[K+m*Q:]; dt = ts-self.design.tau_std
        tau = np.column_stack([ts[:, :-1]/self.design.sel_scale,
               ts[:, -1]-(ts[:, :-1]/self.design.sel_scale)@self.design.sel_center])
        cdf = self.base_phi+np.einsum('mq,mq->m', self.phi_tau, dt)+self.phi_rf@rf
        pdf = self.base_pdf+np.einsum('mq,mq->m', self.pdf_tau, dt)+self.pdf_rf@rf
        k = self.base_k+dt@self.k_tau+self.k_rf@rf
        z = self.base_z.copy()
        z[self.design.mean_z] += self.mean_grad@rf/self.design.mean_z_scale
        cf = self.base_cf+self.cf_grad@rf
        d = self.core.data
        means = Means(d.shares.mean(0), d.lnp.mean(0), float(d.lnexp.mean()),
                      np.zeros(1), cdf, pdf, k, float(cf))
        output = []
        for regime in range(2):
            nt, eta = self.core.unpack(th, regime); c = unpack(nt, self.core.native)
            c.alpha = c.alpha+z@eta
            e = elasticities(c, self.core.native, means, d.a0,
                            tau=tau.ravel(), np_prob=self.stage['layout'].width,
                            layout=self.stage['layout'])
            output.append(np.concatenate([e.income, e.uncompensated.ravel(),
                e.compensated.ravel(), e.income_latent, e.uncompensated_latent.ravel()]))
        return np.concatenate(output)

    def jacobian(self, relative_step=1e-5):
        y = self.evaluate(self.point); J = np.empty((len(y), len(self.point)))
        for j in range(len(self.point)):
            h = relative_step*max(1., abs(self.point[j])); e = np.zeros_like(self.point); e[j] = h
            J[:, j] = (self.evaluate(self.point+e)-self.evaluate(self.point-e))/(2*h)
        return J


def economic_comparison(diff, se, margins=(.05, .1, .2)):
    """Test zero differences and economic equivalence as different hypotheses."""
    m = len(diff['expenditure'])
    values = np.r_[diff['expenditure'], np.diag(diff['marshallian'])]
    errors = np.r_[se['expenditure'], np.diag(se['marshallian'])]
    z = values/errors; p = 2*norm.sf(np.abs(z)); adjusted = holm(p)
    main = []
    for j in range(2*m):
        d, s = float(values[j]), float(errors[j]); ci = [d-1.96*s, d+1.96*s]
        ci90 = [d-norm.ppf(.95)*s, d+norm.ppf(.95)*s]
        item = {'group': j % m+1, 'kind': 'expenditure' if j < m else 'own_marshallian',
            'difference_after_minus_before': d, 'standard_error': s,
            'ci95': ci, 'ci90': ci90, 'pvalue_zero': float(p[j]),
            'pvalue_zero_holm_24': float(adjusted[j]),
            'quantity_response_gap_pp_for_10pct_shock': 10*d,
            'margin_results': {}}
        for margin in margins:
            peq = max(norm.sf((d+margin)/s), norm.cdf((d-margin)/s))
            # Conservative two-sided test that a difference exceeds the margin.
            plarge = min(1., 2*norm.sf((abs(d)-margin)/s))
            small = ci90[0] > -margin and ci90[1] < margin
            large = ci[0] > margin or ci[1] < -margin
            item['margin_results'][str(margin)] = {
                'equivalence_tost_pvalue': float(peq),
                'difference_beyond_margin_pvalue': float(plarge),
                'point_difference_below_margin': abs(d) < margin,
                'economic_classification': 'equivalent_within_margin' if small else
                      ('difference_beyond_margin' if large else 'economic_size_uncertain')}
        main.append(item)
    for margin in margins:
        adjusted_eq = holm([v['margin_results'][str(margin)]['equivalence_tost_pvalue'] for v in main])
        adjusted_large = holm([v['margin_results'][str(margin)]['difference_beyond_margin_pvalue'] for v in main])
        for item, pp, pp_large in zip(main, adjusted_eq, adjusted_large):
            item['margin_results'][str(margin)]['equivalence_pvalue_holm_24'] = float(pp)
            item['margin_results'][str(margin)]['equivalent_after_holm'] = bool(pp < .05)
            item['margin_results'][str(margin)]['difference_beyond_margin_pvalue_holm_24'] = float(pp_large)
            item['margin_results'][str(margin)]['difference_beyond_margin_after_holm'] = bool(pp_large < .05)
    return main


def produce(core, fit, stage, baseline, root, output):
    start = time.time(); design = recover_design(stage, baseline, root)
    covariance_path = root/'frame_stacked_covariance.npz'
    diagnostic_path = root/'frame_stacked_diagnostics.json'
    with threadpool_limits(limits=3):
        if covariance_path.exists():
            archive = np.load(covariance_path)
            np.testing.assert_array_equal(archive['theta'], fit.theta)
            cov = archive['covariance']; conditional = archive['conditional']
            diag = json.loads(diagnostic_path.read_text())
        else:
            cov, conditional, diag = stacked_covariance(core, fit, stage, design,
                                                       log=lambda x: print(x, flush=True))
            np.savez_compressed(covariance_path, covariance=cov, conditional=conditional,
                                theta=fit.theta)
            dump(diagnostic_path, diag)
        V = cov[:core.spec.n_free, :core.spec.n_free]
        tests = {}
        ids = list(range(core.common_base, core.spec.nbase))
        tests['beta_gamma_lambda_equal'] = robust_wald(fit.theta, V, index_R(core, ids))
        offset = 0
        for block in core.blocks:
            width = core.base_slices[block].stop-core.base_slices[block].start
            idx = list(range(core.common_base+offset, core.common_base+offset+width))
            tests[f'{block}_equal'] = robust_wald(fit.theta, V, index_R(core, idx))
            offset += width
        cf_indices = list(range(core.base_slices['cfcoef'].start, core.base_slices['cfcoef'].stop))
        tests['cf_current_zero'] = robust_wald(fit.theta, V, index_R(core, cf_indices))
        mundlak = [j for j, name in enumerate(stage['control_names'])
                   if name.startswith('mean_') and name != 'mean_cf_residual']
        ids_means = [core.spec.nbase+j*11+i for j in mundlak for i in range(11)]
        tests['mundlak_exogenous_means_zero'] = robust_wald(fit.theta, V, index_R(core, ids_means))
        mean_cf_indices = list(range(core.spec.nbase+design.mean_z*11,
                                     core.spec.nbase+(design.mean_z+1)*11))
        tests['mean_cf_translation_zero'] = robust_wald(fit.theta, V, index_R(core, mean_cf_indices))
        for test in tests.values():
            test['qualification'] = 'stacked observed-Jacobian sandwich, panel clusters, CF/12 Probits/Sigma included; constructed prices fixed'
        diag['same_fit_conditional_slope_wald'] = robust_wald(fit.theta, conditional, index_R(core, ids))
        ratios = np.sqrt(np.diag(V)/np.diag(conditional))
        diag['corrected_to_conditional_se_ratio_median'] = float(np.median(ratios))
        diag['corrected_to_conditional_se_ratio_max'] = float(ratios.max())
        ref = ReferenceElasticities(core, fit, stage, design)
        point = ref.evaluate(ref.point); jac = ref.jacobian(); width = len(point)//2
        point0, point1 = point[:width], point[width:]
        e0, e1 = unpack_e(point0, core.spec.neqn), unpack_e(point1, core.spec.neqn)
        diff = unpack_e(point1-point0, core.spec.neqn)
        Jdiff = jac[width:]-jac[:width]
        def standard_errors(J):
            return np.sqrt(np.maximum(np.einsum('ij,ij->i', J@cov, J), 0))
        se0 = unpack_e(standard_errors(jac[:width]), core.spec.neqn)
        se1 = unpack_e(standard_errors(jac[width:]), core.spec.neqn)
        sed = unpack_e(standard_errors(Jdiff), core.spec.neqn)
        # A second finite-difference step independently checks the delta gradient.
        selected = np.r_[np.arange(12), 12+np.arange(12)*13]
        audit_columns = [0, core.base_slices['gamma'].start, core.common_base,
                         core.spec.nbase+design.mean_z*11,
                         core.spec.n_free+12, len(ref.point)-1]
        audit_error = 0.
        for j in audit_columns:
            h = 3e-6*max(1., abs(ref.point[j])); delta = np.zeros_like(ref.point); delta[j] = h
            fd = (ref.evaluate(ref.point+delta)-ref.evaluate(ref.point-delta))/(2*h)
            audit_error = max(audit_error, float(np.max(np.abs(fd-jac[:, j]))))
        diag['elasticity_delta_gradient_max_absolute_step_check'] = audit_error
        comparisons = economic_comparison(diff, sed)
        coefficients = []; restrictions = []
        for regime, label in enumerate(LABELS):
            c = unpack(core.unpack(fit.theta, regime)[0], core.native)
            coefficients.append({'label': label, 'beta': c.beta, 'gamma': c.gamma, 'lambda': c.lam})
            restrictions.append({'label': label, 'alpha_sum': c.alpha.sum(), 'beta_sum': c.beta.sum(),
                'lambda_sum': c.lam.sum(), 'gamma_row_sum_max': np.max(np.abs(c.gamma.sum(1))),
                'gamma_symmetry_max': np.max(np.abs(c.gamma-c.gamma.T))})
        c0, c1 = coefficients
        parameter_difference = {key: np.asarray(c1[key])-np.asarray(c0[key]) for key in ['beta', 'gamma', 'lambda']}
        f = core.fitted(fit.theta)
        result = {
            'sample': baseline['sample'], 'input_hashes': baseline['input_hashes'],
            'pyquaidsce_commit': baseline['pyquaidsce_commit'], 'a0': core.data.a0,
            'specification': baseline['specification'], 'design': baseline['design'],
            'labels': LABELS, 'counts': {label: int((core.regimes == i).sum()) for i, label in enumerate(LABELS)},
            'free_parameters': core.spec.n_free, 'extra_parameters': len(ids),
            'convergence': {'success': bool(fit.converged), 'outer_iterations': fit.n_outer,
                'gn_iterations': fit.n_gn, 'log_likelihood': fit.llf, 'objective': fit.obj,
                'sigma_condition': np.linalg.cond(fit.sigma),
                'unweighted_share_sse': np.sum((core.data.shares-f)**2),
                'point_fit_seconds': fit.pilot_frame_seconds},
            'numerical_settings': fit.pilot_numerical_settings,
            'inference': 'Murphy–Topel/Hardin stacked estimating equations; WLS, 12 marginal Probits, IFGNLS and Sigma; household clusters; no bootstrap',
            'inference_diagnostics': diag, 'tests': tests, 'restrictions': restrictions,
            'coefficients_by_regime': coefficients, 'parameter_differences': parameter_difference,
            'shared_coefficients': coefficient_output(core, fit, stage['control_names'], stage['scales'], stage['centers']),
            'free_coefficients': fit.theta, 'free_coefficient_standard_errors': np.sqrt(np.diag(V)),
            'rf': baseline['CRE']['first_stage'], 'probit_names': baseline['CRE']['probit_regressor_names'],
            'probit_coefficients': stage['tau'], 'participation': baseline['CRE']['participation'],
            'error_covariance': fit.sigma,
            'elasticities_common_point': {LABELS[0]: e0, LABELS[1]: e1},
            'elasticity_standard_errors': {LABELS[0]: se0, LABELS[1]: se1},
            'elasticity_differences': diff, 'elasticity_difference_standard_errors': sed,
            'economic_comparisons': comparisons,
            'predictions': {'negative_fraction': (f < 0).mean(0), 'over_one_fraction': (f > 1).mean(0),
                'fitted_adding_up_rmse': np.sqrt(np.mean((f.sum(1)-1)**2))},
            'notes': [
                '1397 is the documented survey-frame boundary, not an estimated economic break.',
                'Cohort controls are retained; no year/season/wave/1400 dummy.',
                'Only beta/gamma/lambda are allowed to differ; the other loadings are common.',
                'Income exclusion and marginal-Probit/SY mean specification remain maintained assumptions.',
                'Sample, prices, reference covariates, a0, centering and scales condition inference.',
                'Price-donor/quality-adjustment uncertainty is not included.',
                'Reference means and CF controls stay fixed in price/expenditure elasticities.',
                'Statistical and equivalence tests concern this maintained model, not causal preferences.',
                'Economic margins 0.05/0.10/0.20 elasticity units are explicit illustrative sensitivity choices.',
                'Ten-percent shock comparisons are local first-order approximations, not welfare estimates.'],
            'inference_and_elasticity_seconds': time.time()-start}
        dump(output, result)
    print('FRAME TESTS', tests, flush=True)
    print('FRAME ECONOMIC COMPARISONS', comparisons, flush=True)
