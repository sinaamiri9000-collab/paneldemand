"""Two explicit-baseline fits; results are reported in chat.

python -m pilot.cohort1401_no_exp_square_followup.run --run-all

No changes to the active fourteen-model workbook or any previous result.
"""
from pilot.b1_fourteen import run as base
from pilot.b1_fourteen_no_exp_square.run import warm_start,is_square_mean,sha
from pilot.cohort1401_nuts_sensitivity.design import build_stage,working_core,rf_diagnostics
from pilot.cohort1401_nuts_sensitivity.run import diagnostics,clean,save_json
from pilot.cohort1401_nuts_sensitivity.evaluate import point
import argparse
import concurrent.futures
import copy
import fcntl
import json
import pickle
import subprocess
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent
WORK=base.INPUT/'cohort1401_no_exp_square_followup'
SOURCE=base.INPUT/'b1_fourteen_no_exp_square'
MODELS=('no_mean_cf','survey_weighted')
VERSION='1401-no-mean-squared-logexp-CF-and-weight-followup-2026-10-12-v1'


def run_model(name):
    WORK.mkdir(parents=True,exist_ok=True)
    with (WORK/f'{name}.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        result_path=WORK/f'{name}_result.json'
        if result_path.exists():
            old=json.loads(result_path.read_text()); assert old['version']==VERSION
            assert old['diagnostics']['converged']; return name
        sp=SOURCE/'Panel_1401_stage.pkl'; fp=SOURCE/'Panel_1401_fit.pkl'
        hashes={str(p.relative_to(base.REPO)):sha(p) for p in (sp,fp)}
        original=pickle.load(sp.open('rb')); baseline_fit=pickle.load(fp.open('rb'))
        assert not any(is_square_mean(n) for n in original['control_names'])
        baseline=copy.deepcopy(original)
        b=base.model_frame(base.MODEL_MAP['Panel_1401'])
        started_at=datetime.now(timezone.utc).isoformat()
        started=time.perf_counter()
        # Repeat the same weighted RF in both runs, recording its actual time.
        # This stage was already survey-weighted in the baseline.
        rf_start=time.perf_counter(); X=baseline['Xrf']; y=baseline['data'].lnexp
        w=baseline['weights']/baseline['weights'].mean(); sw=np.sqrt(w)
        scale=X.std(0); scale[0]=1.
        coef,_,rank,_=np.linalg.lstsq(X/scale*sw[:,None],y*sw,rcond=1e-11)
        assert rank==X.shape[1]; coef/=scale
        cf=y-X@coef
        np.testing.assert_allclose(cf,original['data'].control_function,atol=3e-10)
        baseline['data'].control_function=cf
        baseline['first_stage']['coefficients']=dict(zip(baseline['rf_names'],coef))
        rf_seconds=time.perf_counter()-rf_start
        selection_start=time.perf_counter()
        stage=build_stage(name,b,baseline=(baseline,baseline_fit))
        selection_seconds=time.perf_counter()-selection_start
        assert not any(is_square_mean(n) for n in stage['control_names']+stage['selection_names'])
        assert ('mean_cf_residual' in stage['control_names'])==(name=='survey_weighted')
        assert 'mean_ln_expenditure' in stage['control_names']
        for key in ('panel_ids','year','weights','Xrf'):
            np.testing.assert_array_equal(stage[key],original[key])
        for key in ('lnp','lnexp','shares'):
            np.testing.assert_array_equal(getattr(stage['data'],key),getattr(original['data'],key))
        core=working_core(stage,name=='survey_weighted')
        th0=warm_start(core,stage,baseline_fit,original)
        fit_start=time.perf_counter()
        fit=core.fit(th0,baseline_fit.sigma.copy(),gn_tol=1e-8,
                     log=lambda text:print(name,text,flush=True))
        demand_seconds=time.perf_counter()-fit_start
        convergence_seconds=time.perf_counter()-started
        assert fit.converged
        fit.pilot_point_seconds=demand_seconds; fit.pilot_version=VERSION
        diag=diagnostics(core,fit,stage,fit.theta)
        assert diag['gn_ratio']<1e-8 and diag['min_scaled_information_eigenvalue']>0
        assert all(s['estimation_method']['method']!='Jeffreys_prior_penalized_probit'
                   for s in stage['selection_diagnostics'])
        baseline_point=point(original,baseline_fit.theta)
        result={'version':VERSION,'name':name,'years':[1401,1402,1403],
            'rows':len(b),'households':int(b.panel_id.nunique()),
            'source_hashes':hashes,'mean_squared_log_expenditure_removed':True,
            'mean_log_expenditure_retained':True,'current_CF_retained':True,
            'mean_CF_retained':name=='survey_weighted',
            'weighting':{'RF':True,'participation':name=='survey_weighted','QUAIDS':name=='survey_weighted',
                'household_means':'unweighted three-wave average; yearly survey weights normalized to mean one'},
            'QUAIDS_and_SY_unchanged':True,'bread_participation_Bachelor_exclusions_preserved':True,
            'timing_seconds':{'weighted_RF':rf_seconds,'participation_and_design':selection_seconds,
                'QUAIDS_IFGNLS':demand_seconds,'total_to_convergence':convergence_seconds,
                'started_UTC':started_at,'definition':'actual wall time with two concurrent processes, single BLAS thread each; includes RF, selection/design, and fitting; excludes subsequent reporting/audits'},
            'diagnostics':diag,'at_common_unweighted_means':point(stage,fit.theta),
            'at_survey_weighted_means':point(stage,fit.theta,weights=stage['weights']),
            'baseline_at_common_unweighted_means':baseline_point,
            'control_names':stage['control_names'],'control_centers':stage['centers'],'control_scales':stage['scales'],
            'selection_names':stage['selection_names'],'tau':stage['tau'],
            'selection':stage['selection_diagnostics'],'first_stage':rf_diagnostics(stage),
            'bootstrap_run':False}
        for p,h in hashes.items(): assert sha(base.REPO/p)==h
        base.save_pickle(WORK/f'{name}_stage.pkl',stage)
        base.save_pickle(WORK/f'{name}_fit.pkl',fit)
        save_json(result_path,result)
        print('FINISHED',name,'total_to_convergence_seconds',convergence_seconds,flush=True)
        return name


def child(name):
    with (WORK/f'{name}.log').open('a') as log:
        code=subprocess.run([sys.executable,'-u','-m','pilot.cohort1401_no_exp_square_followup.run','--model',name],
            cwd=base.REPO,stdout=log,stderr=subprocess.STDOUT).returncode
    if code: raise RuntimeError(f'{name} failed; inspect {WORK/name}.log')
    return name


def collect():
    runs=[json.loads((WORK/f'{n}_result.json').read_text()) for n in MODELS]
    assert all(r['diagnostics']['converged'] for r in runs)
    save_json(OUT/'results.json',{'version':VERSION,'groups':base.GROUPS,'runs':runs,
        'evaluation':'same unweighted geometric price/expenditure reference as the latest 1401 baseline; household means and CF fixed in current-input derivatives',
        'report':'full own-price/expenditure tables and actual convergence timings delivered in chat'})


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--model',choices=MODELS)
    ap.add_argument('--run-all',action='store_true'); args=ap.parse_args()
    WORK.mkdir(parents=True,exist_ok=True)
    if args.model: run_model(args.model)
    if args.run_all:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for name in pool.map(child,MODELS): print('COMPLETED',name,flush=True)
        collect()
