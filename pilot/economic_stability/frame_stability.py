"""Pre/post-1397 slope stability with stacked, household-cluster inference.

Uses the cohort baseline, the same balanced sample and the same market prices.
No year, season, wave or new period-intercept dummy is introduced.
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
from pilot.common.regime_core import RegimeCore


def fit_frame(root):
    with (root/'frame_stage.pkl').open('rb') as f:
        stage = pickle.load(f)
    with (root/'cohort_cre_point.pkl').open('rb') as f:
        restricted = pickle.load(f)
    baseline = json.loads((root/'frame_base.json').read_text())
    regimes = (stage['year'] >= 1397).astype(int)
    core = RegimeCore(stage['data'], stage['Z'], regimes)
    key = {'version': 'prepost1397-cohort-v1',
           'sample_hash': baseline['sample']['sample_hash'],
           'names': stage['control_names'], 'blocks': core.blocks}
    path = root/'frame_temporal_point.pkl'
    start = time.time()
    if path.exists():
        with path.open('rb') as f:
            fit = pickle.load(f)
        if fit.pilot_frame_key != key:
            raise RuntimeError('Frame fit cache differs from the current design')
    else:
        def logger(msg):
            with (root/'frame_temporal_solver.log').open('a') as f:
                f.write(msg+'\n')
            print(msg, flush=True)
        fit = core.fit(core.warm_start(restricted.theta), restricted.sigma, logger)
        fit.pilot_frame_key = key
        fit.pilot_frame_seconds = time.time()-start
        with path.open('wb') as f:
            pickle.dump(fit, f)
    if not fit.converged or not np.isfinite(fit.theta).all():
        raise RuntimeError('Frame alternative failed convergence')
    print('FRAME POINT FIT READY', fit.n_outer, fit.n_gn,
          fit.pilot_frame_seconds, flush=True)
    return core, fit, stage, baseline


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--fit-only', action='store_true')
    p.add_argument('--output', type=Path,
                   default=Path(__file__).parent/'results_frame_stability.json')
    args = p.parse_args()
    core, fit, stage, baseline = fit_frame(args.inputs)
    if args.fit_only:
        return
    from pilot.common.frame_results import produce
    produce(core, fit, stage, baseline, args.inputs, args.output)


if __name__ == '__main__':
    main()
