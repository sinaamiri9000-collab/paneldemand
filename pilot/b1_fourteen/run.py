"""Reproducible 14-run B1 extension; only aggregate outputs enter Git.

python -m pilot.b1_fourteen.run --prepare
python -m pilot.b1_fourteen.run --run-all --workers 2
python -m pilot.b1_fourteen.export
"""
import os
for _key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_key] = '1'
os.environ['PILOT_BLAS_THREADS'] = '1'
import argparse
import concurrent.futures
import hashlib
import json
import pickle
import time
import importlib
import fcntl
import platform
from importlib.metadata import version as package_version
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm
from pyquaidsce.model import DemandData
from pyquaidsce.params import unpack
from pyquaidsce.probit import probit
from pyquaidsce.selection import FirstStageLayout
from pilot.common.prices import construct, digest
from pilot.common.run import PN, dummies, scale_controls, dump, wald, solver_direction, conditional_within_prices
from pilot.common.specification_core import SpecificationCore
from pilot.specification_suite.specification_suite import warm_start, rank_audit, GROUPS
from pilot.b1_fourteen.historical_core import HistoricalCore
from pilot.b1_fourteen.probit_adapter import finite_probit

REPO = Path(__file__).resolve().parents[2]
INPUT = REPO/'intermediate/pilot_inputs'
WORK = INPUT/'b1_fourteen'
OUT = Path(__file__).resolve().parent
VERSION = 'b1-fourteen-2026-10-11-v1'
COHORTS = (1392, 1393, 1394, 1397, 1398, 1399, 1400, 1401)
MODELS = [{'name': f'CS_{s}_{v}', 'sample': s, 'panel': False,
           'history': v == 'history', 'cohort': None}
          for s in ('All', 'B') for v in ('common', 'history')]
MODELS += [{'name': f'Panel_{c}', 'sample': 'B', 'panel': True,
            'history': False, 'cohort': c} for c in COHORTS]
MODELS += [{'name': f'Panel_B_{v}', 'sample': 'B', 'panel': True,
            'history': v == 'history', 'cohort': None} for v in ('common', 'history')]
MODEL_MAP = {m['name']: m for m in MODELS}
SOURCE_HASHES={
    'all_clean_1392_1403.csv.gz':'d077806039d2f891f2a26de2cfca8544acf1c322c593984f46b795152b2ccf69',
    'panelB_clean_1392_1403.csv.zip':'165dfd27c176e2c92e50a58f8762fae9635c3ffb59a61c7259f48f31dbd18ed0',
    'final_commodity_mapping_107.xlsx':'59d9872c0ba15ac5971c15775d537e1a910e05350625dc2fc48cff469cd918ef'}


def save_pickle(path, value):
    tmp = path.with_suffix('.part')
    with tmp.open('wb') as f: pickle.dump(value, f, protocol=5)
    tmp.replace(path)


def regimes(year):
    return np.where(np.asarray(year) < 1397, 0,
                    np.where(np.asarray(year) < 1399, 1, 2))


def hhmean(df, ids):
    return df.groupby(np.asarray(ids), sort=False).transform('mean')


def identified(df, prefix=None):
    """Keep columns in declared priority order; discard only exact redundancy.

    Two-pass modified Gram Schmidt on unit-norm columns avoids arbitrary QR
    pivot choices. Its tolerance is for design rank, not solver convergence.
    """
    base = np.ones((len(df), 1)) if prefix is None else np.asarray(prefix, float)
    Q, _ = np.linalg.qr(base, mode='reduced')
    kept = []; removed = []
    for name in df:
        v = df[name].to_numpy(float).copy(); size = np.linalg.norm(v)
        if size < 1e-14:
            removed.append({'name': name, 'reason': 'constant zero'}); continue
        v /= size
        for _ in range(2): v -= Q@(Q.T@v)
        residual = np.linalg.norm(v)
        if residual <= 1e-9:
            removed.append({'name': name, 'reason': 'exact collinearity',
                            'relative_residual': float(residual)})
        else:
            kept.append(name); Q = np.column_stack([Q, v/residual])
    return df[kept].copy(), removed


def prepare():
    WORK.mkdir(parents=True, exist_ok=True)
    for name,expected in SOURCE_HASHES.items():
        assert digest(INPUT/name)==expected,f'Frozen source changed: {name}'
    for cache,source in [('all.parquet','all_clean_1392_1403.csv.gz'),
                         ('panel.parquet','panelB_clean_1392_1403.csv.zip')]:
        if not (INPUT/cache).exists():
            frame=pd.read_csv(INPUT/source,dtype={'address_raw':str,'head_education':str})
            frame.to_parquet(INPUT/cache,index=False)
    mapping = pd.read_excel(INPUT/'final_commodity_mapping_107.xlsx')
    assert len(mapping) == 107
    mapping = mapping[mapping.p_var != 'p_11_4'].reset_index(drop=True)
    if not (WORK/'priced_all_106.parquet').exists():
        a, p, audit = construct(pd.read_parquet(INPUT/'all.parquet'),
                               pd.read_parquet(INPUT/'panel.parquet'), mapping, return_all=True)
        if (INPUT/'priced_panel_106.parquet').exists():
            prior = pd.read_parquet(INPUT/'priced_panel_106.parquet')
            np.testing.assert_allclose(p[PN], prior[PN], atol=2e-12, rtol=0)
        else: p.to_parquet(INPUT/'priced_panel_106.parquet',index=False)
        a.to_parquet(WORK/'priced_all_106.parquet', index=False)
        dump(WORK/'price_audit.json', audit)
    flows = {}
    previous=json.loads((OUT/'manifest.json').read_text()) if (OUT/'manifest.json').exists() else {}
    prior_path=INPUT/'suite_B1_no_season_means_stage.pkl'
    prior_stage=pickle.load(prior_path.open('rb')) if prior_path.exists() else None
    for sample in ('All', 'B'):
        b = pd.read_parquet(WORK/'priced_all_106.parquet' if sample == 'All'
                            else INPUT/'priced_panel_106.parquet')
        b = b.sort_values(['panel_id', 'year']).reset_index(drop=True)
        original = len(b)
        b['exp_analysis_106'] = b.exp_system_107-b.exp_11_4
        for g in range(1, 13):
            vv = mapping.loc[mapping.group_id == g, 'exp_var']
            b[f'X_{g}'] = b[vv].sum(axis=1, min_count=len(vv))
            b[f'w_{g}'] = b[f'X_{g}']/b.exp_analysis_106
        good = np.ones(len(b), bool); flow = []
        for label, valid in [
            ('food_matched', b.food_matched == 1),
            ('positive_106_expenditure', np.isfinite(b.exp_analysis_106)&(b.exp_analysis_106 > 0)),
            ('positive_real_income', np.isfinite(b.total_income_real)&(b.total_income_real > 0)),
            ('required_demographics', b.head_sex.isin(['Male', 'Female'])&
             np.isfinite(b.head_age)&(b.household_size > 0)),
            ('positive_finite_survey_weight', np.isfinite(b.weight)&(b.weight > 0)),
            ('finite_market_prices_and_shares', np.isfinite(b[PN]).all(axis=1)&
             np.isfinite(b[[f'w_{g}' for g in range(1,13)]]).all(axis=1))]:
            new = good&~np.asarray(valid); good &= np.asarray(valid)
            flow.append({'criterion': label, 'excluded': int(new.sum()), 'remaining': int(good.sum())})
        if sample == 'B':
            balanced = pd.Series(good).groupby(b.panel_id).transform('all').to_numpy()
            flow.append({'criterion': 'retain_complete_three_wave_households',
                         'excluded': int((good&~balanced).sum()), 'remaining': int(balanced.sum())})
            good = balanced
        b = b.loc[good].copy().reset_index(drop=True)
        b['cohort'] = b.groupby('panel_id').year.transform('min')
        b['ln_exp'] = np.log(b.exp_analysis_106)
        np.testing.assert_allclose(b[[f'w_{g}' for g in range(1,13)]].sum(axis=1), 1, atol=1e-10)
        if sample == 'B':
            assert b.groupby('panel_id').size().eq(3).all()
            assert b.groupby('panel_id').year.diff().dropna().eq(1).all()
            if prior_stage is not None:
                np.testing.assert_array_equal(b.panel_id, prior_stage['panel_ids'])
                np.testing.assert_array_equal(b.year, prior_stage['year'])
                np.testing.assert_allclose(b[PN], prior_stage['data'].lnp, rtol=0, atol=0)
                np.testing.assert_allclose(b[[f'w_{g}' for g in range(1,13)]], prior_stage['data'].shares, atol=1e-12)
            assert tuple(sorted(b.cohort.unique())) == COHORTS
        minimal = (['panel_id','address_raw','year','cohort','urban_rural','region','season_number',
                   'head_age','head_sex','head_marital_status','household_size','weight',
                   'total_income_real','exp_analysis_106','ln_exp']+PN+
                  [f'{v}_{g}' for v in ('X','w') for g in range(1,13)])
        b[minimal].to_parquet(WORK/f'sample_{sample}.parquet', index=False)
        sample_hash = hashlib.sha256(('\n'.join(b.panel_id.astype(str)+':'+b.year.astype(str))).encode()).hexdigest()
        if sample=='B':
            assert sample_hash=='397bee5d9347dc92fc687aa3bc6d5fea8c713cca3ce7de242bbd51a5474855ab'
            reference_a0=prior_stage['data'].a0 if prior_stage is not None else float(np.average(b.ln_exp,weights=b.weight))-2
            reference_center=float(b.ln_exp.mean())
        flows[sample] = {'source_rows': original, 'flow': flow, 'rows': len(b),
                         'households': b.panel_id.nunique(), 'sample_hash': sample_hash,
                         'by_year': b.year.value_counts().sort_index().to_dict(),
                         'by_cohort': b.cohort.value_counts().sort_index().to_dict() if sample == 'B' else None}
    dump(OUT/'manifest.json', {'version': VERSION, 'models': MODELS, 'sample': flows,
         'a0':reference_a0, 'authorized_expenditure_means': True,
         'mean_squared_definition': 'mean((ln expenditure - fixed center)^2), NOT square(mean)',
         'fixed_center':reference_center,
         'sources_sha256': {n: digest(INPUT/n) for n in (
             'all_clean_1392_1403.csv.gz','panelB_clean_1392_1403.csv.zip','final_commodity_mapping_107.xlsx')},
         'priced_panel_sha256': digest(INPUT/'priced_panel_106.parquet'),
         'price_method_identical_to_prior': True,
         'uploaded_chat_sha256':previous.get('uploaded_chat_sha256'),
         'reference_pdf_sha256':{p.name:digest(p) for p in (REPO/'refrence').glob('*.pdf')},
         'runtime':{'python':platform.python_version(),**{n:package_version(n) for n in
                    ('numpy','scipy','pandas','pyquaidsce','openpyxl','pyarrow')}},
         'package_commit':'636609f17e732a57b140cbbad5d2bf4042bc396a'})


def model_frame(spec):
    b = pd.read_parquet(WORK/f"sample_{spec['sample']}.parquet")
    if spec['cohort'] is not None: b = b[b.cohort == spec['cohort']].copy()
    return b.reset_index(drop=True)


def make_stage(b, spec):
    manifest = json.loads((OUT/'manifest.json').read_text())
    z = dummies(b, True)
    if spec['panel']: z = z.drop(columns='head_age')  # original B1 uses mean age
    if spec['sample'] == 'All':
        z = z.drop(columns=[c for c in z if c.startswith('cohort_')])
    elif spec['cohort'] is None:
        z = z.drop(columns='year_1397')  # disconnected frame / cohort identity
    z, dropped_level = identified(z)
    ids = b.panel_id.to_numpy(); lp = b[PN].to_numpy(); y = b.ln_exp.to_numpy()
    hist = spec['history']; codes = regimes(b.year); centered_y = y-manifest['fixed_center']
    means = pd.DataFrame(index=b.index); exomeans = means.copy()
    if spec['panel']:
        current = b[PN].copy()
        current['household_size'] = b.household_size.astype(float)
        current['head_age'] = b.head_age.astype(float)
        for c in ('female','marital_Widowed','marital_Divorced','marital_Bachelor'):
            if c in z: current[c] = z[c]
        exomeans = hhmean(current, ids).add_prefix('mean_')
        exomeans, dropped_means = identified(exomeans, np.column_stack([np.ones(len(b)), lp, z]))
        means = exomeans.copy()
        means['mean_ln_expenditure'] = hhmean(pd.DataFrame({'y': y}), ids).y
        means['mean_centered_ln_expenditure_squared'] = hhmean(pd.DataFrame({'y2': centered_y**2}), ids).y2
        if hist:
            extra = pd.DataFrame(index=b.index)
            for code in (1, 2):
                D = (codes == code).astype(float)
                for j, pn in enumerate(PN): extra[f'history_{code}_{pn}'] = D*lp[:, j]
                extra[f'history_{code}_ln_expenditure'] = D*y
                extra[f'history_{code}_centered_ln_expenditure_squared'] = D*centered_y**2
            hm = hhmean(extra, ids).add_prefix('mean_')
            means = pd.concat([means, hm], axis=1)
            # Only exogenous price interactions enter the expenditure RF.
            exomeans = pd.concat([exomeans, hm[[c for c in hm if '_lnp_' in c]]], axis=1)
    else: dropped_means = []
    income = np.log(b.total_income_real.to_numpy())
    ic = float(np.average(income, weights=b.weight)); inc = income-ic
    instruments = pd.DataFrame({'ln_income_centered': inc, 'ln_income_centered_squared': inc**2})
    if hist:
        for code in (1, 2):
            instruments[f'history_{code}_ln_income_centered'] = (codes == code)*inc
            instruments[f'history_{code}_ln_income_centered_squared'] = (codes == code)*inc**2
    rf_controls = pd.concat([b[PN], z], axis=1)
    if hist:
        for code in (1, 2):
            for pn in PN: rf_controls[f'history_{code}_{pn}'] = (codes == code)*b[pn]
    if spec['panel']:
        rf_controls = pd.concat([rf_controls, exomeans, hhmean(instruments, ids).add_prefix('mean_')], axis=1)
    rf_controls, rf_removed = identified(rf_controls)
    ivs, iv_removed = identified(instruments, np.column_stack([np.ones(len(b)), rf_controls]))
    Xrf = np.column_stack([np.ones(len(b)), rf_controls, ivs])
    rfnames = ['constant']+list(rf_controls)+list(ivs)
    wt = b.weight.to_numpy(copy=True); wt /= wt.mean()
    scale = Xrf.std(axis=0); scale[0] = 1.
    sw = np.sqrt(wt)
    coef, _, rank, _ = np.linalg.lstsq(Xrf/scale*sw[:,None], y*sw, rcond=1e-11)
    assert rank == Xrf.shape[1]
    coef /= scale; cf = y-Xrf@coef
    # DataFrame len counts rows. The restricted RF must omit the IV columns.
    rss = float(np.sum(wt*cf**2)); XX = Xrf[:, :1+rf_controls.shape[1]]
    bc = np.linalg.lstsq(XX*sw[:,None], y*sw, rcond=1e-11)[0]
    rss0 = float(np.sum(wt*(y-XX@bc)**2)); numiv = ivs.shape[1]
    rfdiag = {'rank': int(rank), 'columns': len(rfnames), 'income_center': ic,
              'r_squared': 1-rss/np.sum(wt*(y-np.average(y,weights=wt))**2),
              'excluded_current_income_partial_r_squared': 1-rss/rss0,
              'excluded_current_income_classical_f': (rss0-rss)/numiv/(rss/(len(b)-len(rfnames))),
              'excluded_current_income_names': list(ivs),
              'coefficients': dict(zip(rfnames, coef)), 'removed_columns': rf_removed+iv_removed}
    controls = pd.concat([z, means], axis=1)
    if spec['panel']: controls['mean_cf_residual'] = hhmean(pd.DataFrame({'cf': cf}), ids).cf
    controls, dropped_controls = identified(controls, np.column_stack([np.ones(len(b)), lp, y, cf]))
    # Participation uses the same historical boundaries and all identified means.
    selection = pd.DataFrame(lp, columns=PN)
    selection['ln_expenditure'] = y
    selection = pd.concat([selection, controls], axis=1)
    if hist:
        for code in (1, 2):
            for pn in PN: selection[f'history_{code}_{pn}'] = (codes == code)*b[pn]
            selection[f'history_{code}_ln_expenditure'] = (codes == code)*y
    selection['cf_residual'] = cf
    selection, removed_selection = identified(selection)
    # The first 13 native derivative positions must remain identified.
    assert list(selection)[:13] == PN+['ln_expenditure']
    selection_rank = rank_audit(np.column_stack([np.ones(len(b)), selection]))
    assert selection_rank['rank'] == selection_rank['columns']
    sc = selection.mean().to_numpy(); ss = selection.std(ddof=0).to_numpy()
    Xs = (selection.to_numpy()-sc)/ss
    tau = []; ki = []; pdiag = []
    for i in range(12):
        d = (b[f'X_{i+1}'] > 0).to_numpy(float)
        r,selection_method=finite_probit(d,Xs,tol=1e-10,max_iter=100)
        if r.dropped or not r.converged:
            save_pickle(WORK/f"{spec['name']}_failed_probit_{i+1}.pkl",
                         {'result':r,'X':Xs,'y':d,'names':list(selection),
                          'raw_centers':sc,'raw_scales':ss,'panel_ids':ids})
            raise RuntimeError(f"{spec['name']} Probit {i+1}: converged={r.converged}, dropped={r.dropped}")
        bt = np.r_[r.b[:-1]/ss, r.b[-1]-sc@(r.b[:-1]/ss)]
        tau.append(bt); ki.append(selection.to_numpy()@bt[:-1]+bt[-1])
        pdiag.append({'group': i+1, 'iterations': r.n_iter, 'converged': bool(r.converged),
                      'participation_rate': float(d.mean()), 'log_likelihood': float(r.llf),
                      'estimation_method':selection_method})
        print(f"{spec['name']} Probit {i+1}: {r.n_iter}", flush=True)
    tau = np.array(tau); k = np.array(ki).T
    sn = tuple(selection.columns)
    layout = FirstStageLayout(sn, tuple(PN), {pn: sn.index(pn) for pn in PN},
                              sn.index('ln_expenditure'), {}, sn.index('cf_residual'), len(sn))
    effective = np.repeat(tau[None,:,:], 3 if hist else 1, axis=0)
    if hist:
        for code in (1,2):
            for pn in PN:
                name = f'history_{code}_{pn}'
                if name in sn: effective[code,:,sn.index(pn)] += tau[:,sn.index(name)]
            name = f'history_{code}_ln_expenditure'
            if name in sn: effective[code,:,12] += tau[:,sn.index(name)]
    Z, centers, scales = scale_controls(controls, b.weight.to_numpy())
    additive = []
    if 'mean_cf_residual' in controls:
        j = list(controls).index('mean_cf_residual'); additive.append(j)
        centers[j] = 0.; Z[:,j] = controls.iloc[:,j]/scales[j]
    data = DemandData(lp, y, b[[f'w_{g}' for g in range(1,13)]].to_numpy(),
                      np.zeros((len(b),1)), norm.cdf(k), norm.pdf(k), manifest['a0'], cf)
    return {'version': VERSION, 'specification': spec, 'data': data, 'Z': Z,
            'centers': centers, 'scales': scales, 'control_names': list(controls),
            'additive_columns': additive, 'tau': tau, 'effective_tau': effective,
            'selection_names': list(sn), 'selection_index': k, 'layout': layout,
            'Xrf': Xrf, 'rf_names': rfnames, 'first_stage': rfdiag,
            'selection_diagnostics': pdiag, 'panel_ids': ids, 'year': b.year.to_numpy(),
            'cohort': b.cohort.to_numpy(), 'weights': b.weight.to_numpy(), 'regimes': codes,
            'level_names': list(z), 'mundlak_names': [c for c in controls if c.startswith('mean_')],
            'removed_columns': {'levels': dropped_level, 'base_exogenous_means': dropped_means,
                                'demand_controls': dropped_controls, 'selection': removed_selection},
            'rank_selection': selection_rank}


def core_for(stage):
    if stage['specification']['history']:
        return HistoricalCore(stage['data'], stage['Z'], stage['regimes'], stage['additive_columns'])
    return SpecificationCore(stage['data'], stage['Z'], stage['additive_columns'])


def reference(core, fit, stage, rows, code=0, common_point=False):
    d = core.data.subset(rows); zz = core.Z[rows].mean(axis=0)[None,:]
    kk = stage['selection_index'][rows].mean(axis=0)[None,:]
    if common_point:
        # Same global prices, expenditure, levels, means and CF in all regimes;
        # only current historical interactions and regime parameters change.
        lpmean=d.lnp.mean(axis=0); ymean=float(d.lnexp.mean())
        rawcontrols=zz[0]*stage['scales']+stage['centers']
        raw=dict(zip(stage['control_names'],rawcontrols))
        raw.update(dict(zip(PN,lpmean))); raw['ln_expenditure']=ymean
        raw['cf_residual']=float(d.control_function.mean())
        for rr in (1,2):
            for j,pn in enumerate(PN): raw[f'history_{rr}_{pn}']=(code==rr)*lpmean[j]
            raw[f'history_{rr}_ln_expenditure']=(code==rr)*ymean
        x=np.array([raw[name] for name in stage['selection_names']])
        kk=(stage['tau'][:,:-1]@x+stage['tau'][:,-1])[None,:]
    data = DemandData(d.lnp.mean(axis=0)[None,:], np.array([d.lnexp.mean()]),
                     d.shares.mean(axis=0)[None,:], np.zeros((1,1)),
                     norm.cdf(kk), norm.pdf(kk), d.a0, np.array([d.control_function.mean()]))
    if isinstance(core, HistoricalCore):
        c = HistoricalCore(data, zz, np.array([code]), stage['additive_columns'])
        tau = stage['effective_tau']
    else:
        c = SpecificationCore(data, zz, stage['additive_columns']); tau = stage['tau']
    mu = c.fitted(fit.theta)[0]
    dx, dp = c.fitted_derivatives(fit.theta, tau, stage['layout'], kk)
    invalid = (~np.isfinite(mu))|(mu <= 0)
    ex = 1+dx[0]/mu; mar = dp[0]/mu[:,None]-np.eye(12)
    ex[invalid] = np.nan; mar[invalid] = np.nan
    # Independent finite differences include the Probit price/expenditure channel.
    et = stage['effective_tau'][code] if isinstance(core,HistoricalCore) else stage['tau']
    audits = []; h = 1e-5
    oldp = data.lnp.copy(); oldy = data.lnexp.copy()
    for j in range(13):
        values = []
        for sign in (1,-1):
            data.lnp[:] = oldp; data.lnexp[:] = oldy
            if j < 12: data.lnp[0,j] += sign*h
            else: data.lnexp[0] += sign*h
            kval = kk+sign*h*et[:,j][None,:]
            data.cdf[:] = norm.cdf(kval); data.pdf[:] = norm.pdf(kval)
            # HistoricalCore copies input subsets into pieces only for normals;
            # fitted() constructs a fresh view from its current data.
            values.append(c.fitted(fit.theta)[0])
        analytic = dp[0,:,j] if j < 12 else dx[0]
        audits.append(float(np.max(np.abs((values[0]-values[1])/(2*h)-analytic))))
    return {'expenditure': ex, 'marshallian': mar, 'predicted_shares': mu,
            'predicted_share_sum': float(mu.sum()), 'invalid_share_groups': np.flatnonzero(invalid).tolist(),
            'log_prices': oldp[0], 'log_expenditure': float(oldy[0]),
            'max_derivative_absolute_error': max(audits), 'regime': int(code),
            'evaluation_basis': 'same global inputs across regimes' if common_point else 'actual subgroup inputs'}


def summarize(core, fit, stage, b):
    spec = stage['specification']; coefficients = {}
    for code in range(3 if spec['history'] else 1):
        nt, eta = core.unpack(fit.theta, code)
        c = unpack(nt, core.native)
        coefficients[str(code)] = {'alpha': c.alpha, 'beta': c.beta, 'Gamma': c.gamma,
                                   'lambda': c.lam, 'delta': c.delta, 'current_cf': c.cfcoef}
        np.testing.assert_allclose([c.alpha.sum(), c.beta.sum(), c.lam.sum()], [1,0,0], atol=1e-8)
        np.testing.assert_allclose(c.gamma.sum(axis=1), 0, atol=1e-8)
        np.testing.assert_allclose(c.gamma, c.gamma.T, atol=1e-8)
    refs = {}
    if spec['history']:
        for code in range(3): refs[f'period_{code}'] = reference(core,fit,stage,stage['regimes']==code,code)
        # A single discrete regime does not exist at a pooled mean. The overview
        # is explicitly a sample-count weighted mean of the three period points.
        weights = np.bincount(stage['regimes'],minlength=3)/len(b)
        refs['overall'] = {'expenditure': sum(weights[c]*refs[f'period_{c}']['expenditure'] for c in range(3)),
                           'marshallian': sum(weights[c]*refs[f'period_{c}']['marshallian'] for c in range(3)),
                           'definition': 'count-weighted mean of three period-specific at-means elasticities',
                           'period_weights': weights}
        for code in range(3):
            refs[f'common_reference_period_{code}']=reference(core,fit,stage,np.ones(len(b),bool),code,True)
    else: refs['overall'] = reference(core,fit,stage,np.ones(len(b),bool))
    pred = core.fitted(fit.theta)
    P = np.linalg.inv(np.linalg.cholesky(fit.sigma))
    G,g,obj = core.normal(fit.theta,core.data,core.spec,None,P,3000)
    direction = solver_direction(G,g)
    scaled = G/np.sqrt(np.diag(G))[:,None]/np.sqrt(np.diag(G))[None,:]
    eig = np.linalg.eigvalsh(scaled)
    convergence = {'converged': bool(fit.converged), 'parameters_finite': bool(np.isfinite(fit.theta).all()),
                   'outer_iterations': fit.n_outer, 'gn_iterations': fit.n_gn,
                   'objective': float(obj), 'objective_per_row': float(obj/len(b)),
                   'scaled_gn_ratio': abs(float(direction@g))/max(obj,1e-300),
                   'scaled_information_min_eigenvalue': float(eig.min()),
                   'scaled_information_condition': float(eig.max()/max(eig.min(),1e-300)),
                   'prediction_negative_fraction_by_group': (pred < 0).mean(axis=0),
                   'prediction_above_one_fraction_by_group': (pred > 1).mean(axis=0),
                   'prediction_sum_mean': float(pred.sum(axis=1).mean()),
                   'prediction_sum_p01_p99': np.quantile(pred.sum(axis=1),[.01,.99]),
                   'system_rmse': float(np.sqrt(np.mean((pred-core.data.shares)**2))),
                   'rmse_by_group': np.sqrt(np.mean((pred-core.data.shares)**2,axis=0)),
                   'sigma_log_determinant': float(np.linalg.slogdet(fit.sigma)[1]),
                   'gaussian_quasi_log_likelihood': float(fit.llf),
                   'point_seconds': fit.pilot_point_seconds,
                   'settings': fit.pilot_numerical_settings, 'history': fit.history}
    if not np.isfinite(pred).all(): raise RuntimeError('Nonfinite predicted shares')
    out = {'version': VERSION, 'specification': spec,
           'selection_audit_complete':stage.get('selection_audit_complete',False),
           'sample': {'rows': len(b), 'households': b.panel_id.nunique(),
                      'years': sorted(b.year.unique()), 'cohorts': sorted(b.cohort.unique()),
                      'by_year': b.year.value_counts().sort_index().to_dict()},
           'control_names': stage['control_names'], 'level_names': stage['level_names'],
           'mundlak_names': stage['mundlak_names'], 'additive_names': [stage['control_names'][j] for j in stage['additive_columns']],
           'coefficients': coefficients, 'control_coefficients_standardized': eta,
           'control_coefficients_original_units': eta/stage['scales'][:,None],
           'control_centers': stage['centers'], 'control_scales': stage['scales'],
           'selection_names': stage['selection_names'], 'selection_coefficients': stage['tau'],
           'first_stage': stage['first_stage'], 'selection': stage['selection_diagnostics'],
           'rank_selection': stage['rank_selection'], 'removed_columns': stage['removed_columns'],
           'demand_parameters': core.spec.n_free, 'convergence': convergence, 'elasticities': refs}
    if spec['panel']:
        raw=stage['Z']*stage['scales']+stage['centers']
        level=[stage['control_names'].index(name) for name in stage['level_names']]
        out['within_prices_after_time_controls']=conditional_within_prices(
            b,pd.DataFrame(raw[:,level],columns=stage['level_names']))
        span=b.groupby('panel_id').year.agg(['min','max'])
        out['households_crossing_boundaries']={str(cut):int(((span['min']<cut)&(span['max']>=cut)).sum()) for cut in (1397,1399)}
        out['within_between'] = {}
        for name in PN+['ln_exp']:
            vv = b[name].to_numpy(); mb = b.groupby('panel_id')[name].transform('mean').to_numpy()
            out['within_between'][name] = {'overall_sd': float(vv.std()),
                'within_sd': float((vv-mb).std()),
                'between_sd': float(b.groupby('panel_id')[name].mean().std(ddof=0)),
                'within_variance_fraction': float(np.var(vv-mb)/np.var(vv))}
        out['switching'] = {}
        for group in range(1,13):
            vals = (b[f'X_{group}'].to_numpy().reshape(-1,3)>0).sum(axis=1)
            out['switching'][str(group)] = {'always_zero': int((vals==0).sum()),
                 'always_positive': int((vals==3).sum()), 'switchers': int(((vals>0)&(vals<3)).sum())}
    return out


def _run_one(name):
    spec = MODEL_MAP[name]; start = time.time()
    b = model_frame(spec)
    sp = WORK/f'{name}_stage.pkl'; fp = WORK/f'{name}_fit.pkl'
    if sp.exists(): stage = pickle.load(open(sp,'rb')); assert stage['version'] == VERSION
    else: stage = make_stage(b,spec); save_pickle(sp,stage)
    core = core_for(stage)
    if fp.exists(): fit = pickle.load(open(fp,'rb'))
    else:
        common_name = name.replace('_history','_common') if spec['history'] else None
        backup=WORK/f'{name}_native_point_backup.pkl'
        if backup.exists():
            old_fit=pickle.load(backup.open('rb')); old_stage=stage
        elif common_name and (WORK/f'{common_name}_fit.pkl').exists():
            old_fit = pickle.load(open(WORK/f'{common_name}_fit.pkl','rb'))
            old_stage = pickle.load(open(WORK/f'{common_name}_stage.pkl','rb'))
        elif (INPUT/'suite_B1_no_season_means_point.pkl').exists():
            old_fit = pickle.load(open(INPUT/'suite_B1_no_season_means_point.pkl','rb'))
            old_stage = pickle.load(open(INPUT/'suite_B1_no_season_means_stage.pkl','rb'))
        else: old_fit=None;old_stage=None
        # The mapper accepts only the 122 native base parameters before shifters.
        if old_fit is None: th0=None
        elif backup.exists(): th0=old_fit.theta.copy()
        elif spec['history']:
            simple = SpecificationCore(stage['data'],stage['Z'],stage['additive_columns'])
            th0 = core.warm_start(warm_start(simple,stage,old_fit,old_stage))
        else: th0 = warm_start(core,stage,old_fit,old_stage)
        ts = time.time()
        def logger(msg): print(name, msg, flush=True)
        fit = core.fit(th0,old_fit.sigma if old_fit is not None else None,log=logger,gn_tol=1e-8)
        fit.pilot_point_seconds = time.time()-ts; fit.pilot_version = VERSION
        fit.pilot_start_model = common_name or 'previous_B1_no_season_means'
        save_pickle(fp,fit)
    if not fit.converged: raise RuntimeError(f'{name} did not converge; retain fit for diagnosis')
    out = summarize(core,fit,stage,b)
    out['total_seconds'] = time.time()-start
    dump(WORK/f'{name}_result.json',out)
    print('FINISHED',name,'rows',len(b),'seconds',out['total_seconds'],flush=True)
    return name


def run_one(name):
    # A model may already be running during queue startup/resume. A per-model
    # lock prevents duplicated estimation and concurrent cache writes.
    with (WORK/f'{name}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result_path = WORK/f'{name}_result.json'
        if result_path.exists():
            saved = json.loads(result_path.read_text())
            assert saved['version'] == VERSION and saved['convergence']['converged']
            print('REUSED',name,flush=True); return name
        return _run_one(name)


def refresh_results():
    """Postprocess saved fits after a reporting-code update; no re-estimation."""
    for spec in MODELS:
        name=spec['name']; path=WORK/f'{name}_result.json'
        saved=json.loads(path.read_text())
        if (saved.get('selection_audit_complete',False) and 'system_rmse' in saved['convergence'] and
            (not spec['panel'] or 'within_prices_after_time_controls' in saved) and
            (not spec['history'] or 'common_reference_period_0' in saved['elasticities'])):
            continue
        stage=pickle.load(open(WORK/f'{name}_stage.pkl','rb'))
        fit=pickle.load(open(WORK/f'{name}_fit.pkl','rb')); assert fit.converged
        out=summarize(core_for(stage),fit,stage,model_frame(spec))
        out['total_seconds']=saved['total_seconds']
        dump(path,out); print('REFRESHED',name,flush=True)


def subprocess_model(name):
    import subprocess
    logpath = WORK/f'{name}.log'
    with logpath.open('a') as f:
        r = subprocess.run([os.sys.executable,'-u','-m','pilot.b1_fourteen.run','--model',name],
                           cwd=REPO,stdout=f,stderr=subprocess.STDOUT)
    return {'name':name,'exit_code':r.returncode,'log':str(logpath)}


def run_all(workers):
    # Each historical fit starts only after its matching common model. Threads
    # merely launch independent processes; monkeypatched solver cores never share.
    pending = [m['name'] for m in MODELS if not (WORK/f"{m['name']}_result.json").exists()]
    done = {m['name'] for m in MODELS if m['name'] not in pending}; running = {}; failures = []
    external = {}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try: command = (proc/'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, PermissionError, ProcessLookupError): continue
        if b'pilot.b1_fourteen.run' in command and b'--model' in command:
            name = command[command.index(b'--model')+1].decode()
            if name in pending: external[name] = int(proc.name)
    def watch_existing(name,pid):
        while True:
            try:
                cmd = Path(f'/proc/{pid}/cmdline').read_bytes()
                if b'pilot.b1_fourteen.run' not in cmd: break
            except FileNotFoundError: break
            time.sleep(20)
        return {'name':name,'exit_code':0 if (WORK/f'{name}_result.json').exists() else 1,
                'adopted_existing_pid':pid}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for name,pid in external.items():
            running[pool.submit(watch_existing,name,pid)] = name; pending.remove(name)
            print('ADOPT',name,pid,flush=True)
        while pending or running:
            for name in list(pending):
                dependency = name.replace('_history','_common') if name.endswith('_history') else None
                if len(running) < workers and (dependency is None or dependency in done):
                    running[pool.submit(subprocess_model,name)] = name; pending.remove(name)
                    print('START',name,flush=True)
            if not running: break
            finished,_ = concurrent.futures.wait(running,return_when=concurrent.futures.FIRST_COMPLETED)
            for job in finished:
                name = running.pop(job); result = job.result(); print(result,flush=True)
                if result['exit_code'] == 0: done.add(name)
                else: failures.append(result)
            dump(WORK/'status.json',{'finished':sorted(done),'running':list(running.values()),
                                     'pending':pending,'failures':failures})
    actual={m['name'] for m in MODELS if (WORK/f"{m['name']}_result.json").exists()}
    failures=[f for f in failures if f['name'] not in actual]
    pending=[name for name in pending if name not in actual]
    dump(WORK/'status.json',{'finished':sorted(actual),'running':[],
                            'pending':pending,'failures':failures})
    if failures or pending: raise RuntimeError(f'Failed models: {failures}; blocked: {pending}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--prepare',action='store_true')
    ap.add_argument('--run-all',action='store_true'); ap.add_argument('--workers',type=int,default=2)
    ap.add_argument('--refresh-results',action='store_true')
    ap.add_argument('--model',choices=MODEL_MAP); args = ap.parse_args()
    if args.prepare: prepare()
    if args.model: run_one(args.model)
    if args.run_all: run_all(args.workers)
    if args.refresh_results: refresh_results()
