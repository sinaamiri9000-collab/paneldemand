"""Eleven prespecified new fits; two baselines and two pooled fits are reused.

python -m pilot.cohort1401_nuts_sensitivity.run --fixed
python -m pilot.cohort1401_nuts_sensitivity.run --run-all --workers 2

No bootstrap and no changes to QUAIDS quadratic terms, SY, price construction
or the cohort sample. Results are aggregate JSON; the research report is in chat.
"""
from .design import base, MODELS, SOURCE, load_baseline, build_stage, working_core, warm_start, rf_diagnostics
from .evaluate import point, micro, fixed_calculations, NUT
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
import pandas as pd
from pyquaidsce.params import unpack

OUT=Path(__file__).resolve().parent
WORK=base.WORK.parent/'cohort1401_nuts_sensitivity'
VERSION='cohort1401-nuts-fixed-QUAIDS-SY-2026-10-11-v1'


def clean(value):
    if isinstance(value,np.ndarray): return clean(value.tolist())
    if isinstance(value,np.generic): return clean(value.item())
    if isinstance(value,float) and not np.isfinite(value): return None
    if isinstance(value,dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [clean(v) for v in value]
    return value


def save_json(path,data):
    tmp=path.with_suffix('.part')
    tmp.write_text(json.dumps(clean(data),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    tmp.replace(path)


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def sample():
    return base.model_frame(base.MODEL_MAP['Panel_1401'])


def diagnostics(core,fit,stage,theta):
    P=np.linalg.inv(np.linalg.cholesky(fit.sigma))
    G,g,obj=core.normal(theta,core.data,core.spec,None,P,3000)
    step=base.solver_direction(G,g)
    scaled=G/np.sqrt(np.diag(G))[:,None]/np.sqrt(np.diag(G))[None,:]
    eig=np.linalg.eigvalsh(scaled)
    evalcore=base.core_for(stage); pred=evalcore.fitted(theta)
    nt,eta=evalcore.unpack(theta); c=unpack(nt,evalcore.native)
    np.testing.assert_allclose([c.alpha.sum(),c.beta.sum(),c.lam.sum(),c.cfcoef.sum()],[1,0,0,0],atol=1e-8)
    np.testing.assert_allclose(c.gamma.sum(1),0,atol=1e-8)
    np.testing.assert_allclose(c.gamma,c.gamma.T,atol=1e-8)
    np.testing.assert_allclose(eta.sum(1),0,atol=1e-8)
    assert np.isfinite(pred).all() and np.isfinite(theta).all()
    return {'converged':bool(fit.converged),'outer_iterations':int(fit.n_outer),
            'gn_ratio':float(abs(step@g)/obj),'min_scaled_information_eigenvalue':float(eig.min()),
            'scaled_information_condition':float(eig.max()/eig.min()),
            'prediction_negative_fraction_by_group':(pred<0).mean(0),
            'nuts_rmse':float(np.sqrt(np.mean((pred[:,NUT]-stage['data'].shares[:,NUT])**2))),
            'system_rmse':float(np.sqrt(np.mean((pred-stage['data'].shares)**2))),
            'nuts_beta':float(c.beta[NUT]),'nuts_lambda':float(c.lam[NUT]),
            'nuts_delta':float(c.delta[NUT]),'nuts_cf_loading':float(c.cfcoef[NUT]),
            'nuts_cf_probit_loading':float(stage['tau'][NUT,stage['layout'].selection_cf_position])
                if stage['layout'].selection_cf_position is not None else None,
            'parameters':len(theta),'theta':theta,'sigma':fit.sigma,
            'settings':fit.pilot_numerical_settings}


def run_model(name):
    WORK.mkdir(parents=True,exist_ok=True)
    with (WORK/f'{name}.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rp=WORK/f'{name}_result.json'
        if rp.exists():
            out=json.loads(rp.read_text()); assert out['version']==VERSION and out['diagnostics']['converged']
            return name
        start=time.time(); b=sample()
        sp=WORK/f'{name}_stage.pkl'; fp=WORK/f'{name}_fit.pkl'
        if sp.exists(): stage=pickle.load(sp.open('rb'))
        else: stage=build_stage(name,b); base.save_pickle(sp,stage)
        baseline,oldfit=load_baseline()
        for attr in ('lnp','lnexp','shares'):
            np.testing.assert_array_equal(getattr(stage['data'],attr),getattr(baseline['data'],attr))
        np.testing.assert_array_equal(stage['panel_ids'],baseline['panel_ids'])
        np.testing.assert_array_equal(stage['year'],baseline['year'])
        core=working_core(stage,name=='survey_weighted')
        if fp.exists(): fit=pickle.load(fp.open('rb'))
        else:
            th0=warm_start(core,stage,oldfit,baseline)
            fit=core.fit(th0,oldfit.sigma.copy(),gn_tol=1e-8,
                         log=lambda msg:print(name,msg,flush=True))
            fit.sensitivity_version=VERSION; base.save_pickle(fp,fit)
        assert fit.sensitivity_version==VERSION and fit.converged
        diag=diagnostics(core,fit,stage,fit.theta)
        assert diag['gn_ratio']<1e-8 and diag['min_scaled_information_eigenvalue']>0
        result={'version':VERSION,'name':name,'description':dict(MODELS)[name],
                'sample_rows':len(b),'households':b.panel_id.nunique(),'diagnostics':diag,
                'at_means':point(stage,fit.theta),
                'at_survey_weighted_means':point(stage,fit.theta,weights=stage['weights']),
                'by_year':{str(y):point(stage,fit.theta,b.year.to_numpy()==y) for y in sorted(b.year.unique())},
                'micro':micro(stage,fit.theta,b),
                'control_names':stage['control_names'],'additive_names':[stage['control_names'][j] for j in stage['additive_columns']],
                'control_centers':stage['centers'],'control_scales':stage['scales'],
                'selection_names':stage['selection_names'],'tau':stage['tau'],'a0':stage['data'].a0,
                'removed_controls':stage['sensitivity_removed'],'rf_reestimated':stage['rf_reestimated'],
                'first_stage':rf_diagnostics(stage),
                'nuts_participation_coefficients':dict(zip(stage['selection_names']+['constant'],stage['tau'][NUT])),
                'selection':stage['selection_diagnostics'],'seconds':time.time()-start,
                'weighted_likelihood':name=='survey_weighted'}
        save_json(rp,result)
        print('FINISHED',name,'expenditure',result['at_means']['nuts_expenditure'],flush=True)
        return name


def fixed():
    WORK.mkdir(parents=True,exist_ok=True); b=sample()
    out={'version':VERSION,'rows':len(b),'households':b.panel_id.nunique(),
         'years':sorted(b.year.unique()),'source_hashes':{
             str(p.relative_to(base.REPO)):digest(p) for p in
             [SOURCE/'Panel_1401_stage.pkl',SOURCE/'Panel_1401_fit.pkl',base.OUT/'results.json']},
         'baseline_original':{},'baseline_corrected':{},'pooled_comparators':{}}
    for original,key in [(True,'baseline_original'),(False,'baseline_corrected')]:
        stage,fit=load_baseline(original)
        out[key]=fixed_calculations(stage,fit.theta,b)
        out[key]['fit_diagnostics']=diagnostics(base.core_for(stage),fit,stage,fit.theta)
        out[key]['first_stage_recalculated']=rf_diagnostics(stage)
    for name in ('Panel_B_common','Panel_B_history'):
        stage=pickle.load((base.WORK/f'{name}_stage.pkl').open('rb'))
        fit=pickle.load((base.WORK/f'{name}_fit.pkl').open('rb'))
        rows=stage['cohort']==1401
        c=base.core_for(stage)
        ref=base.reference(c,fit,stage,rows,code=2 if name.endswith('history') else 0)
        out['pooled_comparators'][name]=ref
    w=b.w_9.to_numpy(); ln=b.ln_exp.to_numpy()
    within_ln=ln-base.hhmean(pd.DataFrame({'x':ln}),b.panel_id).x.to_numpy()
    price=b.lnp_9.to_numpy()
    within_price=price-base.hhmean(pd.DataFrame({'x':price}),b.panel_id).x.to_numpy()
    pattern=(w>0).reshape(-1,3).sum(1)
    out['data_diagnostics']={
        'purchase_rate':float(np.mean(w>0)),'always_zero_households':int((pattern==0).sum()),
        'always_buy_households':int((pattern==3).sum()),'switcher_households':int(((pattern>0)&(pattern<3)).sum()),
        'mean_observed_share':float(w.mean()),'positive_share_quartiles':np.quantile(w[w>0],[.25,.5,.75]),
        'within_log_expenditure_sd':float(within_ln.std()),'overall_log_expenditure_sd':float(ln.std()),
        'within_log_price_sd':float(within_price.std()),'overall_log_price_sd':float(price.std()),
        'purchase_rate_by_year':{str(y):float(np.mean(w[b.year.to_numpy()==y]>0)) for y in sorted(b.year.unique())}}
    mapping=pd.read_excel(base.INPUT/'final_commodity_mapping_107.xlsx')
    items=mapping[mapping.group_id==9]
    raw=pd.read_parquet(base.INPUT/'priced_panel_106.parquet',columns=['panel_id','year']+items.exp_var.tolist())
    matched=b[['panel_id','year','X_9']].merge(raw,on=['panel_id','year'],validate='one_to_one')
    np.testing.assert_allclose(matched[items.exp_var.tolist()].sum(1),matched.X_9,atol=1e-8,rtol=1e-12)
    out['nuts_item_expenditure_composition']={}
    for y in sorted(b.year.unique()):
        dd=matched[matched.year==y]
        out['nuts_item_expenditure_composition'][str(y)]={
            row.commodity_name:float(dd[row.exp_var].sum()/dd.X_9.sum()) for row in items.itertuples()}
    save_json(WORK/'fixed.json',out)
    print('FIXED COMPUTATIONS COMPLETE',flush=True)


def child(name):
    with (WORK/f'{name}.log').open('w') as log:
        status=subprocess.run([sys.executable,'-u','-m','pilot.cohort1401_nuts_sensitivity.run','--model',name],
                              cwd=base.REPO,stdout=log,stderr=subprocess.STDOUT).returncode
    return {'name':name,'exit_code':status}


def start_check():
    """One numerical check of the unchanged baseline, not a new specification.

    Start from the converged no-expenditure-means fit and add the original
    controls with zero loadings. This checks whether the large elasticity
    difference merely reflects different starting points/local solutions.
    """
    b=sample(); stage,original=load_baseline(); core=base.core_for(stage)
    other=pickle.load((WORK/'no_exp_means_fit.pkl').open('rb'))
    os=pickle.load((WORK/'no_exp_means_stage.pkl').open('rb'))
    fp=WORK/'baseline_alternative_start_fit.pkl'
    if fp.exists(): fit=pickle.load(fp.open('rb'))
    else:
        th0=warm_start(core,stage,other,os)
        fit=core.fit(th0,original.sigma.copy(),gn_tol=1e-8,
                     log=lambda msg:print('BASELINE_START_CHECK',msg,flush=True))
        base.save_pickle(fp,fit)
    assert fit.converged
    diag=diagnostics(core,fit,stage,fit.theta)
    assert diag['gn_ratio']<1e-8 and diag['min_scaled_information_eigenvalue']>0
    out={'same_specification_and_first_stages':True,
         'starting_solution':'no_exp_means; all original controls restored',
         'at_means':point(stage,fit.theta),'diagnostics':diag,
         'maximum_absolute_parameter_difference':float(np.max(abs(fit.theta-original.theta))),
         'maximum_absolute_fitted_share_difference':float(np.max(abs(core.fitted(fit.theta)-core.fitted(original.theta)))),
         'original_residual_covariance_logdet':float(np.linalg.slogdet(original.sigma)[1]),
         'alternative_residual_covariance_logdet':float(np.linalg.slogdet(fit.sigma)[1])}
    save_json(WORK/'baseline_start_check.json',out)
    print('BASELINE_START_CHECK_COMPLETE',out['at_means']['nuts_expenditure'],flush=True)


def collect():
    fixed=json.loads((WORK/'fixed.json').read_text())
    b=sample()
    results=[json.loads((WORK/f'{n}_result.json').read_text()) for n,_ in MODELS]
    for result in results:
        stage=pickle.load((WORK/f"{result['name']}_stage.pkl").open('rb'))
        result['first_stage']=clean(rf_diagnostics(stage))
        fit=pickle.load((WORK/f"{result['name']}_fit.pkl").open('rb'))
        result.update(at_means=clean(point(stage,fit.theta)),micro=clean(micro(stage,fit.theta,b)),
            at_survey_weighted_means=clean(point(stage,fit.theta,weights=stage['weights'])),
            control_centers=clean(stage['centers']),control_scales=clean(stage['scales']),
            selection_names=stage['selection_names'],tau=clean(stage['tau']),a0=stage['data'].a0)
    for p,h in fixed['source_hashes'].items(): assert digest(base.REPO/p)==h
    save_json(OUT/'results.json',{'version':VERSION,
        'prespecified_models':MODELS,'fixed_QUAIDS_and_SY':True,'fixed_sample_and_prices':True,
        'bootstrap_run':False,'fixed_calculations':fixed,'model_results':results,
        'baseline_alternative_start_check':json.loads((WORK/'baseline_start_check.json').read_text()),
        'method_notes':{
            'target':'cohort 1401, three waves 1401-1403; 5341 households, 16023 household-years',
            'demand':'same quadratic QUAIDS, exact S&Y equation, native pyquaidsce IFGNLS and latent restrictions; no AIDS, uncensored model or curvature restriction',
            'elasticity':'direct derivative of fitted unconditional quantity x*mu/p; means, CF residuals, weights and other controls fixed',
            'inference':'point sensitivities only; no final bootstrap or tests that differences between elasticities are statistically significant',
            'weighting':'yearly survey weight in RF throughout; normalized yearly weights additionally in Probit and IFGNLS only for survey_weighted',
            'rf_diagnostic_correction':'older fourteenth-suite diagnostic used len(DataFrame) as a column count; restricted equation inadvertently retained current income instruments. RF coefficients/residuals unchanged; this package recalculates the statistic.'}})


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--fixed',action='store_true')
    ap.add_argument('--run-all',action='store_true'); ap.add_argument('--workers',type=int,default=2)
    ap.add_argument('--model',choices=[n for n,_ in MODELS]); ap.add_argument('--collect',action='store_true')
    ap.add_argument('--start-check',action='store_true')
    args=ap.parse_args(); WORK.mkdir(parents=True,exist_ok=True)
    if args.fixed: fixed()
    if args.model: run_model(args.model)
    if args.start_check: start_check()
    if args.run_all:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            results=list(pool.map(child,[n for n,_ in MODELS]))
        save_json(WORK/'status.json',results); print(results,flush=True)
        assert all(r['exit_code']==0 for r in results)
        start_check()
        collect()
    if args.collect: collect()
