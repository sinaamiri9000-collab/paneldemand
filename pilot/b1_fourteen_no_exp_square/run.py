"""Refit ten panels; reuse four cross-sections and the original estimation core.

python -m pilot.b1_fourteen_no_exp_square.run --run-all --workers 2
python -m pilot.b1_fourteen_no_exp_square.publish

No price reconstruction, source-data edits, bootstrap, or QUAIDS/SY changes.
"""
from pilot.b1_fourteen import run as base  # Set single-thread BLAS first.
import argparse
import concurrent.futures
import fcntl
import hashlib
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
from pilot.b1_fourteen.selection_audit import selection_matrix
from pilot.b1_fourteen.probit_adapter import finite_probit
from pilot.cohort1401_nuts_sensitivity.design import rf_diagnostics
from pilot.cohort1401_nuts_sensitivity.run import clean, save_json
from pilot.specification_suite.specification_suite import rank_audit

OUT=Path(__file__).resolve().parent
WORK=base.INPUT/'b1_fourteen_no_exp_square'
VERSION='B1-fourteen-without-mean-squared-logexp-2026-10-12-v1'
MODELS=[m for m in base.MODELS if m['panel']]
NAMES=[m['name'] for m in MODELS]
CORRECTED={'Panel_1398','Panel_1399','Panel_1401'}
CORRECTION_ROOT=base.INPUT/'marital_participation_sensitivity'


def is_square_mean(name):
    return name.startswith('mean_') and name.endswith('centered_ln_expenditure_squared')


def source_paths(name):
    root=CORRECTION_ROOT if name in CORRECTED else base.WORK
    return root/f'{name}_stage.pkl',root/f'{name}_fit.pkl'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    WORK.mkdir(parents=True,exist_ok=True)
    path=WORK/'source_manifest.json'
    if path.exists(): return json.loads(path.read_text())
    paths=[base.OUT/'results.json',base.OUT/'manifest.json']
    for name in NAMES: paths.extend(source_paths(name))
    data=json.loads((base.OUT/'manifest.json').read_text())
    for name,expected in data['sources_sha256'].items():
        assert sha(base.INPUT/name)==expected
    assert sha(base.INPUT/'priced_panel_106.parquet')==data['priced_panel_sha256']
    manifest={'version':VERSION,'original_commit':'dfc9abd6c84e4326a90c1faf2490826dfc6b1796',
        'original_workbook_sha256':sha(base.OUT/'paneldemand_B1_fourteen_runs.xlsx'),
        'source_hashes':{str(p.relative_to(base.REPO)):sha(p) for p in paths},
        'frozen_data_manifest':data,'models':MODELS,
        'scope':'remove mean((log expenditure-fixed center)^2) and its historical mean interactions from participation and latent controls; retain mean log expenditure, CF, quadratic QUAIDS and exact SY',
        'previous_participation_corrections_preserved':sorted(CORRECTED)}
    save_json(path,manifest)
    return manifest


def trim_controls(stage):
    """Keep existing scaling, all retained controls, RF and data exactly fixed."""
    oldnames=stage['control_names']; X=selection_matrix(stage)
    removed=[c for c in oldnames if is_square_mean(c)]
    assert len(removed)==(3 if stage['specification']['history'] else 1)
    keep=np.array([not is_square_mean(c) for c in oldnames])
    stage['Z']=stage['Z'][:,keep]
    stage['centers']=stage['centers'][keep]; stage['scales']=stage['scales'][keep]
    additive=[oldnames[j] for j in stage['additive_columns']]
    stage['control_names']=[c for c,k in zip(oldnames,keep) if k]
    stage['additive_columns']=[stage['control_names'].index(c) for c in additive]
    stage['mundlak_names']=[c for c in stage['mundlak_names'] if not is_square_mean(c)]
    sk=np.array([not is_square_mean(c) for c in stage['selection_names']])
    X=X[:,sk]; stage['selection_names']=[c for c,k in zip(stage['selection_names'],sk) if k]
    assert 'mean_ln_expenditure' in stage['control_names']
    assert not any(is_square_mean(c) for c in stage['rf_names'])
    stage['removed_squared_expenditure_means']=removed
    return X


def build_stage(name):
    sp,_=source_paths(name); stage=pickle.load(sp.open('rb'))
    exclusions={str(i+1):d.get('excluded_names',[]) for i,d in enumerate(stage['selection_diagnostics'])}
    X=trim_controls(stage); sn=stage['selection_names']; d=stage['data']
    rank=rank_audit(np.column_stack([np.ones(len(X)),X]))
    assert rank['rank']==rank['columns']
    center=X.mean(0); scale=X.std(0); Xs=(X-center)/scale
    tau=[]; diagnostics=[]
    for i in range(12):
        keep=np.array([n not in exclusions[str(i+1)] for n in sn])
        y=(d.shares[:,i]>0).astype(float)
        fit,meta=finite_probit(y,Xs[:,keep],tol=1e-10,max_iter=100)
        assert fit.converged and not fit.dropped and np.isfinite(fit.b).all()
        # Removing regressors cannot create separation absent in the source.
        assert meta['method']!='Jeffreys_prior_penalized_probit'
        bt=np.zeros(len(sn)+1); bt[:-1][keep]=fit.b[:-1]/scale[keep]
        bt[-1]=fit.b[-1]-center[keep]@(fit.b[:-1]/scale[keep])
        tau.append(bt)
        diagnostics.append({'group':i+1,'iterations':int(fit.n_iter),'converged':True,
            'participation_rate':float(y.mean()),'log_likelihood':float(fit.llf),
            'estimation_method':meta,'excluded_names':[n for n,k in zip(sn,keep) if not k]})
        print(name,'Probit',i+1,meta['method'],flush=True)
    tau=np.array(tau); k=X@tau[:,:-1].T+tau[:,-1]
    effective=np.repeat(tau[None,:,:],3 if base.MODEL_MAP[name]['history'] else 1,axis=0)
    for code in range(1,len(effective)):
        for j,p in enumerate(base.PN+['ln_expenditure']):
            term=f'history_{code}_{p}'
            if term in sn: effective[code,:,j]+=tau[:,sn.index(term)]
    ordered=tuple(sn)
    layout=FirstStageLayout(ordered,tuple(base.PN),{p:sn.index(p) for p in base.PN},
        sn.index('ln_expenditure'),{},sn.index('cf_residual'),len(sn))
    stage.update(version=VERSION,specification=dict(base.MODEL_MAP[name],
        removed_mean_expenditure_square=True,participation_exclusions=exclusions),
        tau=tau,effective_tau=effective,selection_index=k,layout=layout,
        selection_diagnostics=diagnostics,rank_selection=rank,
        selection_names_by_equation={str(i+1):[n for n in sn if n not in exclusions[str(i+1)]] for i in range(12)},
        selection_audit_complete=True)
    stage['data']=DemandData(d.lnp,d.lnexp,d.shares,d.demo,norm.cdf(k),norm.pdf(k),d.a0,d.control_function)
    stage['first_stage']=rf_diagnostics(stage)  # Diagnostics only; RF/CF unchanged.
    return stage


def warm_start(core,stage,oldfit,oldstage):
    oldcore=base.core_for(oldstage)
    assert core.spec.nbase==oldcore.spec.nbase
    theta=np.zeros(core.spec.n_free)
    theta[:core.spec.nbase]=oldfit.theta[:oldcore.spec.nbase]
    oldeta=oldcore.unpack(oldfit.theta)[1]
    neweta=np.zeros((len(stage['control_names']),12))
    for j,n in enumerate(stage['control_names']):
        p=oldstage['control_names'].index(n)
        neweta[j]=oldeta[p]*stage['scales'][j]/oldstage['scales'][p]
    old_nonadd=~oldcore.additive_columns; new_nonadd=~core.additive_columns
    shift=oldstage['Z'].mean(0)[old_nonadd]@oldeta[old_nonadd]-stage['Z'].mean(0)[new_nonadd]@neweta[new_nonadd]
    theta[core.base_slices['alpha']]+=shift[:-1]
    theta[core.spec.nbase:]=neweta[:,:-1].ravel()
    return theta


def run_one(name):
    WORK.mkdir(parents=True,exist_ok=True)
    with (WORK/f'{name}.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rp=WORK/f'{name}_result.json'
        if rp.exists():
            r=json.loads(rp.read_text()); assert r['version']==VERSION and r['convergence']['converged']
            return name
        started=time.time(); b=base.model_frame(base.MODEL_MAP[name])
        sp=WORK/f'{name}_stage.pkl'; fp=WORK/f'{name}_fit.pkl'
        if sp.exists(): stage=pickle.load(sp.open('rb'))
        else: stage=build_stage(name); base.save_pickle(sp,stage)
        assert stage['version']==VERSION
        oldsp,oldfp=source_paths(name); oldstage=pickle.load(oldsp.open('rb')); oldfit=pickle.load(oldfp.open('rb'))
        for key in ('panel_ids','year','Xrf','weights'):
            np.testing.assert_array_equal(stage[key],oldstage[key])
        for key in ('lnp','lnexp','shares','control_function'):
            np.testing.assert_array_equal(getattr(stage['data'],key),getattr(oldstage['data'],key))
        core=base.core_for(stage)
        if fp.exists(): fit=pickle.load(fp.open('rb'))
        else:
            # The exact 1401 specification was already studied; use its solution
            # as a start, then actually re-estimate with the rebuilt participation.
            candidate=base.INPUT/'cohort1401_nuts_sensitivity'
            if name=='Panel_1401' and (candidate/'no_exp_square_fit.pkl').exists():
                oldstage=pickle.load((candidate/'no_exp_square_stage.pkl').open('rb'))
                oldfit=pickle.load((candidate/'no_exp_square_fit.pkl').open('rb'))
                start_label='previous_exact_1401_no_exp_square_solution'
            else: start_label='same_model_previous_corrected_solution'
            th0=warm_start(core,stage,oldfit,oldstage); ts=time.time()
            fit=core.fit(th0,oldfit.sigma.copy(),gn_tol=1e-8,log=lambda s:print(name,s,flush=True))
            fit.pilot_point_seconds=time.time()-ts; fit.pilot_version=VERSION; fit.pilot_start_model=start_label
            base.save_pickle(fp,fit)
        assert fit.converged and fit.pilot_version==VERSION
        result=base.summarize(core,fit,stage,b); result['version']=VERSION
        assert result['convergence']['scaled_gn_ratio']<1e-8
        assert result['convergence']['scaled_information_min_eigenvalue']>0
        assert not any(is_square_mean(n) for n in result['control_names']+result['selection_names'])
        result.update(total_seconds=time.time()-started,rf_reestimated=False,
            removed_squared_expenditure_means=stage['removed_squared_expenditure_means'],
            starting_solution=fit.pilot_start_model)
        save_json(rp,result)
        print('FINISHED',name,'nuts expenditure',result['elasticities']['overall']['expenditure'][8],flush=True)
        return name


def child(name):
    with (WORK/f'{name}.log').open('a') as log:
        code=subprocess.run([sys.executable,'-u','-m','pilot.b1_fourteen_no_exp_square.run','--model',name],
            cwd=base.REPO,stdout=log,stderr=subprocess.STDOUT).returncode
    if code: raise RuntimeError(f'{name} failed; inspect {WORK/name}.log')
    return name


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--model',choices=NAMES)
    ap.add_argument('--run-all',action='store_true'); ap.add_argument('--workers',type=int,default=2)
    args=ap.parse_args(); WORK.mkdir(parents=True,exist_ok=True)
    if args.model: run_one(args.model)
    if args.run_all:
        prepare()
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for name in pool.map(child,NAMES): print('COMPLETED',name,flush=True)
