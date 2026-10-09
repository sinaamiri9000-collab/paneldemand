"""Five prespecified common-slope specifications; fixed sample and market prices.

Run: PILOT_BLAS_THREADS=3 python pilot/specification_suite/specification_suite.py \
       --inputs intermediate/pilot_inputs
Working stages/individual influence arrays stay in ignored intermediate/.
Only aggregate results, report and reproducible source are committed.
"""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
import copy
import fcntl
import hashlib
import json
import pickle
import time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm
from threadpoolctl import threadpool_limits
from pyquaidsce.model import DemandData
from pyquaidsce.params import unpack
from pyquaidsce.elasticities import Means, elasticities
from pilot.common.specification_core import SpecificationCore
from pilot.common.staged_inference import StageDesign, stacked_covariance
from pilot.common.run import PN, dummies, first_stage, fit_selection, scale_controls, dump
from pilot.preliminary_stability.stability import robust_wald
from pilot.common.frame_results import unpack_e, holm

VERSION = 'five-specifications-v1'
MODELS = ('B0', 'B1', 'B2', 'B3', 'P0')
GROUPS = ['برنج', 'نان و غلات', 'گوشت', 'لبنیات و تخم‌مرغ', 'روغن و چربی', 'میوه',
          'سبزیجات و سیب‌زمینی', 'حبوبات', 'مغزها، خشکبار و خرما',
          'قند، شیرینی و تنقلات', 'نوشیدنی بدون نوشابه', 'ادویه و چاشنی']
# Full Marshallian matrix, including own prices, plus all expenditure responses.
COMPARISON_ROWS = np.arange(12+144)


def rank_audit(X):
    scale = np.sqrt(np.mean(np.asarray(X)**2, axis=0)); scale[scale == 0] = 1
    s = np.linalg.svd(np.asarray(X)/scale, compute_uv=False)
    rank = int(np.sum(s > s[0]*1e-10))
    return {'columns': X.shape[1], 'rank': rank, 'scaled_condition': float(s[0]/s[-1]),
            'relative_smallest_singular_value': float(s[-1]/s[0])}


def load_sample(root):
    baseline = json.loads((Path(__file__).parents[1]/'cohort/results.json').read_text())
    old_stage = pickle.load(open(root/'frame_stage.pkl', 'rb'))
    b = pd.read_parquet(root/'priced_panel_106.parquet')
    b = b[b.panel_id.isin(old_stage['panel_ids'])].sort_values(['panel_id', 'year']).reset_index(drop=True)
    np.testing.assert_array_equal(b.panel_id, old_stage['panel_ids'])
    np.testing.assert_array_equal(b.year, old_stage['year'])
    np.testing.assert_allclose(b[PN], old_stage['data'].lnp, atol=0, rtol=0)
    b['cohort'] = b.groupby('panel_id').year.transform('min')
    b['exp_analysis_106'] = b.exp_system_107-b.exp_11_4
    b['ln_exp'] = np.log(b.exp_analysis_106)
    for g in range(1, 13):
        b[f'w_{g}'] = old_stage['data'].shares[:, g-1]
        b[f'X_{g}'] = b[f'w_{g}']*b.exp_analysis_106
    sample_hash = hashlib.sha256(('\n'.join(b.panel_id.astype(str)+':'+b.year.astype(str))).encode()).hexdigest()
    assert sample_hash == baseline['sample']['sample_hash']
    assert b.groupby('panel_id').size().eq(3).all()
    assert b.groupby('panel_id').year.diff().dropna().eq(1).all()
    return b, old_stage, baseline


def designs(b, name):
    z = dummies(b, True).drop(columns=['head_age', 'year_1397'])
    # Reference year 1392 is already omitted. Year 1397 is redundant with the
    # sum of post-frame cohort dummies. This retains every identifiable level FE.
    means = pd.DataFrame(index=b.index)
    change = {c: int((b.groupby('panel_id')[c].nunique() > 1).sum())
              for c in ['head_sex', 'head_marital_status', 'season_number', 'urban_rural', 'region']}
    if name != 'P0':
        xx = b[PN].copy()
        xx['household_size'] = z.household_size
        xx['head_age'] = b.head_age.astype(float)
        if name != 'B3':
            if change['head_sex']: xx['female'] = z.female
            if change['head_marital_status']:
                for c in ['marital_Widowed', 'marital_Divorced', 'marital_Bachelor']: xx[c] = z[c]
        if change['season_number']:
            for c in ['season_2', 'season_3', 'season_4']: xx[c] = z[c]
        means = xx.groupby(b.panel_id).transform('mean').add_prefix('mean_')
    rf_means = means.copy()
    inc = np.log(b.total_income_real)-np.average(np.log(b.total_income_real), weights=b.weight)
    if name != 'P0':
        rf_means['mean_ln_income_centered'] = inc.groupby(b.panel_id).transform('mean')
        rf_means['mean_ln_income_centered_squared'] = (inc**2).groupby(b.panel_id).transform('mean')
    return z, means, rf_means, change


def make_stage(b, name, z, means, rf_means, rf_stage=None,
               mean_cf=None, mean_expenditure=None):
    if rf_stage is None:
        cf, rf = first_stage(b, z, rf_means, name != 'P0')
    else:
        cf = rf_stage['data'].control_function.copy()
        rf = copy.deepcopy(rf_stage['first_stage'])
    if mean_cf is None: mean_cf = name in ('B1', 'B2')
    if mean_expenditure is None: mean_expenditure = name == 'B2'
    controls = pd.concat([z, means], axis=1)
    if mean_cf:
        controls['mean_cf_residual'] = pd.Series(cf).groupby(b.panel_id).transform('mean')
    if mean_expenditure:
        controls['mean_ln_expenditure'] = b.ln_exp.groupby(b.panel_id).transform('mean')
    lp = b[PN].to_numpy(); y = b.ln_exp.to_numpy()
    Xsel = np.column_stack([np.ones(len(b)), lp, y, controls, cf])
    audit = rank_audit(Xsel)
    if audit['rank'] != audit['columns']:
        raise ValueError(f'{name}: selection not identified: {audit}')
    tau, k, pdiag, layout = fit_selection(b, lp, y, controls, cf, name)
    Z, centers, scales = scale_controls(controls, b.weight.to_numpy())
    additive = []
    if 'mean_cf_residual' in controls:
        j = list(controls).index('mean_cf_residual'); additive = [j]
        # A pure additive CF uses raw vbar / SD, with no intercept centering.
        centers[j] = 0.; Z[:, j] = controls.iloc[:, j]/scales[j]
    a0 = float(np.average(y, weights=b.weight))-2.
    data = DemandData(lp, y, b[[f'w_{g}' for g in range(1, 13)]].to_numpy(),
                      np.zeros((len(b), 1)), norm.cdf(k), norm.pdf(k), a0, cf)
    if rf_stage is None:
        Xrf = np.column_stack([np.ones(len(b)), lp, z, rf_means, inc_terms(b)])
        rf_names = ['constant']+PN+list(z)+list(rf_means)+['ln_income_centered','ln_income_centered_squared']
    else:
        np.testing.assert_array_equal(lp, rf_stage['data'].lnp)
        np.testing.assert_array_equal(y, rf_stage['data'].lnexp)
        np.testing.assert_array_equal(b.panel_id, rf_stage['panel_ids'])
        Xrf = rf_stage['Xrf']; rf_names = rf_stage['rf_names']
    np.testing.assert_allclose(y-Xrf@np.array([rf['coefficients'][c] for c in rf_names]), cf, atol=2e-10)
    return {'data': data, 'Z': Z, 'centers': centers, 'scales': scales,
            'control_names': list(controls), 'additive_columns': additive,
            'tau': tau, 'selection_index': k, 'layout': layout,
            'Xrf': Xrf, 'rf_names': rf_names, 'first_stage': rf,
            'selection_diagnostics': pdiag, 'rank_selection': audit,
            'panel_ids': b.panel_id.to_numpy(), 'year': b.year.to_numpy(),
            'cohort': b.cohort.to_numpy(), 'weights': b.weight.to_numpy(),
            'level_names': list(z), 'mundlak_names': list(means),
            'rf_only_means': [c for c in rf_names if c.startswith('mean_') and c not in controls]}


def inc_terms(b):
    z = np.log(b.total_income_real.to_numpy())
    z -= np.average(z, weights=b.weight)
    return np.column_stack([z, z**2])


def inference_design(stage):
    d = stage['data']; X = stage['Xrf']; names = stage['control_names']
    raw = stage['Z']*stage['scales']+stage['centers']
    Xsel = np.column_stack([d.lnp, d.lnexp, raw, d.control_function])
    center = Xsel.mean(0); scale = Xsel.std(0)
    Xs = np.column_stack([(Xsel-center)/scale, np.ones(len(X))])
    tau = stage['tau']; tau_std = np.column_stack([tau[:, :-1]*scale, tau[:, -1]+tau[:, :-1]@center])
    np.testing.assert_allclose(Xs@tau_std.T, stage['selection_index'], atol=2e-11)
    rscale = X.std(0); rscale[0] = 1.; Xr = X/rscale
    Xbar = np.repeat(Xr.reshape(-1, 3, Xr.shape[1]).mean(1), 3, axis=0)
    j = names.index('mean_cf_residual') if 'mean_cf_residual' in names else -1
    weights = stage['weights'].copy(); weights /= weights.mean()
    return StageDesign(Xr, Xbar, weights, Xs, tau_std, center, scale,
                       Xsel.shape[1]-1, 13+j if j >= 0 else -1,
                       j, float(stage['scales'][j]) if j >= 0 else 1., rscale, stage['rf_names'])


def warm_start(core, stage, old_fit, old_stage):
    theta = np.zeros(core.spec.n_free)
    theta[:core.spec.nbase] = old_fit.theta[:122]
    # Preserve old alpha at the common representative controls. New variables
    # begin at zero; shared original-unit coefficients are carried forward.
    old_eta = old_fit.theta[122:].reshape(len(old_stage['control_names']), 11)@core.B.T
    old_alpha = unpack(core.offset+core.T@old_fit.theta[:122], core.native).alpha
    old_add = np.zeros(len(old_stage['control_names']), bool)
    old_add[old_stage.get('additive_columns', [])] = True
    refalpha = old_alpha+old_stage['Z'].mean(0)[~old_add]@old_eta[~old_add]
    eta = np.zeros((len(stage['control_names']), 12))
    for j, name in enumerate(stage['control_names']):
        if name in old_stage['control_names']:
            k = old_stage['control_names'].index(name)
            if old_add[k] == core.additive_columns[j]:
                eta[j] = old_eta[k]/old_stage['scales'][k]*stage['scales'][j]
    theta[core.spec.nbase:] = eta[:, :-1].ravel()
    atcenter = refalpha-core.Z.mean(0)[~core.additive_columns]@eta[~core.additive_columns]
    theta[core.base_slices['alpha']] = atcenter[:-1]
    return theta


class SuiteElasticities:
    """Native at-means convention, means/CF fixed for contemporaneous effects.

    RF/Probit uncertainty is propagated for inference. Empirical reference
    inputs, price construction and all scaling constants are treated fixed.
    """
    def __init__(self, core, fit, stage, design):
        self.core, self.fit, self.stage, self.design = core, fit, stage, design
        self.K = core.spec.n_free; self.Q = design.Xs.shape[1]; self.R = design.Xr.shape[1]
        d = core.data; k = stage['selection_index']; tau = stage['tau']
        self.phi = d.cdf.mean(0); self.pdf = d.pdf.mean(0); self.k = k.mean(0)
        self.z = core.Z.mean(0); self.cf = float(d.control_function.mean())
        self.phi_tau = d.pdf.T@design.Xs/d.nobs
        self.pdf_tau = (-k*d.pdf).T@design.Xs/d.nobs
        self.phi_rf = np.empty((12, self.R)); self.pdf_rf = self.phi_rf.copy(); self.k_rf = self.phi_rf.copy()
        for i in range(12):
            kd = -tau[i, design.cf_pos]*design.Xr
            if design.mean_pos >= 0: kd -= tau[i, design.mean_pos]*design.Xbar
            self.phi_rf[i] = d.pdf[:, i]@kd/d.nobs
            self.pdf_rf[i] = (-k[:, i]*d.pdf[:, i])@kd/d.nobs
            self.k_rf[i] = kd.mean(0)
        self.point = np.r_[fit.theta, design.tau_std.ravel(), np.zeros(self.R)]

    def evaluate(self, parameters):
        core, design = self.core, self.design
        theta = parameters[:self.K]
        ts = parameters[self.K:self.K+12*self.Q].reshape(12, self.Q)
        rf = parameters[self.K+12*self.Q:]; dt = ts-design.tau_std
        tau = np.column_stack([ts[:, :-1]/design.sel_scale,
              ts[:, -1]-(ts[:, :-1]/design.sel_scale)@design.sel_center])
        cdf = self.phi+np.einsum('mq,mq->m', self.phi_tau, dt)+self.phi_rf@rf
        pdf = self.pdf+np.einsum('mq,mq->m', self.pdf_tau, dt)+self.pdf_rf@rf
        k = self.k+dt@design.Xs.mean(0)+self.k_rf@rf
        z = self.z.copy()
        if design.mean_z >= 0: z[design.mean_z] -= design.Xbar.mean(0)@rf/design.mean_z_scale
        cf = self.cf-design.Xr.mean(0)@rf
        nt, eta = core.unpack(theta); c = unpack(nt, core.native)
        c.alpha += z[~core.additive_columns]@eta[~core.additive_columns]
        # Native core accepts one fixed CF input. Its product is exactly the sum
        # of current and mean additive effects at this reference point.
        c.cfcoef = c.cfcoef*cf+z[core.additive_columns]@eta[core.additive_columns]
        d = core.data
        means = Means(d.shares.mean(0), d.lnp.mean(0), float(d.lnexp.mean()),
                      np.zeros(1), cdf, pdf, k, 1.)
        e = elasticities(c, core.native, means, d.a0, tau=tau.ravel(),
                        np_prob=self.stage['layout'].width, layout=self.stage['layout'])
        return np.r_[e.income, e.uncompensated.ravel(), e.compensated.ravel(),
                     e.income_latent, e.uncompensated_latent.ravel()]

    def jacobian(self, step=1e-5):
        J = np.empty((456, len(self.point)))
        for j in range(len(self.point)):
            h = step*max(1., abs(self.point[j])); e = np.zeros_like(self.point); e[j] = h
            J[:, j] = (self.evaluate(self.point+e)-self.evaluate(self.point-e))/(2*h)
        return J


def block_tests(core, fit, stage, covariance):
    K = core.spec.n_free; Q = stage['tau'].shape[1]; h = 11
    design = inference_design(stage)
    params = np.r_[fit.theta, design.tau_std.ravel(), np.zeros(stage['Xrf'].shape[1])]
    def test(ids, name):
        if not len(ids): return {'not_applicable': True}
        r = robust_wald(params[ids], covariance[np.ix_(ids, ids)], np.eye(len(ids)))
        r['qualification'] = 'multistage observed-Jacobian household-cluster Wald; WLS, 12 Probits and IFGNLS Sigma propagated; prices fixed'
        r['block'] = name
        return r
    output = {}
    groups = {'mundlak': stage['mundlak_names'],
              'mean_cf': ['mean_cf_residual'], 'mean_expenditure': ['mean_ln_expenditure']}
    for label, names in groups.items():
        js = [stage['control_names'].index(c) for c in names if c in stage['control_names']]
        demand = [core.spec.nbase+j*h+r for j in js for r in range(h)]
        participation = [K+i*Q+13+j for i in range(12) for j in js]
        output[label+'_demand'] = test(demand, label)
        output[label+'_participation'] = test(participation, label)
        output[label+'_joint_stages'] = test(demand+participation, label)
    current = list(range(core.base_slices['cfcoef'].start, core.base_slices['cfcoef'].stop))
    part = [K+i*Q+Q-2 for i in range(12)]
    output['current_cf_demand'] = test(current, 'current_cf')
    output['current_cf_joint_stages'] = test(current+part, 'current_cf')
    if 'mean_cf_residual' in stage['control_names']:
        j = stage['control_names'].index('mean_cf_residual')
        mean = list(range(core.spec.nbase+j*h, core.spec.nbase+(j+1)*h))
        pmean = [K+i*Q+13+j for i in range(12)]
        output['two_part_cf_joint_stages'] = test(current+mean+part+pmean, 'two_part_cf')
    R = design.Xr.shape[1]
    coeff = np.array([stage['first_stage']['coefficients'][c] for c in stage['rf_names']])*design.rf_scale
    excluded = [j for j,c in enumerate(stage['rf_names']) if 'income_centered' in c]
    output['excluded_income_reduced_form'] = robust_wald(coeff[excluded], covariance[-R:,-R:][np.ix_(excluded, excluded)], np.eye(len(excluded)))
    output['excluded_income_reduced_form']['qualification'] = 'household-cluster WLS relevance Wald; current income terms plus RF-only income means when present; no proof of exclusion validity'
    output['excluded_income_reduced_form']['names'] = [stage['rf_names'][j] for j in excluded]
    return output


def coefficient_summary(core, fit, stage, covariance):
    nt, eta = core.unpack(fit.theta); c = unpack(nt, core.native); K = core.spec.n_free
    V = covariance[:K, :K]; out = {}; se = {}
    for label, field in [('alpha_at_center','alpha'),('beta','beta'),('lambda','lambda'),
                         ('delta','delta'),('cf_current','cfcoef')]:
        out[label] = getattr(c, 'lam' if field == 'lambda' else field)
        R = np.zeros((12, K)); sl = core.base_slices[field]
        R[:, sl] = np.eye(12) if field == 'delta' else core.B
        se[label] = np.sqrt(np.maximum(np.diag(R@V@R.T), 0))
    out['gamma'] = c.gamma
    gamma_ids = np.arange(core.base_slices['gamma'].start, core.base_slices['gamma'].stop)
    Rg = np.zeros((144, K))
    for j in gamma_ids:
        t = np.zeros(K); t[j] = 1
        Rg[:, j] = unpack(core.unpack(t)[0], core.native).gamma.ravel()
    se['gamma'] = np.sqrt(np.maximum(np.diag(Rg@V@Rg.T), 0)).reshape(12,12)
    raw = eta/stage['scales'][:, None]; sraw = np.zeros_like(raw)
    for j in range(len(raw)):
        ids = np.arange(core.spec.nbase+j*11, core.spec.nbase+(j+1)*11)
        sraw[j] = np.sqrt(np.maximum(np.diag(core.B@V[np.ix_(ids, ids)]@core.B.T), 0))/stage['scales'][j]
    out['control_names'] = stage['control_names']; out['control_types'] = ['additive_cf' if a else 'alpha_translation' for a in core.additive_columns]
    out['controls_original_units'] = raw; out['controls_standardized'] = eta
    if 'mean_cf_residual' in stage['control_names']:
        j = stage['control_names'].index('mean_cf_residual')
        out['cf_mean'] = raw[j]; se['cf_mean'] = sraw[j]
    out['control_centers'] = stage['centers']; out['control_scales'] = stage['scales']
    se['controls_original_units'] = sraw
    design = inference_design(stage); Q = design.Xs.shape[1]; R = design.Xr.shape[1]
    T = np.eye(Q); T[:-1, :-1] = np.diag(1/design.sel_scale)
    T[-1, :-1] = -design.sel_center/design.sel_scale
    tau_se = []
    for i in range(12):
        sl = slice(K+i*Q, K+(i+1)*Q)
        tau_se.append(np.sqrt(np.maximum(np.diag(T@covariance[sl, sl]@T.T), 0)))
    out['probit_names'] = list(stage['layout'].ordered_names)+['constant']
    out['probit'] = stage['tau']; se['probit'] = np.array(tau_se)
    out['reduced_form'] = stage['first_stage']['coefficients']
    v = np.diag(covariance[-R:, -R:])/(design.rf_scale**2)
    se['reduced_form'] = dict(zip(stage['rf_names'], np.sqrt(np.maximum(v, 0))))
    out['standard_errors'] = se
    return out


def _fit_model(root, b, old_stage, name, baseline, output_dir, preflight=False,
               prepared_stage=None, start_model=None, influence_consumer=None):
    started = time.time()
    if prepared_stage is None:
        z, means, rf_means, change = designs(b, name)
    stage_path = root/f'suite_{name}_stage.pkl'
    if prepared_stage is not None:
        stage = prepared_stage
        stage['version'] = VERSION
        if stage_path.exists():
            cached = pickle.load(open(stage_path, 'rb'))
            assert cached['control_names'] == stage['control_names']
            np.testing.assert_array_equal(cached['Z'], stage['Z'])
            np.testing.assert_array_equal(cached['data'].control_function, stage['data'].control_function)
            np.testing.assert_array_equal(cached['Xrf'], stage['Xrf'])
            assert cached['rf_names'] == stage['rf_names']
            np.testing.assert_allclose(cached['selection_index'], stage['selection_index'], atol=1e-10, rtol=1e-10)
        with open(stage_path, 'wb') as f: pickle.dump(stage, f)
    elif stage_path.exists() and not preflight:
        stage = pickle.load(open(stage_path, 'rb')); assert stage['version'] == VERSION
    else:
        cf, rf = first_stage(b, z, rf_means, name != 'P0')
        cc = pd.concat([z, means], axis=1)
        if name in ('B1','B2'): cc['mean_cf_residual'] = pd.Series(cf).groupby(b.panel_id).transform('mean')
        if name == 'B2': cc['mean_ln_expenditure'] = b.ln_exp.groupby(b.panel_id).transform('mean')
        pre = {'model': name, 'rf': rank_audit(np.column_stack([np.ones(len(b)), b[PN], z, rf_means, inc_terms(b)])),
               'selection': rank_audit(np.column_stack([np.ones(len(b)), b[PN], b.ln_exp, cc, cf])),
               'alpha_or_additive_controls': list(cc), 'rf_only_means': [c for c in rf_means if c not in means]}
        print('PREFLIGHT', json.dumps(pre, ensure_ascii=False), flush=True)
        if preflight: return pre
        stage = make_stage(b, name, z, means, rf_means); stage['version'] = VERSION
        with open(stage_path, 'wb') as f: pickle.dump(stage, f)
    core = SpecificationCore(stage['data'], stage['Z'], stage['additive_columns'])
    design = inference_design(stage)
    fit_path = root/f'suite_{name}_point.pkl'
    with open(root/f'suite_{name}_solver.log', 'a') as logfile:
        def log(msg):
            logfile.write(msg+'\n'); logfile.flush(); print(name, msg, flush=True)
        if fit_path.exists():
            fit = pickle.load(open(fit_path, 'rb')); assert fit.pilot_suite_version == VERSION
        else:
            # Nearby nested fits supply starts, with unchanged stopping rules.
            start_name = start_model or {'B1':'B0', 'B2':'B1', 'B3':'B0', 'P0':'B0'}.get(name)
            start_path = root/f'suite_{start_name}_point.pkl'
            if start_name and start_path.exists():
                old_fit = pickle.load(open(start_path, 'rb'))
                start_stage = pickle.load(open(root/f'suite_{start_name}_stage.pkl', 'rb'))
            else:
                start_name = 'previous_cohort_model'
                old_fit = pickle.load(open(root/'cohort_cre_point.pkl', 'rb'))
                start_stage = old_stage
            theta0 = warm_start(core, stage, old_fit, start_stage)
            if stage.get('merge_season_mean_start'):
                old_eta = old_fit.theta[122:].reshape(len(start_stage['control_names']), 11)
                eta = theta0[122:].reshape(len(stage['control_names']), 11)
                for ss in (2, 3, 4):
                    current, mean = f'season_{ss}', f'mean_season_{ss}'
                    j = stage['control_names'].index(current)
                    jj = start_stage['control_names'].index(mean)
                    extra = old_eta[jj]*stage['scales'][j]/start_stage['scales'][jj]
                    eta[j] += extra
                    theta0[core.base_slices['alpha']] -= core.Z[:, j].mean()*extra
            ts = time.time()
            fit = core.fit(theta0, old_fit.sigma, log=log, gn_tol=1e-8)
            fit.pilot_start_name = start_name
            fit.pilot_suite_version = VERSION; fit.pilot_point_seconds = time.time()-ts
            with open(fit_path, 'wb') as f: pickle.dump(fit, f)
        if not fit.converged: raise RuntimeError(f'{name}: solver did not converge')
        covariance_path = root/f'suite_{name}_inference.npz'
        if covariance_path.exists():
            a = np.load(covariance_path)
            np.testing.assert_array_equal(a['theta'], fit.theta)
            covariance = a['covariance']; ediag = json.loads(str(a['diagnostics']))
            epoints = a['elasticities']; ese = a['elasticity_se']; EIF = a['elasticity_influence']
        else:
            with open(root/'suite_inference.lock', 'a') as inference_lock:
                fcntl.flock(inference_lock, fcntl.LOCK_EX)
                covstart = time.time()
                covariance, conditional, ediag, IF = stacked_covariance(core, fit, stage, design,
                            log=log, return_influence=True)
                ref = SuiteElasticities(core, fit, stage, design)
                epoints = ref.evaluate(ref.point); J = ref.jacobian()
                ese = np.sqrt(np.maximum(np.einsum('ij,ij->i', J@covariance, J), 0))
                EIF = IF@J[COMPARISON_ROWS].T
                if influence_consumer is not None:
                    influence_consumer(core, fit, stage, design, covariance, IF)
                # Independent step check, including additive CF and its RF channel.
                cols = [0, core.base_slices['gamma'].start, core.spec.nbase,
                        core.spec.n_free+design.cf_pos, len(ref.point)-1]
                if design.mean_z >= 0: cols.append(core.spec.nbase+design.mean_z*11)
                checks = []
                for j in cols:
                    h = 3e-6*max(1., abs(ref.point[j])); step = np.zeros_like(ref.point); step[j] = h
                    fd = (ref.evaluate(ref.point+step)-ref.evaluate(ref.point-step))/(2*h)
                    checks.append(float(np.max(np.abs(fd-J[:, j]))))
                ediag['elasticity_delta_gradient_max_step_difference'] = max(checks)
                ediag['inference_seconds'] = time.time()-covstart
                np.savez_compressed(covariance_path, covariance=covariance, theta=fit.theta,
                       diagnostics=json.dumps(ediag, default=lambda v: v.tolist()),
                       elasticities=epoints, elasticity_se=ese, elasticity_influence=EIF)
                del IF, conditional, J
    f = core.fitted(fit.theta); u = core.data.shares-f
    nt, eta = core.unpack(fit.theta); c = unpack(nt, core.native)
    restrictions = {'alpha_sum': float(c.alpha.sum()), 'beta_sum': float(c.beta.sum()),
                    'lambda_sum': float(c.lam.sum()), 'cf_current_sum': float(c.cfcoef.sum()),
                    'all_control_loading_sum_max_abs': float(np.abs(eta.sum(1)).max()),
                    'gamma_row_sum_max_abs': float(np.abs(c.gamma.sum(1)).max()),
                    'gamma_symmetry_max_abs': float(np.abs(c.gamma-c.gamma.T).max())}
    result = {'model': name, 'version': VERSION,
              'sample_hash': baseline['sample']['sample_hash'],
              'observations': len(b), 'households': b.panel_id.nunique(),
              'specification': {'level_controls': stage['level_names'], 'mundlak_controls': stage['mundlak_names'],
                                'rf_only_means': stage['rf_only_means'], 'controls': stage['control_names'],
                                'additive_cf_controls': [stage['control_names'][j] for j in stage['additive_columns']],
                                'year_omitted': [1392,1397], 'cohort_reference':1392,
                                'head_age_current': False, 'head_age_mean': name != 'P0',
                                'common_beta_gamma_lambda': True, 'wave': False, 'curvature': False},
              'rank': {'selection': stage['rank_selection'], 'reduced_form_columns': len(stage['rf_names']),
                       'reduced_form_rank': stage['first_stage']['rank']},
              'parameters': {'demand': core.spec.n_free, 'probit_each': design.Xs.shape[1],
                             'reduced_form': design.Xr.shape[1], 'sigma':78},
              'numerical_settings': fit.pilot_numerical_settings,
              'starting_model': getattr(fit, 'pilot_start_name', 'previous_cohort_model'),
              'convergence': {'success': bool(fit.converged), 'outer_iterations': fit.n_outer,
                              'gn_iterations': fit.n_gn, 'objective': fit.obj, 'log_likelihood': fit.llf,
                              'share_sse': float(np.sum(u*u)), 'point_seconds': fit.pilot_point_seconds,
                              'sigma_condition': float(np.linalg.cond(fit.sigma)),
                              'parameter_finite': bool(np.isfinite(fit.theta).all())},
              'error_covariance': fit.sigma,
              'fit': {'share_rmse_by_group': np.sqrt(np.mean(u*u, axis=0)),
                      'share_rmse_overall': float(np.sqrt(np.mean(u*u))),
                      'negative_share_fraction_by_group': (f < 0).mean(0),
                      'negative_share_fraction_overall': float((f < 0).mean()),
                      'over_one_share_fraction_by_group': (f > 1).mean(0),
                      'adding_up_rmse': float(np.sqrt(np.mean((f.sum(1)-1)**2))),
                      'mean_fitted_shares': f.mean(0), 'mean_observed_shares': core.data.shares.mean(0)},
              'restrictions': restrictions, 'first_stage': stage['first_stage'],
              'selection_diagnostics': stage['selection_diagnostics'],
              'inference_diagnostics': ediag, 'tests': block_tests(core, fit, stage, covariance),
              'coefficients': coefficient_summary(core, fit, stage, covariance),
              'elasticities': unpack_e(epoints,12), 'elasticity_standard_errors': unpack_e(ese,12),
              'wall_seconds_this_invocation': time.time()-started}
    for old in result['selection_diagnostics']:
        # Old helper's conditional tests are not the requested multistage tests.
        for key in list(old):
            if key.endswith('_test') or key.endswith('_z'): del old[key]
    dump(output_dir/f'{name}.json', result)
    return result


def fit_model(root, b, old_stage, name, baseline, output_dir, preflight=False, **kwargs):
    with open(root/f'suite_{name}.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _fit_model(root, b, old_stage, name, baseline, output_dir, preflight, **kwargs)


def compare(root, results):
    output = {}
    for before, after in [('B0','B1'),('B1','B2'),('B0','B3'),('P0','B0')]:
        aa = np.load(root/f'suite_{before}_inference.npz'); bb = np.load(root/f'suite_{after}_inference.npz')
        diff = bb['elasticities'][:156]-aa['elasticities'][:156]
        influence = bb['elasticity_influence']-aa['elasticity_influence']
        H = len(influence)
        se = np.sqrt((influence*influence).sum(0)*H/(H-1))
        p = 2*norm.sf(np.abs(diff)/se)
        main = np.r_[np.arange(12), 12+np.arange(12)*13]
        output[f'{after}_minus_{before}'] = {'difference_expenditure': diff[:12],
                'difference_marshallian': diff[12:].reshape(12,12),
                'standard_error_expenditure': se[:12], 'standard_error_marshallian': se[12:].reshape(12,12),
                'ci95_lower_expenditure': (diff-1.96*se)[:12], 'ci95_upper_expenditure': (diff+1.96*se)[:12],
                'ci95_lower_marshallian': (diff-1.96*se)[12:].reshape(12,12),
                'ci95_upper_marshallian': (diff+1.96*se)[12:].reshape(12,12),
                'pvalue_main24_holm': holm(p[main]), 'pvalue_main24': p[main],
                'economic_margin_illustrative': .1,
                'main24_ci95_outside_plus_minus_0_1': (np.abs(diff[main])-1.96*se[main]) > .1,
                'main24_ci90_inside_plus_minus_0_1': (np.abs(diff[main])+norm.ppf(.95)*se[main]) < .1,
                'qualification': 'paired multistage household influence functions; shared data/RF correlation included; constructed prices fixed; economic margin 0.1 illustrative'}
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--models', nargs='+', choices=MODELS, default=list(MODELS))
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--threads', type=int, default=3)
    args = parser.parse_args(); root = args.inputs
    if args.threads < 1: parser.error('--threads must be positive')
    os.environ['PILOT_BLAS_THREADS'] = str(args.threads)
    outdir = Path(__file__).parent; outdir.mkdir(exist_ok=True)
    b, old_stage, baseline = load_sample(root)
    output = {'version': VERSION, 'sample': baseline['sample'], 'groups': GROUPS,
              'previous_price_audit': 'pilot/cohort/results.json#prices',
              'source_input_hashes': baseline['input_hashes'],
              'priced_panel_sha256': hashlib.sha256((root/'priced_panel_106.parquet').read_bytes()).hexdigest(),
              'pyquaidsce_commit': baseline['pyquaidsce_commit'],
              'source_manifest': baseline.get('source_manifest', {}), 'models': {},
              'household_change_counts': designs(b,'B0')[3]}
    with threadpool_limits(limits=args.threads):
        for name in args.models:
            print('START', name, flush=True)
            output['models'][name] = fit_model(root, b, old_stage, name, baseline, outdir, args.preflight)
            print('DONE', name, flush=True)
        if args.preflight:
            dump(root/'suite_preflight.json', output); return
        if set(args.models) == set(MODELS):
            output['comparisons'] = compare(root, output['models'])
            (outdir/'results.json').write_text(json.dumps(output, ensure_ascii=False,
                separators=(',', ':'), default=lambda v: v.tolist())+'\n')
            for name in MODELS: (outdir/f'{name}.json').unlink()


if __name__ == '__main__': main()
