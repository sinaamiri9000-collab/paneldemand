"""Drop Bachelor level/mean only from the three separated Probit equations.

python -m pilot.marital_participation_sensitivity.run --run-all --workers 2

Original stages/results are read-only. All other participation equations, CF,
latent controls, samples, prices and solver settings remain identical. The full
12-equation demand system is re-estimated after the single Probit is replaced.
"""
from pilot.b1_fourteen import run as base  # Set single-thread BLAS before NumPy.
import argparse
import concurrent.futures
import hashlib
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import norm

from pilot.b1_fourteen.probit_adapter import finite_probit, separation_certificate
from pilot.b1_fourteen.selection_audit import selection_matrix
from pilot.common.run import dump
from pilot.specification_suite.specification_suite import rank_audit


OUT = Path(__file__).resolve().parent
WORK = base.WORK.parent / 'marital_participation_sensitivity'
TARGETS = {'Panel_1398': 2, 'Panel_1399': 7, 'Panel_1401': 2}
DROP = ('marital_Bachelor', 'mean_marital_Bachelor')
VERSION = 'b1-marital-participation-2026-10-11-v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_one(name):
    WORK.mkdir(parents=True, exist_ok=True)
    result_path = WORK / f'{name}_result.json'
    if result_path.exists():
        result = json.loads(result_path.read_text())
        assert result['version'] == VERSION and result['convergence']['converged']
        return name
    start = time.time()
    sp = base.WORK / f'{name}_stage.pkl'
    fp = base.WORK / f'{name}_fit.pkl'
    original_hashes = {'stage': sha(sp), 'fit': sha(fp)}
    stage = pickle.load(sp.open('rb'))
    old_fit = pickle.load(fp.open('rb'))
    assert stage['selection_audit_complete'] and old_fit.converged
    group = TARGETS[name]
    target = group - 1
    names = stage['selection_names']
    assert all(n in names for n in DROP)
    assert stage['selection_diagnostics'][target]['estimation_method']['method'] == 'Jeffreys_prior_penalized_probit'
    b = base.model_frame(base.MODEL_MAP[name])
    X = selection_matrix(stage)
    keep = np.array([n not in DROP for n in names])
    center = X[:, keep].mean(axis=0)
    scale = X[:, keep].std(axis=0)
    Xs = (X[:, keep] - center) / scale
    rank = rank_audit(np.column_stack([Xs, np.ones(len(X))]))
    assert rank['rank'] == rank['columns']
    y = (stage['data'].shares[:, target] > 0).astype(float)
    cert = separation_certificate(y, np.column_stack([Xs, np.ones(len(X))]))
    assert not cert['separated'], 'Separation remains after dropping the Bachelor level and mean.'
    r, method = finite_probit(y, Xs, tol=1e-10, max_iter=100, certificate=cert)
    assert r.converged and not r.dropped and np.isfinite(r.b).all()
    assert method['method'] != 'Jeffreys_prior_penalized_probit'
    bt = np.zeros(len(names) + 1)
    bt[:-1][keep] = r.b[:-1] / scale
    bt[-1] = r.b[-1] - center @ (r.b[:-1] / scale)
    others = np.arange(12) != target
    old_other_cdf = stage['data'].cdf[:, others].copy()
    old_other_pdf = stage['data'].pdf[:, others].copy()
    old_other_tau = stage['tau'][others].copy()
    stage['tau'][target] = bt
    k = X @ bt[:-1] + bt[-1]
    stage['selection_index'][:, target] = k
    stage['data'].cdf[:, target] = norm.cdf(k)
    stage['data'].pdf[:, target] = norm.pdf(k)
    stage['effective_tau'] = stage['tau'][None, :, :].copy()
    np.testing.assert_array_equal(stage['data'].cdf[:, others], old_other_cdf)
    np.testing.assert_array_equal(stage['data'].pdf[:, others], old_other_pdf)
    np.testing.assert_array_equal(stage['tau'][others], old_other_tau)
    assert all(stage['tau'][target, names.index(n)] == 0 for n in DROP)
    diag = stage['selection_diagnostics'][target]
    diag.update(iterations=int(r.n_iter), converged=True, log_likelihood=float(r.llf),
                estimation_method=method, excluded_names=list(DROP),
                identified_rank=rank)
    stage['specification'] = dict(stage['specification'],
        name=name + '_drop_bachelor_participation', source_model=name,
        participation_exclusions={str(group): list(DROP)})
    # The common derivative layout is retained; omitted coefficients are exactly
    # zero in this equation. They remain estimated in the other 11 Probits.
    stage['selection_names_by_equation'] = {
        str(i + 1): [n for n in names if i != target or n not in DROP]
        for i in range(12)}
    stage_path = WORK / f'{name}_stage.pkl'
    fit_path = WORK / f'{name}_fit.pkl'
    cached_fit = None
    if fit_path.exists():
        previous_stage = pickle.load(stage_path.open('rb'))
        cached_fit = pickle.load(fit_path.open('rb'))
        assert cached_fit.pilot_version == VERSION and cached_fit.converged
        assert previous_stage['specification'] == stage['specification']
        for key in ('tau', 'selection_index', 'Z', 'centers', 'scales', 'panel_ids', 'year', 'Xrf'):
            np.testing.assert_array_equal(previous_stage[key], stage[key])
        for key in ('lnp', 'lnexp', 'shares', 'control_function', 'cdf', 'pdf'):
            np.testing.assert_array_equal(getattr(previous_stage['data'], key), getattr(stage['data'], key))
    base.save_pickle(stage_path, stage)
    print(name, 'regular Probit', group, method['method'],
          'iterations', r.n_iter, 'separation', cert['separated'], flush=True)
    core = base.core_for(stage)
    if cached_fit is None:
        ts = time.time()
        fit = core.fit(old_fit.theta.copy(), old_fit.sigma.copy(),
                       log=lambda msg: print(name, msg, flush=True), gn_tol=1e-8)
        fit.pilot_point_seconds = time.time() - ts
        fit.pilot_version = VERSION
        fit.pilot_start_model = name + '_Jeffreys_original'
    else:
        fit = cached_fit
        print(name, 'reuse verified converged fit', flush=True)
    assert fit.converged and np.isfinite(fit.theta).all()
    base.save_pickle(fit_path, fit)
    result = base.summarize(core, fit, stage, b)
    result['version'] = VERSION
    result['selection_names_by_equation'] = stage['selection_names_by_equation']
    result['sensitivity'] = {
        'source_model': name, 'target_group': group, 'excluded_names': list(DROP),
        'exclusion_scope': 'target Probit only; both current Bachelor and its three-wave household mean',
        'all_other_11_probits_identical': True,
        'latent_demand_controls_and_expenditure_CF_identical': True,
        'source_hashes': original_hashes,
        'separation_after_exclusion': cert,
        'probit_identified_rank': rank,
    }
    published = json.loads((base.OUT / 'results.json').read_text())
    before = next(q for q in published['runs'] if q['specification']['name'] == name)
    old = before['elasticities']['overall']
    new = result['elasticities']['overall']
    for key in ('rows', 'households', 'years', 'cohorts'):
        assert before['sample'][key] == result['sample'][key]
    assert before['sample']['by_year'] == {
        str(k): int(v) for k, v in result['sample']['by_year'].items()}
    own_delta = np.diag(np.array(new['marshallian']) - np.array(old['marshallian']))
    ex_delta = np.array(new['expenditure']) - np.array(old['expenditure'])
    mar_delta = np.array(new['marshallian']) - np.array(old['marshallian'])
    offdiag = np.abs(mar_delta).copy()
    np.fill_diagonal(offdiag, 0)
    pos = np.unravel_index(offdiag.argmax(), offdiag.shape)
    result['comparison'] = {
        'before_elasticities': old, 'after_elasticities': new,
        'own_price_difference': own_delta, 'expenditure_difference': ex_delta,
        'marshallian_difference': mar_delta,
        'max_absolute_own_difference': float(np.max(np.abs(own_delta))),
        'max_absolute_expenditure_difference': float(np.max(np.abs(ex_delta))),
        'max_absolute_cross_price_difference': float(offdiag.max()),
        'max_cross_price_pair': [int(pos[0] + 1), int(pos[1] + 1)],
        'before_selection': before['selection'][target],
        'before_convergence': before['convergence'],
        'definition': 'at the same cohort-sample mean; household means and CF fixed in derivatives',
    }
    result['total_seconds'] = time.time() - start
    assert original_hashes == {'stage': sha(sp), 'fit': sha(fp)}
    dump(result_path, result)
    print('FINISHED', name, result['total_seconds'], flush=True)
    return name


def child(name):
    with (WORK / f'{name}.log').open('w') as f:
        code = subprocess.run(
            [sys.executable, '-u', '-m', 'pilot.marital_participation_sensitivity.run',
             '--model', name], cwd=base.REPO, stdout=f, stderr=subprocess.STDOUT).returncode
    if code != 0: raise RuntimeError(f'{name} failed; see {WORK}/{name}.log')
    return name


def collect():
    runs = [json.loads((WORK / f'{name}_result.json').read_text()) for name in TARGETS]
    assert all(r['convergence']['converged'] for r in runs)
    dump(OUT / 'results.json', {'version': VERSION, 'groups': base.GROUPS,
        'scope': 'drop only Bachelor and mean Bachelor from the three previously separated participation equations',
        'baseline_results_sha256': sha(base.OUT / 'results.json'), 'runs': runs})


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', choices=TARGETS)
    ap.add_argument('--run-all', action='store_true')
    ap.add_argument('--workers', type=int, default=2)
    args = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    if args.model: run_one(args.model)
    if args.run_all:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for name in pool.map(child, TARGETS): print('COMPLETED', name, flush=True)
        collect()
