"""Three descriptive CS common/history comparisons, with frozen parameters.

1. Actual period means, aggregated using observation-count period weights.
2. Global reference with historical regimes activated, then the same weights.
3. Individual household-year elasticities: mean, median and validity diagnostics.

Microdata and individual arrays are written only to --work, never to this package.
"""
from pilot.b1_fourteen import run as base  # Preserve the existing BLAS policy.
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from scipy.stats import norm
from pyquaidsce.model import DemandData
from pyquaidsce.params import unpack
from pyquaidsce.selection import FirstStageLayout
from pilot.common.specification_core import SpecificationCore
from pilot.b1_fourteen.historical_core import HistoricalCore
from pilot.specification_followup.direct_elasticities import finite_difference_audit
from .prepare import sample_hash

OUT = Path(__file__).resolve().parent
SOURCE = base.REPO/'pilot/b1_fourteen_no_mean_cf/results.json'
SOURCE_COMMIT = '843d9d07241c35a720014b186e2779ad92517202'
MODELS = ('CS_All_common', 'CS_All_history', 'CS_B_common', 'CS_B_history')
FIELDS = [('alpha', 'alpha'), ('beta', 'beta'), ('gamma', 'Gamma'),
          ('lam', 'lambda'), ('delta', 'delta'), ('cfcoef', 'current_cf')]


def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [clean(v) for v in value]
    if isinstance(value, np.ndarray): return clean(value.tolist())
    if isinstance(value, (np.integer, np.bool_)): return value.item()
    if isinstance(value, (float, np.floating)): return float(value) if np.isfinite(value) else None
    return value


def build_core(frame, record, a0):
    """Recover RF inputs, Probit, translations and native constrained parameters."""
    raw = base.dummies(frame, True)[record['control_names']].copy()
    for price in base.PN: raw[price] = frame[price].to_numpy()
    raw['ln_expenditure'] = frame.ln_exp.to_numpy()
    raw['constant'] = 1.
    income = np.log(frame.total_income_real.to_numpy())-record['first_stage']['income_center']
    raw['ln_income_centered'] = income
    raw['ln_income_centered_squared'] = income**2
    codes = base.regimes(frame.year)
    if record['specification']['history']:
        for code in (1, 2):
            for name in base.PN+['ln_expenditure', 'ln_income_centered', 'ln_income_centered_squared']:
                raw[f'history_{code}_{name}'] = (codes == code)*raw[name]
    rfcoef = record['first_stage']['coefficients']
    cf = frame.ln_exp.to_numpy()-raw[list(rfcoef)].to_numpy()@np.array(list(rfcoef.values()))
    raw['cf_residual'] = cf
    Z = (raw[record['control_names']].to_numpy()-record['control_centers'])/record['control_scales']
    tau = np.array(record['selection_coefficients'])
    names = record['selection_names']
    k = raw[names].to_numpy()@tau[:, :-1].T+tau[:, -1]
    data = DemandData(frame[base.PN].to_numpy(), frame.ln_exp.to_numpy(),
                     frame[[f'w_{g}' for g in range(1, 13)]].to_numpy(), np.zeros((len(frame), 1)),
                     norm.cdf(k), norm.pdf(k), a0, cf)
    historical = record['specification']['history']
    core = HistoricalCore(data, Z, codes, []) if historical else SpecificationCore(data, Z, [])
    theta = np.zeros(core.spec.n_free)
    coefficient = record['coefficients']['0']
    for key, field in [('alpha', 'alpha'), ('beta', 'beta'), ('lambda', 'lambda'),
                       ('delta', 'delta'), ('cfcoef', 'current_cf')]:
        values = np.array(coefficient[field])
        theta[core.base_slices[key]] = values if key == 'delta' else values[:-1]
    gamma = np.array(coefficient['Gamma'])
    theta[core.base_slices['gamma']] = [gamma[i, j] for j in range(11) for i in range(j, 11)]
    if historical:
        for code in (1, 2):
            current = record['coefficients'][str(code)]
            gamma = np.array(current['Gamma'])-np.array(coefficient['Gamma'])
            theta[core.contrast_slice(code)] = np.r_[
                np.array(current['beta'])[:-1]-np.array(coefficient['beta'])[:-1],
                [gamma[i, j] for j in range(11) for i in range(j, 11)],
                np.array(current['lambda'])[:-1]-np.array(coefficient['lambda'])[:-1]]
    eta = np.array(record['control_coefficients_standardized'])
    theta[core.spec.nbase:] = eta[:, :-1].ravel()
    for code in range(3 if historical else 1):
        native, recovered = core.unpack(theta, code) if historical else core.unpack(theta)
        coefficients = unpack(native, core.native)
        for key, field in FIELDS:
            np.testing.assert_allclose(getattr(coefficients, key), record['coefficients'][str(code)][field],
                                       rtol=0, atol=2e-12)
        np.testing.assert_allclose(recovered, eta, rtol=0, atol=2e-12)
    layout = FirstStageLayout(tuple(names), tuple(base.PN), {p: names.index(p) for p in base.PN},
                              names.index('ln_expenditure'), {}, names.index('cf_residual'), len(names))
    effective = np.repeat(tau[None, :, :], 3 if historical else 1, axis=0)
    if historical:
        for code in (1, 2):
            for j, name in enumerate(base.PN+['ln_expenditure']):
                effective[code, :, j] += tau[:, names.index(f'history_{code}_{name}')]
    stage = dict(data=data, Z=Z, tau=tau, effective_tau=effective, selection_index=k, layout=layout,
                 additive_columns=[], scales=np.array(record['control_scales']),
                 centers=np.array(record['control_centers']), control_names=record['control_names'],
                 selection_names=names, regimes=codes)
    return core, SimpleNamespace(theta=theta), stage


def weighted_points(points, weights):
    return {'expenditure': sum(weights[i]*np.array(points[str(i)]['expenditure']) for i in range(3)),
            'marshallian': sum(weights[i]*np.array(points[str(i)]['marshallian']) for i in range(3)),
            'weights': weights}


def check_reference(actual, expected):
    errors = {}
    for key in ('expenditure', 'marshallian', 'predicted_shares', 'log_prices', 'log_expenditure'):
        if key not in expected: continue
        error = float(np.nanmax(abs(np.asarray(actual[key])-np.asarray(expected[key]))))
        assert error < 2e-9, (key, error)
        errors[key] = error
    return errors


def distribution(values, rows):
    data = np.asarray(values[rows])
    return {'mean': np.nanmean(data, axis=0), 'median': np.nanmedian(data, axis=0),
            'p01': np.nanquantile(data, .01, axis=0), 'p99': np.nanquantile(data, .99, axis=0),
            'min': np.nanmin(data, axis=0), 'max': np.nanmax(data, axis=0),
            'valid_count': np.isfinite(data).sum(axis=0),
            'absolute_above_100_count': (abs(data) > 100).sum(axis=0)}


def observation_summary(expenditure, marshallian, shares, rows):
    own = marshallian[:, np.arange(12), np.arange(12)]
    return {'rows': int(np.sum(rows)), 'expenditure': distribution(expenditure, rows),
            'own_price': distribution(own, rows),
            'marshallian_mean': np.nanmean(marshallian[rows], axis=0),
            'marshallian_median': np.nanmedian(marshallian[rows], axis=0),
            'invalid_share_count': ((~np.isfinite(shares[rows])) | (shares[rows] <= 0)).sum(axis=0),
            'positive_share_below_1e_6_count': ((shares[rows] > 0) & (shares[rows] < 1e-6)).sum(axis=0)}


def individual_audit(core, fit, stage, record, arrays):
    expenditure, marshallian, _ = arrays
    own = marshallian[:, np.arange(12), np.arange(12)]
    indices = np.unique(np.r_[np.linspace(0, len(expenditure)-1, 50, dtype=int),
                              np.nanargmax(abs(expenditure), axis=0), np.nanargmax(abs(own), axis=0)])
    reports = []
    for code in range(3 if record['specification']['history'] else 1):
        selected = indices[stage['regimes'][indices] == code] if record['specification']['history'] else indices
        # Include some points from every regime even if the largest ratios occur elsewhere.
        if not len(selected): selected = np.flatnonzero(stage['regimes'] == code)[:5]
        local = SpecificationCore(core.data.subset(selected), core.Z[selected], [])
        localfit = SimpleNamespace(theta=core.local_theta(fit.theta, code) if isinstance(core, HistoricalCore) else fit.theta)
        localstage = dict(selection_index=stage['selection_index'][selected],
                          layout=stage['layout'], tau=stage['effective_tau'][code if isinstance(core, HistoricalCore) else 0])
        audit = finite_difference_audit(local, localfit, localstage, slice(None), step=1e-5)
        assert audit['max_absolute_error'] < 1e-7, audit
        reports.append(dict(regime=code, **audit))
    return reports


def load_arrays(work, name):
    return tuple(np.load(work/f'{name}_{field}.npy', mmap_mode='r')
                 for field in ('individual_expenditure', 'individual_marshallian', 'predicted_shares'))


def paired_comparisons(work, common, historical, codes):
    c = load_arrays(work, common); h = load_arrays(work, historical)
    output = {}
    for label, rows in [('overall', np.ones(len(codes), bool))]+[(f'period_{i}', codes == i) for i in range(3)]:
        point = {}
        for kind, ca, ha in [('expenditure', c[0], h[0]),
                             ('own_price', c[1][:, np.arange(12), np.arange(12)], h[1][:, np.arange(12), np.arange(12)])]:
            ca = np.asarray(ca[rows]); ha = np.asarray(ha[rows])
            valid = np.isfinite(ca) & np.isfinite(ha)
            cv = np.where(valid, ca, np.nan); hv = np.where(valid, ha, np.nan)
            difference = hv-cv
            point[kind] = {'valid_pair_count': valid.sum(axis=0),
                           'common_mean': np.nanmean(cv, axis=0), 'historical_mean': np.nanmean(hv, axis=0),
                           'mean_difference': np.nanmean(difference, axis=0),
                           'common_median': np.nanmedian(cv, axis=0), 'historical_median': np.nanmedian(hv, axis=0),
                           'median_individual_difference': np.nanmedian(difference, axis=0)}
        output[label] = point
    return output


def run(work, output):
    frozen = json.loads(SOURCE.read_text())
    manifest = json.loads((base.OUT/'manifest.json').read_text())
    runs = {}
    for name in MODELS:
        print('MODEL', name, flush=True)
        record = next(r for r in frozen['runs'] if r['specification']['name'] == name)
        sample = record['specification']['sample']
        frame = pd.read_pickle(work/f'sample_{sample}.pkl')
        assert sample_hash(frame) == manifest['sample'][sample]['sample_hash']
        core, fit, stage = build_core(frame, record, manifest['a0'])
        codes = stage['regimes']; weights = np.bincount(codes, minlength=3)/len(frame)
        points = {str(i): base.reference(core, fit, stage, codes == i, i) for i in range(3)}
        checks = {}
        historical = record['specification']['history']
        if historical:
            common_refs = {str(i): base.reference(core, fit, stage, np.ones(len(frame), bool), i, True) for i in range(3)}
            for i in range(3):
                checks[f'period_{i}'] = check_reference(points[str(i)], record['elasticities'][f'period_{i}'])
                checks[f'common_reference_period_{i}'] = check_reference(common_refs[str(i)], record['elasticities'][f'common_reference_period_{i}'])
        else:
            global_ref = base.reference(core, fit, stage, np.ones(len(frame), bool))
            checks['global'] = check_reference(global_ref, record['elasticities']['overall'])
            common_refs = {str(i): global_ref for i in range(3)}
        method1 = weighted_points(points, weights)
        method2 = weighted_points(common_refs, weights)
        if historical: checks['overall'] = check_reference(method1, record['elasticities']['overall'])
        n = len(frame)
        paths = [work/f'{name}_{field}.npy' for field in ('individual_expenditure', 'individual_marshallian', 'predicted_shares')]
        # Always evaluate from the frozen coefficients rather than trusting unrelated caches.
        ex = np.lib.format.open_memmap(paths[0], mode='w+', dtype='float64', shape=(n, 12))
        mar = np.lib.format.open_memmap(paths[1], mode='w+', dtype='float64', shape=(n, 12, 12))
        shares = np.lib.format.open_memmap(paths[2], mode='w+', dtype='float64', shape=(n, 12))
        for start in range(0, n, 3000):
            rows = slice(start, min(n, start+3000))
            mu = core.fitted(fit.theta, rows)
            tau = stage['effective_tau'] if historical else stage['tau']
            dx, dp = core.fitted_derivatives(fit.theta, tau, stage['layout'], stage['selection_index'], rows)
            valid = np.isfinite(mu) & (mu > 0)
            xe = np.full_like(mu, np.nan); pe = np.full_like(dp, np.nan)
            np.divide(dx, mu, out=xe, where=valid); xe += 1
            np.divide(dp, mu[:, :, None], out=pe, where=valid[:, :, None]); pe -= np.eye(12)[None, :, :]
            xe[~np.isfinite(xe)] = np.nan; pe[~np.isfinite(pe)] = np.nan
            ex[rows] = xe; mar[rows] = pe; shares[rows] = mu
        ex.flush(); mar.flush(); shares.flush()
        stats = {'overall': observation_summary(ex, mar, shares, np.ones(n, bool))}
        for i in range(3): stats[f'period_{i}'] = observation_summary(ex, mar, shares, codes == i)
        expected = np.array(record['convergence']['prediction_negative_fraction_by_group'])*n
        np.testing.assert_allclose(stats['overall']['invalid_share_count'], expected, rtol=0, atol=1e-8)
        audit = individual_audit(core, fit, stage, record, (ex, mar, shares))
        # Means of valid observations recombine by group-specific valid counts,
        # not by the original period counts if validity differs across periods.
        for field in ('expenditure', 'own_price'):
            counts = np.array([stats[f'period_{i}'][field]['valid_count'] for i in range(3)])
            means = np.array([stats[f'period_{i}'][field]['mean'] for i in range(3)])
            recombined = (counts*means).sum(axis=0)/counts.sum(axis=0)
            np.testing.assert_allclose(recombined, stats['overall'][field]['mean'], rtol=1e-10, atol=1e-10)
        runs[name] = clean({'sample': record['sample'], 'sample_hash': sample_hash(frame), 'period_weights': weights,
                            'old_overall': record['elasticities']['overall'], 'method1_period_points': points,
                            'method1_overall': method1, 'method2_reference_points': common_refs,
                            'method2_overall': method2, 'method3': stats,
                            'verification': {'stored_reference_reproduction': checks, 'individual_derivative_audits': audit,
                                             'stored_negative_prediction_counts_match': True,
                                             'valid_period_means_recombine': True, 'model_reestimated': False}})
        print('FINISHED', name, 'method1 bread', method1['expenditure'][1],
              'method2 bread', method2['expenditure'][1], flush=True)
        del core, stage, frame, ex, mar, shares
    comparisons = {}
    for sample in ('All', 'B'):
        cn = f'CS_{sample}_common'; hn = f'CS_{sample}_history'
        c = runs[cn]; h = runs[hn]; result = {}
        for method in ('method1', 'method2'):
            result[method] = {key: np.array(h[f'{method}_overall'][key])-np.array(c[f'{method}_overall'][key])
                              for key in ('expenditure', 'marshallian')}
        old = {key: np.array(h['old_overall'][key])-np.array(c['old_overall'][key]) for key in ('expenditure', 'marshallian')}
        method_effect = {key: np.array(c['method1_overall'][key])-np.array(c['old_overall'][key])
                         for key in ('expenditure', 'marshallian')}
        for key in old:
            np.testing.assert_allclose(old[key], result['method1'][key]+method_effect[key], atol=2e-9, rtol=0)
        codes = base.regimes(pd.read_pickle(work/f'sample_{sample}.pkl').year)
        result['old_comparison'] = old
        result['common_summary_method_effect'] = method_effect
        result['method3_paired_valid'] = paired_comparisons(work, cn, hn, codes)
        result['method3_separate_valid'] = {
            label: {field: {stat: np.array(h['method3'][label][field][stat])-np.array(c['method3'][label][field][stat])
                            for stat in ('mean', 'median')}
                    for field in ('expenditure', 'own_price')}
            for label in ('overall', 'period_0', 'period_1', 'period_2')}
        comparisons[sample] = clean(result)
    payload = {'source_commit': SOURCE_COMMIT, 'source_results_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
               'package_commit': '636609f17e732a57b140cbbad5d2bf4042bc396a',
               'groups': frozen['groups'], 'periods': ['1392–1396', '1397–1398', '1399–1403'],
               'period_weight_definition': 'original estimation-sample observation count divided by sample N; no survey weights',
               'method3_definition': 'unweighted household-year mean and median over finite elasticities with positive fitted shares; no trimming or winsorization; group-specific valid counts',
               'method2_cf_convention': 'Keep each fitted model own full-sample mean CF residual fixed; activate current historical interactions in participation only, as existing common_reference_period outputs. Do not substitute a common residual or recompute RF at hypothetical regimes.',
               'inference': 'Descriptive frozen-parameter comparison; no new SE, bootstrap or statistical significance claim.',
               'runs': runs, 'comparisons': comparisons}
    output.write_text(json.dumps(clean(payload), ensure_ascii=False, indent=2)+'\n')
    print('SAVED', output, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, default=base.INPUT/'cs_summary_comparison')
    parser.add_argument('--output', type=Path, default=OUT/'results.json')
    args = parser.parse_args()
    run(args.work, args.output)
