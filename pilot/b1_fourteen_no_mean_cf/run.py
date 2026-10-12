"""Remove mean CF from the current ten panels; keep RF, QUAIDS and SY fixed.

python -m pilot.b1_fourteen_no_mean_cf.run --run-all --workers 2
"""
from pilot.b1_fourteen import run as base  # Set single-thread BLAS first.
from pilot.b1_fourteen_no_exp_square.run import warm_start, is_square_mean, sha
from pilot.b1_fourteen.selection_audit import selection_matrix
from pilot.b1_fourteen.probit_adapter import finite_probit
from pilot.specification_suite.specification_suite import rank_audit
from pilot.cohort1401_nuts_sensitivity.run import clean, save_json
import argparse
import concurrent.futures
import fcntl
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
from scipy.stats import norm
from pyquaidsce.model import DemandData
from pyquaidsce.selection import FirstStageLayout

OUT = Path(__file__).resolve().parent
SOURCE = base.INPUT / 'b1_fourteen_no_exp_square'
WORK = base.INPUT / 'b1_fourteen_no_mean_cf'
VERSION = 'B1-fourteen-without-mean-CF-and-mean-squared-logexp-2026-10-12-v1'
MODELS = [m for m in base.MODELS if m['panel']]
NAMES = [m['name'] for m in MODELS]
REMOVED = 'mean_cf_residual'
PREVIOUS = OUT.parent / 'b1_fourteen_no_exp_square' / 'results.json'


def source_paths(name):
    return SOURCE / f'{name}_stage.pkl', SOURCE / f'{name}_fit.pkl'


def prepare():
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / 'source_manifest.json'
    if path.exists():
        manifest = json.loads(path.read_text())
    else:
        paths = [PREVIOUS, base.OUT / 'paneldemand_B1_fourteen_runs.xlsx']
        for name in NAMES:
            paths.extend(source_paths(name))
        manifest = dict(version=VERSION, previous_commit='be4e5f48417670c5fab24f40567e58c4c941e309',
            source_hashes={str(p.relative_to(base.REPO)): sha(p) for p in paths},
            scope='remove mean_cf_residual from participation and latent demand; retain current CF, mean log expenditure, no mean squared log expenditure, same RF, controls, prices and sample',
            models=MODELS)
        save_json(path, manifest)
    assert manifest['version'] == VERSION
    # The active workbook will change on publication, but frozen inputs may not.
    for p, h in manifest['source_hashes'].items():
        if p.endswith('.xlsx'): continue
        assert sha(base.REPO / p) == h, p
    return manifest


def trim_controls(stage):
    names = stage['control_names']
    assert names.count(REMOVED) == 1
    assert not any(is_square_mean(n) for n in names)
    assert REMOVED not in stage['rf_names']
    X = selection_matrix(stage)
    additive = [names[j] for j in stage['additive_columns']]
    keep = np.array([n != REMOVED for n in names])
    stage['Z'] = stage['Z'][:, keep]
    stage['centers'] = stage['centers'][keep]
    stage['scales'] = stage['scales'][keep]
    stage['control_names'] = [n for n in names if n != REMOVED]
    stage['additive_columns'] = [stage['control_names'].index(n) for n in additive if n != REMOVED]
    stage['mundlak_names'] = [n for n in stage['mundlak_names'] if n != REMOVED]
    keep = np.array([n != REMOVED for n in stage['selection_names']])
    X = X[:, keep]
    stage['selection_names'] = [n for n in stage['selection_names'] if n != REMOVED]
    assert 'mean_ln_expenditure' in stage['control_names']
    assert 'cf_residual' in stage['selection_names']
    return X


def build_stage(name):
    sp, _ = source_paths(name)
    stage = pickle.load(sp.open('rb'))
    exclusions = {str(i+1): d.get('excluded_names', []) for i, d in enumerate(stage['selection_diagnostics'])}
    X = trim_controls(stage)
    sn = stage['selection_names']; d = stage['data']
    rank = rank_audit(np.column_stack([np.ones(len(X)), X]))
    assert rank['rank'] == rank['columns']
    center = X.mean(0); scale = X.std(0); Xs = (X-center)/scale
    tau = []; diagnostics = []
    for i in range(12):
        keep = np.array([n not in exclusions[str(i+1)] for n in sn])
        y = (d.shares[:, i] > 0).astype(float)
        fit, meta = finite_probit(y, Xs[:, keep], tol=1e-10, max_iter=100)
        assert fit.converged and not fit.dropped and np.isfinite(fit.b).all()
        assert meta['method'] != 'Jeffreys_prior_penalized_probit'
        bt = np.zeros(len(sn)+1)
        bt[:-1][keep] = fit.b[:-1]/scale[keep]
        bt[-1] = fit.b[-1] - center[keep] @ (fit.b[:-1]/scale[keep])
        tau.append(bt)
        diagnostics.append(dict(group=i+1, iterations=int(fit.n_iter), converged=True,
            participation_rate=float(y.mean()), log_likelihood=float(fit.llf),
            estimation_method=meta, excluded_names=[n for n, k in zip(sn, keep) if not k]))
        print(name, 'Probit', i+1, meta['method'], flush=True)
    tau = np.array(tau); k = X @ tau[:, :-1].T + tau[:, -1]
    effective = np.repeat(tau[None, :, :], 3 if base.MODEL_MAP[name]['history'] else 1, axis=0)
    for code in range(1, len(effective)):
        for j, p in enumerate(base.PN + ['ln_expenditure']):
            term = f'history_{code}_{p}'
            if term in sn: effective[code, :, j] += tau[:, sn.index(term)]
    layout = FirstStageLayout(tuple(sn), tuple(base.PN), {p: sn.index(p) for p in base.PN},
        sn.index('ln_expenditure'), {}, sn.index('cf_residual'), len(sn))
    stage.update(version=VERSION,
        specification=dict(stage['specification'], removed_mean_cf=True),
        tau=tau, effective_tau=effective, selection_index=k, layout=layout,
        selection_diagnostics=diagnostics, rank_selection=rank,
        selection_names_by_equation={str(i+1): [n for n in sn if n not in exclusions[str(i+1)]] for i in range(12)},
        selection_audit_complete=True, removed_cf_means=[REMOVED])
    stage['data'] = DemandData(d.lnp, d.lnexp, d.shares, d.demo, norm.cdf(k), norm.pdf(k), d.a0, d.control_function)
    return stage


def run_one(name):
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / f'{name}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rp = WORK / f'{name}_result.json'
        if rp.exists():
            r = json.loads(rp.read_text())
            assert r['version'] == VERSION and r['convergence']['converged']
            return name
        started = time.perf_counter()
        b = base.model_frame(base.MODEL_MAP[name])
        oldsp, oldfp = source_paths(name)
        original = pickle.load(oldsp.open('rb')); oldfit = pickle.load(oldfp.open('rb'))
        sp = WORK / f'{name}_stage.pkl'; fp = WORK / f'{name}_fit.pkl'
        if sp.exists(): stage = pickle.load(sp.open('rb'))
        else:
            stage = build_stage(name); base.save_pickle(sp, stage)
        assert stage['version'] == VERSION
        for key in ('panel_ids', 'year', 'Xrf', 'weights'):
            np.testing.assert_array_equal(stage[key], original[key])
        for key in ('lnp', 'lnexp', 'shares', 'control_function'):
            np.testing.assert_array_equal(getattr(stage['data'], key), getattr(original['data'], key))
        core = base.core_for(stage)
        if fp.exists(): fit = pickle.load(fp.open('rb'))
        else:
            th0 = warm_start(core, stage, oldfit, original)
            ts = time.perf_counter()
            fit = core.fit(th0, oldfit.sigma.copy(), gn_tol=1e-8,
                log=lambda s: print(name, s, flush=True))
            fit.pilot_point_seconds = time.perf_counter()-ts
            fit.pilot_version = VERSION
            fit.pilot_start_model = 'previous_same_model_without_mean_squared_logexp'
            base.save_pickle(fp, fit)
        assert fit.converged and fit.pilot_version == VERSION
        result = base.summarize(core, fit, stage, b)
        assert result['convergence']['scaled_gn_ratio'] < 1e-8
        assert result['convergence']['scaled_information_min_eigenvalue'] > 0
        assert REMOVED not in result['control_names'] + result['selection_names']
        assert not any(is_square_mean(n) for n in result['control_names'] + result['selection_names'])
        result.update(version=VERSION, total_seconds=time.perf_counter()-started,
            rf_reestimated=False, removed_cf_means=[REMOVED],
            starting_solution=fit.pilot_start_model)
        save_json(rp, result)
        print('FINISHED', name, 'nuts expenditure', result['elasticities']['overall']['expenditure'][8], flush=True)
        return name


def child(name):
    with (WORK / f'{name}.log').open('a') as log:
        code = subprocess.run([sys.executable, '-u', '-m', 'pilot.b1_fourteen_no_mean_cf.run', '--model', name],
            cwd=base.REPO, stdout=log, stderr=subprocess.STDOUT).returncode
    if code: raise RuntimeError(f'{name} failed; inspect {WORK/name}.log')
    return name


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--model', choices=NAMES)
    ap.add_argument('--run-all', action='store_true'); ap.add_argument('--workers', type=int, default=2)
    args = ap.parse_args(); WORK.mkdir(parents=True, exist_ok=True)
    if args.model:
        prepare(); run_one(args.model)
    if args.run_all:
        prepare()
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for name in pool.map(child, NAMES): print('COMPLETED', name, flush=True)
