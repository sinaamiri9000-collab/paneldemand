"""Restricted-score complements to the uncensored stability Wald tests.

Robust score/LM principle: Wooldridge (1990), Econometric Theory 6:17--43,
MIT WP 480 (1988), especially nonlinear least-squares/QML examples 3.1/3.3.
This implementation uses the full observed estimating-equation Jacobian and
household score sums, not an iid TR-squared or likelihood-ratio shortcut.
"""
import os
for key in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[key] = '1'
import argparse
import json
import pickle
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from threadpoolctl import threadpool_limits
from plain_core import PlainCore
from plain_stability import plain_covariance
from run import dump
from frame_results import economic_comparison


def main():
    p = argparse.ArgumentParser(); p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--results', type=Path, default=Path(__file__).parent/'results_plain_stability.json')
    args = p.parse_args(); root = args.inputs
    with (root/'frame_stage.pkl').open('rb') as f: stage = pickle.load(f)
    with (root/'plain_common_point.pkl').open('rb') as f: common = pickle.load(f)
    r = json.loads(args.results.read_text())
    # Classification can be regenerated cheaply from the saved point differences
    # and standard errors, without refitting or rerunning the delta method.
    for kind in ['frame','temporal','cohort']:
        if kind in r:
            model = r[kind]
            for key, diff in model['elasticity_differences'].items():
                model['economic_comparisons'][key] = economic_comparison(
                    diff, model['elasticity_difference_standard_errors'][key])
    for kind in ['frame','temporal','cohort']:
        if kind not in r: continue
        model = r[kind]
        if 'robust_restricted_score_equal' in model['tests']: continue
        if kind == 'frame': regimes = (stage['year'] >= 1397).astype(int)
        elif kind == 'temporal':
            regimes = np.select([stage['year'] <= 1396, stage['year'] <= 1399], [0,1], default=2)
        else:
            regimes = np.searchsorted(np.sort(np.unique(stage['cohort'])), stage['cohort'])
        core = PlainCore(stage, regimes, tuple(model['blocks_allowed_to_vary']))
        fit = SimpleNamespace(theta=core.warm_from_plain(common.theta), sigma=common.sigma)
        with threadpool_limits(limits=3):
            test = plain_covariance(core, fit, score_test=True)
        model['tests']['robust_restricted_score_equal'] = test
        dump(args.results, r)
        print('ROBUST RESTRICTED SCORE', kind, test, flush=True)
    dump(args.results, r)


if __name__ == '__main__': main()
