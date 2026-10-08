"""Small, reproducible temporal/cohort Wald stability pilot; no bootstrap.

Run the common-stage restricted fit first (see report command), then this file.
Both alternatives use identical observations, prices, CF and Probit stages.
Covariance is conditional, clustered by the complete three-wave household.
"""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
    os.environ[key]='1'
import argparse,json,pickle,time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import chi2
from pyquaidsce.params import unpack
from pyquaidsce.elasticities import elasticities,Means
from run import dump,inference,coefficient_output
from regime_core import RegimeCore


def robust_wald(theta,cov,R):
    b=R@theta;V=R@cov@R.T
    scale=np.sqrt(np.maximum(np.diag(V),1e-300))
    v=V/scale[:,None]/scale[None,:];bb=b/scale
    rank=int(np.linalg.matrix_rank(v,tol=np.linalg.norm(v,2)*1e-9))
    stat=float(bb@np.linalg.pinv(v,rcond=1e-9)@bb)
    return {'statistic':stat,'df':rank,'nominal_restrictions':len(b),
            'pvalue':float(chi2.sf(stat,rank)),
            'qualification':'conditional panel-cluster Wald; generated stages fixed; not final inference'}


def index_R(core,indices):
    return np.eye(core.spec.n_free)[indices]


def common_point_elasticities(core,fit,stage,regime):
    nt,eta=core.unpack(fit.theta,regime);c=unpack(nt,core.native)
    c.alpha=c.alpha+core.Z.mean(0)@eta
    d=core.data;k=stage['selection_index']
    means=Means(d.shares.mean(0),d.lnp.mean(0),float(d.lnexp.mean()),np.zeros(1),
      d.cdf.mean(0),d.pdf.mean(0),k.mean(0),float(d.control_function.mean()))
    layout=stage['layout']
    e=elasticities(c,core.native,means,d.a0,tau=stage['tau'].ravel(),
                   np_prob=layout.width,layout=layout)
    return {'expenditure':e.income,'marshallian':e.uncompensated,
      'hicksian_slutsky_convention':e.compensated,'latent_expenditure':e.income_latent,
      'latent_marshallian':e.uncompensated_latent}


def fit_alternative(stage,restricted,root,kind):
    if kind=='temporal':
        regimes=np.select([stage['year']<=1396,stage['year']<=1399],[0,1],default=2)
        labels=['1392–1396','1397–1399','1400–1403']
        blocks=('beta','gamma','lambda')
    else:
        cohorts=np.sort(np.unique(stage['cohort']))
        regimes=np.searchsorted(cohorts,stage['cohort'])
        labels=[f'{c}–{c+2}' for c in cohorts]
        blocks=('beta','lambda')
    core=RegimeCore(stage['data'],stage['Z'],regimes,blocks)
    theta0=core.warm_start(restricted.theta)
    np.testing.assert_allclose(core.fitted(theta0),
      # Zero differences must reproduce the restricted model exactly.
      restricted.pilot_stability_fitted,rtol=1e-12,atol=1e-12)
    cache=root/f'stability_{kind}_point.pkl'
    key={'kind':kind,'blocks':blocks,'sample_hash':restricted.pilot_cache_key['sample_hash'],
         'stage_design':stage['control_names'],'version':'slope-stability-v1'}
    start=time.time()
    def logger(msg):
        with open(root/f'stability_{kind}_solver.log','a') as f:f.write(msg+'\n')
        print(kind,msg,flush=True)
    if cache.exists():
        with cache.open('rb') as f:fit=pickle.load(f)
        assert fit.pilot_stability_key==key
    else:
        fit=core.fit(theta0,restricted.sigma,logger)
        fit.pilot_stability_key=key
        with cache.open('wb') as f:pickle.dump(fit,f)
    b=pd.DataFrame({'panel_id':stage['panel_ids']})
    diag,cov=inference(core,fit,b,20,return_cov=True)
    contrast=list(range(core.common_base,core.spec.nbase))
    tests={'all_selected_slopes_equal':robust_wald(fit.theta,cov,index_R(core,contrast))}
    offset=0
    for block in blocks:
        width=core.base_slices[block].stop-core.base_slices[block].start
        idx=[core.common_base+r*core.slope_width+j
             for r in range(core.spec.ncontrast) for j in range(offset,offset+width)]
        tests[f'{block}_equal']=robust_wald(fit.theta,cov,index_R(core,idx))
        offset+=width
    for reg in range(1,len(labels)):
        idx=list(range(core.contrast_slice(reg).start,core.contrast_slice(reg).stop))
        tests[f'{labels[reg]}_vs_{labels[0]}']=robust_wald(fit.theta,cov,index_R(core,idx))
    if kind=='temporal':
        R=index_R(core,list(range(core.contrast_slice(2).start,core.contrast_slice(2).stop)))-index_R(core,list(range(core.contrast_slice(1).start,core.contrast_slice(1).stop)))
        tests['1400–1403_vs_1397–1399']=robust_wald(fit.theta,cov,R)
    coefficients=[];restrictions=[]
    for reg,label in enumerate(labels):
        nt,eta=core.unpack(fit.theta,reg);c=unpack(nt,core.native)
        coefficients.append({'label':label,'beta':c.beta,'gamma':c.gamma,'lambda':c.lam})
        restrictions.append({'label':label,'alpha_sum':c.alpha.sum(),'beta_sum':c.beta.sum(),
          'lambda_sum':c.lam.sum(),'gamma_row_sum_max':np.abs(c.gamma.sum(1)).max(),
          'gamma_symmetry_max':np.abs(c.gamma-c.gamma.T).max(),
          'cf_sum':c.cfcoef.sum(),'translation_sum_max':np.abs(eta.sum(1)).max()})
    f=core.fitted(fit.theta)
    return {'blocks_allowed_to_vary':blocks,'labels':labels,
      'free_parameters':core.spec.n_free,'extra_parameters':len(contrast),
      'counts':{label:int((regimes==reg).sum()) for reg,label in enumerate(labels)},
      'convergence':{'success':bool(fit.converged),'outer_iterations':fit.n_outer,
        'gn_iterations':fit.n_gn,'log_likelihood':fit.llf,'objective':fit.obj,
        'unweighted_share_sse':float(np.sum((core.data.shares-f)**2)),
        'parameter_finite':bool(np.isfinite(fit.theta).all()),
        'sigma_condition':float(np.linalg.cond(fit.sigma))},
      'numerical_settings':fit.pilot_numerical_settings,'wall_seconds':time.time()-start,
      'inference_diagnostics':diag,'tests':tests,'restrictions':restrictions,
      'coefficients_by_regime':coefficients,
      'shared_coefficients':coefficient_output(core,fit,stage['control_names'],stage['scales'],stage['centers']),
      'error_covariance':fit.sigma,
      'elasticities_common_point':{label:common_point_elasticities(core,fit,stage,reg)
                                  for reg,label in enumerate(labels)},
      'predictions':{'fitted_adding_up_rmse':float(np.sqrt(np.mean((f.sum(1)-1)**2))),
                    'negative_fraction':(f<0).mean(0),'over_one_fraction':(f>1).mean(0)}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--only',choices=['temporal','cohort','both'],default='both')
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'results_stability.json')
    args=parser.parse_args();root=args.inputs
    with (root/'stability_stage.pkl').open('rb') as f:stage=pickle.load(f)
    with (root/'stability_null_cre_point.pkl').open('rb') as f:restricted=pickle.load(f)
    null=json.loads((root/'stability_null.json').read_text())
    from panel_core import PanelCore
    d=stage['data'];base=PanelCore(d.lnp,d.lnexp,d.shares,d.cdf,d.pdf,d.control_function,stage['Z'],d.a0)
    restricted.pilot_stability_fitted=base.fitted(restricted.theta)
    result={'sample':null['sample'],'input_hashes':null['input_hashes'],
      'prices':null['prices'],'source_manifest':null['source_manifest'],
      'shared_stage_specification':null['specification'],'design':null['design'],
      'a0':null['a0'],'pyquaidsce_commit':null['pyquaidsce_commit'],
      'restricted_common_slopes':null['CRE'],
      'inference_scope':'conditional panel-cluster Wald; CF and all Probit stages fixed; no bootstrap',
      'design_notes':['1397 is the documented survey frame boundary, not an asserted economic break.',
        '1400 splits the newer frame into two manageable periods; not an estimated break date.',
        'Late-period intercept enters CF, Probit and translated-alpha QUAIDS in BOTH null and alternatives.',
        'A pre/post1397 intercept is collinear with cohort dummies and is not duplicated.',
        'The mean of the late-period indicator is a function of cohort and is not duplicated.',
        'Temporal test permits beta/gamma/lambda to vary; other slopes/shifters/CF/SY loadings are common.',
        'Complementary cohort test varies only beta/lambda; gamma is common, so this is NOT a complete cohort price-slope test.',
        'Tests do not assert causality; entry cohort differences can reflect calendar time, composition and frame.',
        'Null rejection indicates evidence of differences, not the economic size of those differences.']}
    for kind in (['temporal','cohort'] if args.only=='both' else [args.only]):
        result[kind]=fit_alternative(stage,restricted,root,kind)
        dump(args.output,result)
        print(kind,'TESTS',result[kind]['tests'],flush=True)


if __name__=='__main__':main()
