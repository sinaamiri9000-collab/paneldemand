"""Prespecified entry-cohort then annual slope stability, maintained SY/CF.

Native QUAIDS restrictions/solver/elasticities are reused. Restricted-score
tests use the observed estimating-equation Jacobian, household clusters, and
generated WLS/Probit/Sigma uncertainty. No unknown-break search or bootstrap.
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
import json
import pickle
import time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from scipy.stats import norm
from threadpoolctl import threadpool_limits
from pyquaidsce.model import DemandData
from pyquaidsce.params import unpack
from pilot.common.regime_core import RegimeCore
from pilot.common.staged_inference import recover_design, stacked_covariance, scaled_solve
from pilot.preliminary_stability.stability import robust_wald, index_R
from pilot.common.frame_results import ReferenceElasticities, unpack_e, economic_comparison, holm
from pilot.common.run import dump, first_stage, fit_selection, scale_controls, coefficient_output


def dump_results(path, obj):
    """Compact machine artifact; readable tables live in the Markdown report."""
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':'),
                               default=lambda value: value.tolist())+'\n')


def contrast_groups(core):
    groups = {}; offset = 0
    for block in core.blocks:
        width = core.base_slices[block].stop-core.base_slices[block].start
        groups[block] = np.array([core.common_base+r*core.slope_width+j
            for r in range(core.spec.ncontrast) for j in range(offset, offset+width)])
        offset += width
    return groups


def score_family(core, bread, scores, gradient, objective):
    """Project ONLY common-null nuisance; other added slopes stay restricted.

Each block test shares the same common null. Other contrast scores are not
treated as estimated nuisance. This differs from a conditional block Wald
inside an unrestricted all-block model, so both are labelled explicitly.
"""
    tested = np.arange(core.common_base, core.spec.nbase)
    nuisance = np.setdiff1d(np.arange(core.spec.n_free), tested)
    projection = scaled_solve(bread[np.ix_(nuisance, nuisance)].T,
                              bread[np.ix_(tested, nuisance)].T).T
    efficient = scores[:, tested]-scores[:, nuisance]@projection.T
    meat = efficient.T@efficient*(len(scores)/(len(scores)-1))
    moment = efficient.sum(0)
    tests = {}
    for name, ids in dict(all=tested, **contrast_groups(core)).items():
        jj = ids-core.common_base
        tests[name] = robust_wald(moment[jj], meat[np.ix_(jj, jj)], np.eye(len(jj)))
        tests[name]['qualification'] = 'restricted robust score under common-slopes null; household clusters; WLS/12 Probits/Sigma propagated; market prices fixed'
    adjusted = holm([tests[b]['pvalue'] for b in core.blocks])
    for b, p in zip(core.blocks, adjusted): tests[b]['pvalue_holm_3'] = float(p)
    return {'tests': tests, 'clusters': len(scores),
        'common_null_nuisance_parameters': len(nuisance),
        'null_nuisance_gradient_max_abs': float(np.max(np.abs(gradient[nuisance]))),
        'contrast_score_dimension': len(tested),
        'efficient_score_covariance_condition': float(np.linalg.cond(meat)),
        'null_objective': objective}


def annual_stage(root, stage, baseline):
    cache = root/'path_annual_stage.pkl'; bp = root/'path_annual_base.json'
    if cache.exists():
        with cache.open('rb') as f: return pickle.load(f), json.loads(bp.read_text())
    d = stage['data']; names = stage['control_names']
    raw = pd.DataFrame(stage['Z']*stage['scales']+stage['centers'], columns=names)
    level_names = [n for n in names if not n.startswith('mean_')]
    z = raw[level_names].copy()
    means = raw[[n for n in names if n.startswith('mean_') and n != 'mean_cf_residual']].copy()
    # Two disconnected calendar-frame components: cohort FE span the new-frame
    # indicator. Omit 1392 and 1397 year columns; all annual LEVEL shifts remain
    # representable jointly with the retained cohort controls.
    years = np.sort(np.unique(stage['year']))
    for y in years:
        if y not in (1392, 1397): z[f'year_{y}'] = (stage['year'] == y).astype(float)
    X = np.column_stack([np.ones(d.nobs), d.lnp, z, means])
    s = np.linalg.svd(X/np.linalg.norm(X, axis=0), compute_uv=False)
    rank = int(np.sum(s > s[0]*1e-10))
    if rank != X.shape[1]: raise RuntimeError('Annual common design rank deficient')
    b = pd.read_parquet(root/'priced_panel_106.parquet', columns=[
        'panel_id','year','weight','total_income_real','exp_system_107','exp_11_4'])
    b = b[b.panel_id.isin(stage['panel_ids'])].sort_values(['panel_id','year']).reset_index(drop=True)
    np.testing.assert_array_equal(b.panel_id, stage['panel_ids'])
    np.testing.assert_array_equal(b.year, stage['year'])
    b['exp_analysis_106'] = b.exp_system_107-b.exp_11_4
    np.testing.assert_allclose(np.log(b.exp_analysis_106), d.lnexp)
    for g in range(12): b[f'lnp_{g+1}'] = d.lnp[:,g]
    for g in range(12): b[f'X_{g+1}'] = d.shares[:, g]*b.exp_analysis_106
    cf, rf = first_stage(b, z, means, True)
    zz = pd.concat([z, means], axis=1)
    zz['mean_cf_residual'] = cf.reshape(-1, 3).mean(1).repeat(3)
    tau, k, diag, layout = fit_selection(b, d.lnp, d.lnexp, zz, cf, 'ANNUAL')
    Z, centers, scales = scale_controls(zz, b.weight.to_numpy())
    new = dict(stage, data=DemandData(d.lnp,d.lnexp,d.shares,d.demo,
        norm.cdf(k),norm.pdf(k),d.a0,cf), Z=Z, centers=centers, scales=scales,
        control_names=list(zz.columns), tau=tau, selection_index=k, layout=layout)
    out = copy.deepcopy(baseline)
    out['CRE']['first_stage'] = rf; out['CRE']['participation'] = diag
    out['path_annual_design'] = {'rank': rank, 'columns': X.shape[1],
        'condition': float(s[0]/s[-1]), 'added_year_controls': [n for n in z if n.startswith('year_')],
        'omitted_redundant_year':1397,
        'year_means_not_duplicated':'annual-dummy household means are spanned by entry-cohort dummies in complete consecutive three-wave panels',
        'within_prices_after_household_and_year_effects': annual_within(stage)}
    with cache.open('wb') as f: pickle.dump(new, f)
    dump(bp, out)
    return new, out


def annual_within(stage):
    p = stage['data'].lnp
    pw = p-p.reshape(-1,3,12).mean(1).repeat(3,axis=0)
    t = np.column_stack([(stage['year']==y).astype(float) for y in np.unique(stage['year'])])
    t -= t.reshape(-1,3,t.shape[1]).mean(1).repeat(3,axis=0)
    residual = pw-t@np.linalg.lstsq(t,pw,rcond=1e-11)[0]
    return {f'G{i+1}': {'sd': float(residual[:,i].std()),
        'fraction_remaining': float(residual[:,i].var()/pw[:,i].var())} for i in range(12)}


def warm_translations(old, old_stage, new_stage, core):
    theta = np.zeros(core.spec.n_free)
    theta[:core.common_base] = old.theta[:core.common_base]
    old_eta = old.theta[core.common_base:].reshape(-1,11)/old_stage['scales'][:,None]
    new_eta = np.zeros((core.spec.nshift,11)); alpha = theta[core.base_slices['alpha']].copy()
    for i,name in enumerate(old_stage['control_names']):
        j = new_stage['control_names'].index(name)
        new_eta[j] = old_eta[i]*new_stage['scales'][j]
        alpha += (new_stage['centers'][j]-old_stage['centers'][i])*old_eta[i]
    theta[core.base_slices['alpha']] = alpha
    theta[core.spec.nbase:] = new_eta.ravel()
    return theta


def cached_fit(root, name, core, init, sigma):
    path = root/f'path_{name}_point.pkl'
    key = {'version':'cohort-annual-SYCF-v1','names':core.path_names,
           'blocks':core.blocks,'regimes': np.unique(core.regimes).tolist(), 'n_free':core.spec.n_free}
    if path.exists():
        with path.open('rb') as f: fit=pickle.load(f)
        assert fit.path_key == key
        return fit
    start=time.time()
    def log(msg):
        print(name,msg,flush=True)
        with (root/f'path_{name}_solver.log').open('a') as f: f.write(msg+'\n')
    fit=core.fit(init,sigma,log); fit.path_key=key; fit.path_seconds=time.time()-start
    if not fit.converged or not np.isfinite(fit.theta).all(): raise RuntimeError(f'{name} did not converge')
    with path.open('wb') as f: pickle.dump(fit,f)
    return fit


def model_analysis(root, name, core, fit, stage, baseline, labels):
    design=recover_design(stage,baseline,root); cp=root/f'path_{name}_covariance.npz'
    dp=root/f'path_{name}_diagnostics.json'
    if cp.exists():
        a=np.load(cp); np.testing.assert_array_equal(a['theta'],fit.theta)
        cov=a['covariance']; diagnostics=json.loads(dp.read_text())
    else:
        cov,conditional,diagnostics=stacked_covariance(core,fit,stage,design)
        np.savez_compressed(cp,theta=fit.theta,covariance=cov); dump(dp,diagnostics)
    K=core.spec.n_free; tests={}
    for block,idx in dict(all=np.arange(core.common_base,core.spec.nbase),**contrast_groups(core)).items():
        if len(idx):
            tests[block]=robust_wald(fit.theta,cov[:K,:K],index_R(core,idx))
            tests[block]['qualification']='conditional block Wald inside selected-block alternative; stacked WLS/Probit/Sigma, household clusters, prices fixed'
    ref=ReferenceElasticities(core,fit,stage,design); point=ref.evaluate(ref.point)
    if not np.isfinite(point).all(): raise RuntimeError(f'{name}: nonfinite reference elasticities')
    jp=root/f'path_{name}_elasticity_jacobian.npz'
    if jp.exists():
        a=np.load(jp); np.testing.assert_array_equal(a['point'],ref.point); J=a['jacobian']
    else:
        J=ref.jacobian(); np.savez_compressed(jp,point=ref.point,jacobian=J)
    width=len(point)//len(labels)
    if not np.isfinite(J).all(): raise RuntimeError(f'{name}: nonfinite elasticity Jacobian')
    JV=J@cov
    def se(j,jv): return np.sqrt(np.maximum(np.einsum('ij,ij->i',jv,j),0))
    elas={}; eses={}; coefs=[]; restrictions=[]
    for code,label in enumerate(labels):
        sl=slice(code*width,(code+1)*width)
        elas[label]=unpack_e(point[sl],12); eses[label]=unpack_e(se(J[sl],JV[sl]),12)
        nt,eta=core.unpack(fit.theta,code); c=unpack(nt,core.native)
        coefs.append({'label':label,'alpha_at_center':c.alpha,'beta':c.beta,'gamma':c.gamma,
                      'lambda':c.lam,'delta':c.delta,'cfcoef':c.cfcoef})
        restrictions.append({'label':label,'alpha_sum':c.alpha.sum(),'beta_sum':c.beta.sum(),
            'lambda_sum':c.lam.sum(),'gamma_row_sum_max':np.abs(c.gamma.sum(1)).max(),
            'gamma_symmetry_max':np.abs(c.gamma-c.gamma.T).max(), 'cf_sum':c.cfcoef.sum(),
            'translation_sum_max':np.abs(eta.sum(1)).max()})
    comparisons={}
    # Reference comparisons plus consecutive cohorts/years, with joint covariance.
    pairs=sorted(set([(0,j) for j in range(1,len(labels))]+[(j-1,j) for j in range(1,len(labels))]))
    items=[]
    for a,b in pairs:
        sa=slice(a*width,(a+1)*width); sb=slice(b*width,(b+1)*width)
        diff=unpack_e(point[sb]-point[sa],12); ds=unpack_e(se(J[sb]-J[sa],JV[sb]-JV[sa]),12)
        econ=economic_comparison(diff,ds)
        comparisons[f'{labels[b]} minus {labels[a]}']={'difference':diff,'standard_error':ds,'economic':econ}
        items.extend(econ)
    for item,p in zip(items,holm([v['pvalue_zero'] for v in items])):
        item['pvalue_zero_holm_all_reported_contrasts']=float(p)
    for margin in ('.05','.1','.2'):
        key=str(float(margin))
        for typ,outkey in [('equivalence_tost_pvalue','equivalent_holm_all_contrasts'),
                           ('difference_beyond_margin_pvalue','beyond_margin_holm_all_contrasts')]:
            for item,p in zip(items,holm([v['margin_results'][key][typ] for v in items])):
                item['margin_results'][key][outkey]=bool(p<.05)
    f=core.fitted(fit.theta)
    return {'labels':labels,'blocks_allowed_to_vary':core.blocks if len(labels)>1 else [],
        'counts':{label:int((core.regimes==i).sum()) for i,label in enumerate(labels)},
        'free_parameters':K,'convergence':{'success':bool(fit.converged),'outer_iterations':fit.n_outer,
            'gn_iterations':fit.n_gn,'objective':fit.obj,'log_likelihood':fit.llf,
            'unweighted_share_sse':float(np.sum((core.data.shares-f)**2)),
            'sigma_condition':np.linalg.cond(fit.sigma),
            'elapsed_seconds':getattr(fit,'path_seconds',None)},
        'numerical_settings':fit.pilot_numerical_settings,'inference':diagnostics,'wald_tests':tests,
        'coefficients_by_regime':coefs,'shared_coefficients':coefficient_output(core,fit,
            stage['control_names'],stage['scales'],stage['centers']),
        'free_coefficients':fit.theta,'free_standard_errors':np.sqrt(np.diag(cov[:K,:K])),
        'error_covariance':fit.sigma,'restrictions':restrictions,
        'elasticities_common_point':elas,'elasticity_standard_errors':eses,
        'elasticity_comparisons':comparisons,'economic_margin_note':'0.05/0.1/0.2 illustrative sensitivity margins; not prescribed by Wooldridge; pointwise CI95, Holm across all reported contrasts separately per model',
        'predictions':{'negative_fraction':(f<0).mean(0),'over_one_fraction':(f>1).mean(0),
            'raw_SY_adding_up_rmse':np.sqrt(np.mean((f.sum(1)-1)**2))}}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--only',choices=['cohort','annual','both'],default='both')
    p.add_argument('--output',type=Path,default=Path(__file__).parent/'results.json')
    args=p.parse_args(); root=args.inputs
    with (root/'frame_stage.pkl').open('rb') as f: original=pickle.load(f)
    with (root/'cohort_cre_point.pkl').open('rb') as f: basefit=pickle.load(f)
    baseline=json.loads((root/'frame_base.json').read_text())
    out=json.loads(args.output.read_text()) if args.output.exists() else {
        'sample':baseline['sample'],'input_hashes':baseline['input_hashes'],
        'pyquaidsce_commit':baseline['pyquaidsce_commit'],'a0':baseline['a0'],
        'estimator':'Maintained Mundlak marginal-Probit + CF + SY translated-alpha QUAIDS; not full joint RE likelihood',
        'scope':'cohort and calendar-year hypotheses tested separately; nuisance CF/participation coefficients remain common; not joint separation of cohort vs time slope causes',
        'controls':'same cohort baseline; annual test adds rank-independent annual level shifts to RF, Probit and latent demand; no season/wave/education/curvature'}
    with threadpool_limits(limits=3):
        for kind in (['cohort','annual'] if args.only=='both' else [args.only]):
            if kind=='cohort':
                stage=original; bp=baseline; nullfit=basefit
                values=np.sort(np.unique(stage['cohort'])); regimes=np.searchsorted(values,stage['cohort'])
                labels=[f'{v}–{v+2}' for v in values]
            else:
                stage,bp=annual_stage(root,original,baseline)
                nc=RegimeCore(stage['data'],stage['Z'],np.zeros(len(stage['year']),int))
                nc.path_names=stage['control_names']
                nullfit=cached_fit(root,'annual_null',nc,warm_translations(basefit,original,stage,nc),basefit.sigma)
                values=np.sort(np.unique(stage['year'])); regimes=np.searchsorted(values,stage['year'])
                labels=[str(v) for v in values]
                out['annual_level_design']=bp['path_annual_design']
            out.setdefault(kind,{})['labels']=labels
            out[kind]['null_convergence']={'success':bool(nullfit.converged),
                'outer_iterations':nullfit.n_outer,'gn_iterations':nullfit.n_gn,
                'numerical_settings':nullfit.pilot_numerical_settings}
            out[kind]['stages']={'first_stage':bp['CRE']['first_stage'],
                'probit_coefficients':stage['tau'],
                'probit_regressor_names':list(stage['layout'].ordered_names)+['constant'],
                'participation':bp['CRE']['participation'],
                'translation_names':stage['control_names']}
            core=RegimeCore(stage['data'],stage['Z'],regimes)
            core.path_names=stage['control_names']
            if 'restricted_scores' not in out[kind]:
                null=SimpleNamespace(theta=core.warm_start(nullfit.theta),sigma=nullfit.sigma)
                np.testing.assert_allclose(core.fitted(null.theta),
                    RegimeCore(stage['data'],stage['Z'],np.zeros(len(regimes),int)).fitted(nullfit.theta),atol=2e-12)
                design=recover_design(stage,bp,root)
                score=stacked_covariance(core,null,stage,design,score_test=True)
                out[kind]['restricted_scores']=score; dump_results(args.output,out)
                print('SCORE RESULT',kind,score,flush=True)
            if 'selected_model' in out[kind]: continue
            blocks=tuple(b for b in core.blocks if out[kind]['restricted_scores']['tests'][b]['pvalue_holm_3']<.05)
            out[kind]['selection_note']='screening by three Holm-corrected block scores; alternative CIs are exploratory after selection, not selection-adjusted'
            if not blocks:
                out[kind]['selected_model']=None; dump_results(args.output,out); continue
            selected=RegimeCore(stage['data'],stage['Z'],regimes,blocks)
            selected.path_names=stage['control_names']
            fit=cached_fit(root,kind,selected,selected.warm_start(nullfit.theta),nullfit.sigma)
            out[kind]['selected_model']=model_analysis(root,kind,selected,fit,stage,bp,labels)
            if kind=='annual':
                nc=RegimeCore(stage['data'],stage['Z'],np.zeros(len(regimes),int))
                out[kind]['common_slopes_with_year_levels']=model_analysis(root,'annual_null',nc,nullfit,stage,bp,['common'])
            dump_results(args.output,out)
            print('COMPLETE',kind,flush=True)


if __name__=='__main__': main()
