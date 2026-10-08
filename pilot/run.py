"""Point-estimation pilot. Usage: python pilot/run.py --inputs PATH.

All caches and fit objects are private intermediate files. Results contain only
aggregates/coefficients. Neither raw nor frozen clean data are modified.
"""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
    os.environ[key]='1'
import argparse,json,time,pickle,platform
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm,chi2
from pyquaidsce.probit import probit
from pyquaidsce.probit import _lambda_ratio
from pyquaidsce.params import unpack
from pyquaidsce.elasticities import elasticities,Means
from pyquaidsce.selection import FirstStageLayout
from panel_core import PanelCore
from prices import construct,digest

PN=[f'lnp_{g}' for g in range(1,13)]

def dump(path,obj):
    def convert(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        raise TypeError(str(type(x)))
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=convert)+'\n')

def dummies(b,cohort_instead_of_wave=False):
    z=pd.DataFrame(index=b.index)
    z['household_size']=b.household_size.astype(float)
    z['head_age']=b.head_age.astype(float)
    z['female']=(b.head_sex=='Female').astype(float)
    z['urban']=(b.urban_rural=='Urban').astype(float)
    for r in range(1,6):z[f'region_{r}']=(b.region==r).astype(float)
    for value in ['Widowed','Divorced','Bachelor']:
        z[f'marital_{value}']=(b.head_marital_status==value).astype(float)
    for y in range(1393,1404):z[f'year_{y}']=(b.year==y).astype(float)
    for s in [2,3,4]:z[f'season_{s}']=(b.season_number==s).astype(float)
    if cohort_instead_of_wave:
        cohorts=sorted(b.cohort.unique())
        for c in cohorts[1:]:z[f'cohort_{int(c)}']=(b.cohort==c).astype(float)
    else:
        for w in [2,3]:z[f'wave_{w}']=(b.wave==w).astype(float)
    return z

def variation(b,cols):
    out={}
    for name in cols:
        v=b[name].to_numpy(float);mean=b.groupby('panel_id')[name].transform('mean').to_numpy()
        valid=np.isfinite(v)&np.isfinite(mean)
        overall=np.std(v[valid]);within=np.std(v[valid]-mean[valid])
        between=np.std(b.groupby('panel_id')[name].mean().dropna().to_numpy())
        out[name]={'overall_sd':overall,'between_sd':between,'within_sd':within,
                   'within_variance_fraction':within**2/overall**2}
    return out

def conditional_within_prices(b,z):
    """Price support after removing household means and common time effects."""
    time_names=[n for n in z if n.startswith(('year_','season_','wave_'))]
    t=z[time_names]-z[time_names].groupby(b.panel_id).transform('mean')
    lp=b[PN]-b[PN].groupby(b.panel_id).transform('mean')
    beta,_,rank,_=np.linalg.lstsq(t.to_numpy(),lp.to_numpy(),rcond=1e-11)
    residual=lp.to_numpy()-t.to_numpy()@beta
    s=np.linalg.svd(residual/np.linalg.norm(residual,axis=0),compute_uv=False)
    return {'time_design_columns':len(time_names),'time_design_within_rank':int(rank),
      'residual_price_rank':int(np.sum(s>s[0]*1e-10)),
      'residual_price_condition':float(s[0]/s[-1]),
      'prices':{name:{'within_sd_after_time_effects':float(np.std(residual[:,j])),
        'fraction_of_within_variance_remaining':float(np.var(residual[:,j])/np.var(lp.to_numpy()[:,j]))}
        for j,name in enumerate(PN)}}

def cluster_cov(X,res,weight,groups):
    A=X.T@(weight[:,None]*X)
    score=X*(weight*res)[:,None]
    scores=pd.DataFrame(score).groupby(groups,sort=False).sum().to_numpy()
    Ai=np.linalg.inv(A)
    return Ai@(scores.T@scores)@Ai

def wald(b,V,idx):
    bb=b[idx];vv=V[np.ix_(idx,idx)]
    rank=np.linalg.matrix_rank(vv,tol=max(np.linalg.norm(vv,2),1e-300)*1e-9)
    stat=float(bb@np.linalg.pinv(vv,rcond=1e-9)@bb)
    return {'statistic':stat,'df':int(rank),'pvalue':float(chi2.sf(stat,rank)),
      'qualification':'conditional panel-cluster sandwich; generated stages treated fixed; provisional'}

def first_stage(b,z,means,cre):
    lp=b[PN].to_numpy(float);y=np.log(b.exp_analysis_106.to_numpy())
    income=np.log(b.total_income_real.to_numpy());weights=b.weight.to_numpy(copy=True);weights/=weights.mean()
    center=float(np.average(income,weights=weights));inc=income-center
    iv=np.column_stack([inc,inc**2])
    cc=np.column_stack([lp,z.to_numpy(),means.to_numpy()]) if cre else np.column_stack([lp,z.to_numpy()])
    names=PN+list(z.columns)+(list(means.columns) if cre else [])
    X=np.column_stack([np.ones(len(b)),cc,iv]);names=['constant']+names+['ln_income_centered','ln_income_centered_squared']
    norms=np.std(X,axis=0);norms[0]=1;Xs=X/norms
    sw=np.sqrt(weights);coef,_,rank,_=np.linalg.lstsq(Xs*sw[:,None],y*sw,rcond=1e-11)
    if rank!=X.shape[1]:raise RuntimeError('Reduced form rank deficiency')
    coef/=norms;res=y-X@coef
    restricted=X[:,:-2]
    rb=np.linalg.lstsq(restricted*sw[:,None],y*sw,rcond=1e-11)[0]
    rss=float(np.sum(weights*res**2));rss0=float(np.sum(weights*(y-restricted@rb)**2))
    cov=cluster_cov(X,res,weights,b.panel_id.to_numpy())
    diag={'rank':int(rank),'columns':len(names),'r_squared':1-rss/np.sum(weights*(y-np.average(y,weights=weights))**2),
          'excluded_partial_r_squared':1-rss/rss0,'excluded_classical_f':((rss0-rss)/2)/(rss/(len(y)-len(names))),
          'excluded_panel_cluster_wald':wald(coef,cov,[len(names)-2,len(names)-1]),
          'income_center':center,'coefficients':dict(zip(names,coef))}
    return res,diag

def scale_controls(z,weights,prior=None):
    center=np.average(z.to_numpy(),axis=0,weights=weights)
    scale=np.sqrt(np.average((z.to_numpy()-center)**2,axis=0,weights=weights))
    if prior is not None:
        nc=len(prior[0]);center[:nc]=prior[0];scale[:nc]=prior[1]
    if np.any(scale<1e-10):raise RuntimeError('Constant shifter would duplicate alpha')
    return (z.to_numpy()-center)/scale,center,scale

def fit_selection(b,lp,lnx,z,cf,tag):
    X=np.column_stack([lp,lnx,z.to_numpy(),cf]);names=PN+['ln_expenditure']+list(z.columns)+['cf_residual']
    # Standardize for stable Probit Newton solves; transform coefficients back.
    center=X.mean(0);scale=X.std(0)
    if np.any(scale<1e-10):raise RuntimeError('Selection constant or collinear variable')
    Xs=(X-center)/scale
    tau=[];indices=[];diagnostics=[]
    for g in range(1,13):
        y=(b[f'X_{g}'].to_numpy()>0).astype(float)
        r=probit(y,Xs,tol=1e-10,max_iter=100)
        if r.dropped:raise RuntimeError(f'Selection design dropped columns {r.dropped}')
        bt=np.r_[r.b[:-1]/scale,r.b[-1]-np.sum(center*r.b[:-1]/scale)]
        k=X@bt[:-1]+bt[-1]
        diagnostics.append({'group':g,'converged':bool(r.converged),'iterations':r.n_iter,
         'log_likelihood':r.llf,'participation_rate':y.mean(),
         'Phi_min':norm.cdf(k).min(),'Phi_max':norm.cdf(k).max(),
         'cf_coefficient':bt[-2],'cf_naive_z':r.b[-2]/np.sqrt(r.V[-2,-2])})
        diagnostics[-1].update(selection_tests(y,X,bt,names))
        if not r.converged:raise RuntimeError(f'{tag} participation {g} did not converge')
        tau.append(bt);indices.append(k)
        print(f'{tag} Probit {g}: {r.n_iter} iterations',flush=True)
    layout=FirstStageLayout(tuple(names),tuple(PN),{name:i for i,name in enumerate(PN)},12,
         {name:13+i for i,name in enumerate(z.columns)},len(names)-1,len(names))
    return np.array(tau),np.array(indices).T,diagnostics,layout

def selection_tests(y,X,bt,names):
    """Conditional panel-cluster inference on a balanced, panel-sorted sample."""
    center=X.mean(0);scale=X.std(0)
    xx=np.column_stack([(X-center)/scale,np.ones(len(X))])
    bs=np.r_[bt[:-1]*scale,bt[-1]+center@bt[:-1]]
    q=2*y-1;v=q*(xx@bs);lam=_lambda_ratio(v)
    weight=lam*(lam+v)
    bread=np.linalg.inv(xx.T@(weight[:,None]*xx))
    score=(xx*(q*lam)[:,None]).reshape(-1,3,xx.shape[1]).sum(1)
    cov=bread@(score.T@score)@bread
    out={'cf_panel_cluster_test':wald(bs,cov,[names.index('cf_residual')])}
    midx=[i for i,n in enumerate(names) if n.startswith('mean_') and n!='mean_cf_residual']
    if midx:out['mundlak_panel_cluster_joint_test']=wald(bs,cov,midx)
    return out

def coefficient_output(core,fit,names,scales,centers):
    nt,eta=core.unpack(fit.theta);c=unpack(nt,core.native)
    return {'alpha_at_center':c.alpha,'beta':c.beta,'gamma':c.gamma,'lambda':c.lam,
      'delta':c.delta,'cf_current':c.cfcoef,'translation_names':names,
      'translations_standardized':eta,'translations_original_units':eta/scales[:,None],
      'translation_centers':centers,'translation_scales':scales}

def inference(core,fit,b,mundlak_start):
    P=np.linalg.inv(np.linalg.cholesky(fit.sigma))
    K=core.spec.n_free
    G,g,obj=core.normal(fit.theta,core.data,core.spec,None,P,3000)
    scores=[]
    for start in range(0,len(b),3000):
        sl=slice(start,min(start+3000,len(b)))
        u=(core.data.shares[sl]-core.fitted(fit.theta,sl))@P.T
        J,H=core.derivative_blocks(fit.theta,sl);J=np.matmul(P,J);H=np.matmul(P,H)
        base=np.einsum('tik,ti->tk',J,u,optimize=True)
        hscore=np.einsum('tik,ti->tk',H,u,optimize=True)
        shift=(core.Z[sl,:,None]*hscore[:,None,:]).reshape(len(u),-1)
        s=np.column_stack([base,shift]).reshape(-1,3,K).sum(1)
        scores.append(s)
    S=np.vstack(scores);Gi=np.linalg.inv(G)
    cov=Gi@(S.T@S)@Gi
    sd=np.sqrt(np.diag(G));scaled=G/sd[:,None]/sd[None,:]
    ev=np.linalg.eigvalsh(scaled)
    direction=solver_direction(G,g)
    diag={'gradient_scaled_gn_ratio':abs(float(direction@g))/max(obj,1e-300),
       'max_scaled_score':float(np.max(np.abs(g)/sd)),
       'information_scaled_min_eigenvalue':ev[0],'information_scaled_condition':ev[-1]/ev[0],
       'conditional_cf_current_joint_test':wald(fit.theta,cov,list(range(core.base_slices['cfcoef'].start,core.base_slices['cfcoef'].stop)))}
    if mundlak_start is not None:
        idx=list(range(core.spec.nbase+mundlak_start*11,core.spec.n_free))
        diag['mundlak_and_mean_cf_joint_test']=wald(fit.theta,cov,idx)
        # Pure Mundlak (exogenous means), separate from mean-CF control.
        diag['mundlak_joint_test']=wald(fit.theta,cov,idx[:-11])
    return diag

def solver_direction(G,g):
    from pyquaidsce.nlsur import _solve_scaled
    return _solve_scaled(G,g)

def summarize_model(core,fit,b,tau,k,layout,names,scales,centers,mundlak_start):
    nt,eta=core.unpack(fit.theta);c=unpack(nt,core.native)
    w=b[[f'w_{g}' for g in range(1,13)]].to_numpy()
    # Exactly the native at-means elasticity convention; controls are centered
    # at its unweighted representative point. Translation adds to alpha in BOTH
    # the index and the share equation. Means and CF remain fixed in derivatives.
    refshift=core.Z.mean(0)@eta
    c.alpha=c.alpha+refshift
    means=Means(w.mean(0),core.data.lnp.mean(0),float(core.data.lnexp.mean()),np.zeros(1),
                  core.data.cdf.mean(0),core.data.pdf.mean(0),k.mean(0),float(core.data.control_function.mean()))
    elas=elasticities(c,core.native,means,core.data.a0,tau=tau.ravel(),np_prob=layout.width,layout=layout)
    f=core.fitted(fit.theta)
    pred={'mean_fitted_shares':f.mean(0),'negative_fitted_fraction':(f<0).mean(0),
      'over_one_fitted_fraction':(f>1).mean(0),'fitted_adding_up_rmse':np.sqrt(np.mean((f.sum(1)-1)**2)),
      'fitted_share_sum_quantiles':np.quantile(f.sum(1),[0,.01,.5,.99,1])}
    restriction={'alpha_sum':float(unpack(nt,core.native).alpha.sum()),'beta_sum':float(c.beta.sum()),
      'lambda_sum':float(c.lam.sum()),'cf_sum':float(c.cfcoef.sum()),
      'gamma_row_sum_max_abs':np.abs(c.gamma.sum(1)).max(),
      'gamma_symmetry_max_abs':np.abs(c.gamma-c.gamma.T).max(),
      'translation_sum_max_abs':np.abs(eta.sum(1)).max()}
    return {'convergence':{'success':bool(fit.converged),'outer_iterations':fit.n_outer,
       'gn_iterations':fit.n_gn,'objective':fit.obj,'log_likelihood':fit.llf,
       'unweighted_share_sse':float(np.sum((w-f)**2)),
       'sigma_condition':float(np.linalg.cond(fit.sigma)),
       'parameter_finite':bool(np.isfinite(fit.theta).all())},
      'error_covariance':fit.sigma,
      'restrictions':restriction,'predictions':pred,
      'coefficients':coefficient_output(core,fit,names,scales,centers),
      'elasticities':{'expenditure':elas.income,'marshallian':elas.uncompensated,
          'hicksian_slutsky_convention':elas.compensated,'latent_expenditure':elas.income_latent,
          'latent_marshallian':elas.uncompensated_latent,'censoring_adjusted_mean_share':elas.we},
      'inference_diagnostics':inference(core,fit,b,mundlak_start)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'results.json')
    parser.add_argument('--models',nargs='+',choices=['Pooled','CRE'],default=['Pooled','CRE'])
    parser.add_argument('--algorithm',choices=['gn','lm'],default='gn')
    parser.add_argument('--gn-tol',type=float,default=1e-8)
    parser.add_argument('--no-year-season',action='store_true')
    parser.add_argument('--cohort-instead-of-wave',action='store_true')
    parser.add_argument('--cache-prefix',default='')
    parser.add_argument('--warm-start',type=Path)
    args=parser.parse_args();p=args.inputs;t0=time.time()
    hashes={name:digest(p/name) for name in ['all_clean_1392_1403.csv.gz','panelB_clean_1392_1403.csv.zip','final_commodity_mapping_107.xlsx']}
    assert hashes['all_clean_1392_1403.csv.gz']=='d077806039d2f891f2a26de2cfca8544acf1c322c593984f46b795152b2ccf69'
    assert hashes['panelB_clean_1392_1403.csv.zip']=='165dfd27c176e2c92e50a58f8762fae9635c3ffb59a61c7259f48f31dbd18ed0'
    assert hashes['final_commodity_mapping_107.xlsx']=='59d9872c0ba15ac5971c15775d537e1a910e05350625dc2fc48cff469cd918ef'
    m=pd.read_excel(p/'final_commodity_mapping_107.xlsx')
    assert len(m)==107 and (m.p_var=='p_11_4').sum()==1
    assert m.loc[m.p_var=='p_11_4','commodity_code'].item()==12211
    m=m[m.p_var!='p_11_4'].reset_index(drop=True)
    if not (p/'priced_panel_106.parquet').exists():
        a=pd.read_csv(p/'all_clean_1392_1403.csv.gz',dtype={'address_raw':str,'head_education':str})
        b=pd.read_csv(p/'panelB_clean_1392_1403.csv.zip',dtype={'address_raw':str,'head_education':str})
        b,pa=construct(a,b,m);b.to_parquet(p/'priced_panel_106.parquet',index=False);dump(p/'price_audit_106.json',pa)
        del a
    b=pd.read_parquet(p/'priced_panel_106.parquet').sort_values(['panel_id','year']).reset_index(drop=True)
    assert b.groupby('panel_id').size().eq(3).all()
    assert b.groupby('panel_id').year.diff().dropna().eq(1).all()
    b['wave']=b.groupby('panel_id').cumcount()+1
    b['cohort']=b.groupby('panel_id').year.transform('min')
    b['exp_analysis_106']=b.exp_system_107-b.exp_11_4
    for g in range(1,13):
        b[f'X_{g}']=b[m.loc[m.group_id==g,'exp_var']].sum(1,min_count=len(m[m.group_id==g]))
        b[f'w_{g}']=b[f'X_{g}']/b.exp_analysis_106
    assert np.allclose(b.loc[b.food_matched==1,[f'X_{g}' for g in range(1,13)]].sum(1),
                      b.loc[b.food_matched==1,'exp_analysis_106'])
    switching={}
    for g in range(1,13):
        xt=b[f'X_{g}'].to_numpy().reshape(-1,3)
        # A clean-file zero for unmatched food is not an observed nonpurchase.
        valid=np.isfinite(xt).all(1)&b.food_matched.to_numpy().reshape(-1,3).astype(bool).all(1)
        positive=xt>0
        switching[str(g)]={'all_panels':46347,'unknown_food_waves':int((~valid).sum()),
          'always_zero':int((valid&~positive.any(1)).sum()),
          'always_positive':int((valid&positive.all(1)).sum()),
          'switchers':int((valid&positive.any(1)&~positive.all(1)).sum())}
    good=np.ones(len(b),bool);flow=[]
    for label,ok in [('food_match',b.food_matched.eq(1).to_numpy()),
       ('positive_system_expenditure',np.isfinite(b.exp_analysis_106)&(b.exp_analysis_106>0)),
       ('positive_income',np.isfinite(b.total_income_real)&(b.total_income_real>0)),
       ('required_demographics',b.head_sex.isin(['Male','Female'])&b.head_age.notna()&b.household_size.gt(0)),
       ('finite_market_group_prices',np.isfinite(b[PN]).all(axis=1))]:
        drop=good&~np.asarray(ok);good&=np.asarray(ok)
        flow.append({'criterion':label,'new_excluded_rows':int(drop.sum()),'remaining_rows':int(good.sum())})
    balanced=pd.Series(good).groupby(b.panel_id).transform('all').to_numpy()
    flow.append({'criterion':'complete_three_wave_estimation_panels','new_excluded_rows':int((good&~balanced).sum()),
                 'remaining_rows':int(balanced.sum())})
    b=b[balanced].reset_index(drop=True)
    assert b.groupby('panel_id').size().eq(3).all()
    b['ln_exp']=np.log(b.exp_analysis_106)
    sample={'source_rows':139041,'source_panels':46347,'flow':flow,'estimation_rows':len(b),
      'estimation_panels':b.panel_id.nunique(),'year_counts':b.year.value_counts().sort_index().to_dict(),
      'cohort_counts':b[b.wave==1].year.value_counts().sort_index().to_dict(),
      'sample_hash':__import__('hashlib').sha256(('\n'.join(b.panel_id.astype(str)+':'+b.year.astype(str))).encode()).hexdigest()}
    print('Sample',sample,flush=True)
    z=dummies(b,args.cohort_instead_of_wave)
    if args.no_year_season:
        z=z.drop(columns=[n for n in z if n.startswith(('year_','season_'))])
    xx=pd.concat([b[PN],z[['household_size','head_age','female','marital_Widowed','marital_Divorced','marital_Bachelor']]],axis=1)
    means=xx.groupby(b.panel_id).transform('mean').add_prefix('mean_')
    income=np.log(b.total_income_real);income-=np.average(income,weights=b.weight)
    means['mean_ln_income_centered']=income.groupby(b.panel_id).transform('mean')
    means['mean_ln_income_centered_squared']=(income**2).groupby(b.panel_id).transform('mean')
    Xrank=np.column_stack([np.ones(len(b)),b[PN],z,means])
    s=np.linalg.svd(Xrank/np.linalg.norm(Xrank,axis=0),compute_uv=False)
    rank={'columns':Xrank.shape[1],'rank':int(np.sum(s>s[0]*1e-10)),'condition':float(s[0]/s[-1]),
          'Mundlak_variables':list(means.columns),'level_controls':list(z.columns)}
    if rank['rank']!=rank['columns']:raise RuntimeError(f'Mundlak rank deficiency {rank}')
    out={'input_hashes':hashes,'sample':sample,'prices':json.loads((p/'price_audit_106.json').read_text()),
         'estimator_label':'matched pooled versus Mundlak-augmented marginal-Probit/SY translated QUAIDS; not joint RE likelihood',
         'analysis_basket':{'source_items':107,'analysis_items':106,'groups':12,
           'excluded_code':12211,'excluded_item':'soda','authorization':'explicit user instruction',
           'expenditure':'exp_system_107 - exp_11_4','education_used':False,'curvature_imposed':False},
         'variation':variation(b,PN+['ln_exp']),'switching_source_panel':switching,'design':rank,
         'conditional_within_prices':conditional_within_prices(b,z),
         'python':platform.python_version(),'pyquaidsce_commit':'636609f17e732a57b140cbbad5d2bf4042bc396a'}
    out['source_manifest']={'project_base_commit':'8d04114',
      'prior_bundle_SHA256':'220686116e3f5a23984e2af18f64151faf9f1950540010d46c5db7b3639364e7',
      'panel_csv_uncompressed_SHA256':'2f4c3683643304e6751d3d4eeecf78daebc23e8799574f46b4a52aedc1236e20'}
    out['specification']={'year_FE':not args.no_year_season,'season_FE':not args.no_year_season,'wave_FE':not args.cohort_instead_of_wave,
      'cohort_FE':args.cohort_instead_of_wave,
      'cohort_definition':'first observed year of the original complete three-year Panel B trajectory',
      'cohort_reference':int(b.cohort.min()) if args.cohort_instead_of_wave else None}
    out['initialization']={'warm_start_result':str(args.warm_start) if args.warm_start else None}
    lp=b[PN].to_numpy();lnx=b.ln_exp.to_numpy();w=b[[f'w_{g}' for g in range(1,13)]].to_numpy()
    weights=b.weight.to_numpy();a0=float(np.average(lnx,weights=weights))-2.0
    previous=None;norms=None
    for tag in args.models:
        model_start=time.time()
        cre=tag=='CRE'
        cf,rf=first_stage(b,z,means,cre)
        zz=pd.concat([z,means],axis=1) if cre else z.copy()
        if cre:zz['mean_cf_residual']=pd.Series(cf).groupby(b.panel_id).transform('mean')
        tau,k,pdiag,layout=fit_selection(b,lp,lnx,zz,cf,tag)
        Z,center,scale=scale_controls(zz,weights,norms)
        if not cre:norms=(center,scale)
        core=PanelCore(lp,lnx,w,norm.cdf(k),norm.pdf(k),cf,Z,a0)
        init=None;sigma0=None
        if args.warm_start:
            old=json.loads(args.warm_start.read_text())[tag]
            co=old['coefficients'];oldnames=co['translation_names']
            et=np.zeros((len(zz.columns),12));oldcenter=np.array(co['translation_centers'])
            alpha=np.array(co['alpha_at_center']).copy()
            for j,n in enumerate(zz.columns):
                if n in oldnames:
                    i=oldnames.index(n);et[j]=np.array(co['translations_original_units'])[i]
                    alpha+=(center[j]-oldcenter[i])*et[j]
            # New cohort coefficients start at zero; omitted wave effects are
            # held at their previous centering point only for initialization.
            init=np.zeros(core.spec.n_free)
            for name,key in [('alpha','alpha_at_center'),('beta','beta'),('lambda','lambda'),('delta','delta'),('cfcoef','cf_current')]:
                val=alpha if name=='alpha' else np.array(co[key])
                sl=core.base_slices[name];init[sl]=val[:sl.stop-sl.start]
            # Native gamma packs the upper triangle (including diagonal) of
            # the first n-1 goods; final row/column follows homogeneity.
            init[core.base_slices['gamma']]=np.array(co['gamma'])[:11,:11][np.triu_indices(11)]
            init[core.spec.nbase:]=(et[:,:-1]*scale[:,None]).ravel()
            sigma0=np.array(old['error_covariance'])
        if previous is not None and len(previous.theta)<=core.spec.n_free:
            init=np.zeros(core.spec.n_free);init[:len(previous.theta)]=previous.theta;sigma0=previous.sigma
        logfile=p/f'{args.cache_prefix}{tag.lower()}_solver.log'
        def logger(msg):
            with open(logfile,'a') as f:f.write(msg+'\n')
            print(tag,msg,flush=True)
        cache=p/f'{args.cache_prefix}{tag.lower()}_point.pkl'
        cache_key={'input_hashes':hashes,'sample_hash':sample['sample_hash'],
          'version':'106-translated-SY-v1','translation_names':list(zz.columns),'a0':a0}
        if cache.exists():
            with open(cache,'rb') as f:fit=pickle.load(f)
            if getattr(fit,'pilot_cache_key',None)!=cache_key:
                raise RuntimeError(f'Fit cache does not match inputs/design: {cache}; remove it to refit')
        else:
            fit=core.fit(init,sigma0,logger,algorithm=args.algorithm,gn_tol=args.gn_tol)
            fit.pilot_cache_key=cache_key
            with open(cache,'wb') as f:pickle.dump(fit,f)
        result=summarize_model(core,fit,b,tau,k,layout,list(zz.columns),scale,center,len(z.columns) if cre else None)
        result['first_stage']=rf;result['participation']=pdiag;result['probit_coefficients']=tau
        result['numerical_settings']=fit.pilot_numerical_settings
        result['stage_wall_seconds']=time.time()-model_start
        result['probit_regressor_names']=list(layout.ordered_names)+['constant']
        out[tag]=result;dump(args.output,out)
        previous=fit
    out['a0']=a0;out['elapsed_seconds']=time.time()-t0
    out['runtime']={'CRE_total_stage_wall_seconds':out.get('CRE',{}).get('stage_wall_seconds'),
                   'BLAS_threads_per_process':int(os.environ.get('PILOT_BLAS_THREADS','1')),'machine_CPU_cores':os.cpu_count()}
    if all(t in out for t in ['Pooled','CRE']):
        out['common_convergence_audit']={'gradient_threshold':1e-8,'stricter_post_fit_threshold':1e-12,
          'both_pass':all(out[t]['inference_diagnostics']['gradient_scaled_gn_ratio']<1e-12 for t in ['Pooled','CRE'])}
    dump(args.output,out)

if __name__=='__main__':main()
