"""Changes to controls and weighted likelihood only; reuse the existing core."""
from pilot.b1_fourteen import run as base  # Single-thread BLAS before NumPy.
import copy
import pickle
import numpy as np
import pandas as pd
from scipy.stats import norm
from pyquaidsce.model import DemandData
from pyquaidsce.selection import FirstStageLayout
from pyquaidsce.probit import _lambda_ratio
from pilot.common.run import scale_controls
from pilot.specification_suite.specification_suite import rank_audit, warm_start
from pilot.b1_fourteen.probit_adapter import finite_probit
from pilot.common.specification_core import SpecificationCore
from scipy.stats import chi2

SOURCE = base.WORK.parent/'marital_participation_sensitivity'
MODELS = [
    ('no_exp_square', 'حذف میانگین مربع لگاریتم مخارج'),
    ('no_exp_means', 'حذف میانگین مخارج و میانگین مربع آن'),
    ('no_mean_cf', 'حذف میانگین CF؛ حفظ CF جاری'),
    ('no_demog_means', 'حذف میانگین جنس و تأهل؛ حفظ میانگین سن و اندازه'),
    ('no_price_means', 'حذف میانگین قیمت‌ها'),
    ('no_year', 'حذف دامی سال'),
    ('no_season', 'حذف دامی فصل'),
    ('no_time', 'حذف دامی سال و فصل'),
    ('flexible_cf', 'CF غنی‌تر: v²، میانگین v² و مربع میانگین v'),
    ('survey_weighted', 'وزن سال جاری در مشارکت و IFGNLS نیز اعمال شود'),
    ('linear_income', 'مرحلهٔ اول با لگاریتم درآمد و میانگین آن؛ بدون مربع‌ها'),
]


def load_baseline(original=False):
    root = base.WORK if original else SOURCE
    return (pickle.load((root/'Panel_1401_stage.pkl').open('rb')),
            pickle.load((root/'Panel_1401_fit.pkl').open('rb')))


def rf_diagnostics(stage):
    """Recalculate relevance using column counts and independent restricted WLS.

    The historical RF fit is untouched. Its old diagnostic used len(DataFrame)
    where the number of columns was intended, so its restricted regression
    accidentally kept the instruments. Cluster covariance below concerns only
    the expenditure RF, not the generated-regressor demand elasticity.
    """
    import copy
    X=stage['Xrf']; names=stage['rf_names']; d=stage['data']; n,k=X.shape
    w=stage['weights']/stage['weights'].mean(); sw=np.sqrt(w)
    coef=np.array([stage['first_stage']['coefficients'][c] for c in names])
    v=d.lnexp-X@coef
    np.testing.assert_allclose(v,d.control_function,atol=3e-10)
    iv=[j for j,c in enumerate(names) if c in ('ln_income_centered','ln_income_centered_squared')]
    X0=np.delete(X,iv,axis=1); s0=X0.std(0); s0[0]=1.
    bc,_,rank,_=np.linalg.lstsq(X0/s0*sw[:,None],d.lnexp*sw,rcond=1e-11)
    assert rank==X0.shape[1] and len(iv)>0
    rss=float(np.sum(w*v*v)); rss0=float(np.sum(w*(d.lnexp-X0/s0@bc)**2))
    scale=X.std(0); scale[0]=1.; xs=X/scale
    bread=np.linalg.inv(xs.T@(w[:,None]*xs))
    scores=xs*(w*v)[:,None]
    assert len(stage['panel_ids'])==n and n%3==0
    panels=np.asarray(stage['panel_ids']).reshape(-1,3)
    assert (panels==panels[:,:1]).all() and len(np.unique(panels[:,0]))==len(panels)
    score_h=scores.reshape(-1,3,k).sum(1); H=len(score_h)
    V=bread@(score_h.T@score_h)@bread * H/(H-1)*(n-1)/(n-k)
    b=coef[iv]*scale[iv]
    wald=float(b@np.linalg.solve(V[np.ix_(iv,iv)],b))
    out=copy.deepcopy(stage['first_stage'])
    out.update(excluded_current_income_names=[names[j] for j in iv],
        excluded_current_income_partial_r_squared=1-rss/rss0,
        excluded_current_income_classical_f=(rss0-rss)/len(iv)/(rss/(n-k)),
        excluded_current_income_panel_cluster_wald=wald,
        excluded_current_income_panel_cluster_df=len(iv),
        excluded_current_income_panel_cluster_p=float(chi2.sf(wald,len(iv))),
        relevance_diagnostic_recalculated=True,
        relevance_diagnostic_note='column counts and restricted WLS checked independently; historical estimates unchanged')
    return out


def weighted_probit(y, X, weights):
    """GLM maximizes the normalized weighted Bernoulli-Probit likelihood.

    Frequency-weight API is used only to obtain the point likelihood optimum;
    its model-based covariance is not used for survey or final inference.
    """
    import statsmodels.api as sm
    XX=np.column_stack([X,np.ones(len(X))])
    w=np.asarray(weights,float); w=w/w.mean()
    result=sm.GLM(y,XX,family=sm.families.Binomial(link=sm.families.links.Probit()),
                  freq_weights=w).fit(maxiter=200,tol=1e-10)
    eta=XX@result.params; z=(2*y-1)*eta; lam=_lambda_ratio(z)
    score=XX.T@(w*(2*y-1)*lam)
    info=XX.T@((w*lam*(lam+z))[:,None]*XX)
    ll=float(np.sum(w*norm.logcdf(z)))
    decrement=float(score@np.linalg.solve(info,score))/(1+abs(ll))
    assert result.converged and 0<=decrement<=1e-10
    assert np.isfinite(result.params).all() and np.linalg.eigvalsh(info).min()>0
    return result.params, {
        'method':'normalized_survey_weighted_probit_GLM',
        'converged':bool(result.converged),'iterations':int(result.fit_history['iteration']),
        'log_likelihood':ll,'relative_newton_decrement':decrement,
        'maximum_absolute_score':float(np.abs(score).max()),
        'covariance_not_used':True,
    }


def build_stage(name, b):
    old,_=load_baseline(); stage=copy.deepcopy(old)
    d=stage['data']; names=old['control_names']
    controls=pd.DataFrame(old['Z']*old['scales']+old['centers'],columns=names)
    drop=[]
    if name=='no_exp_square': drop=['mean_centered_ln_expenditure_squared']
    if name=='no_exp_means': drop=['mean_ln_expenditure','mean_centered_ln_expenditure_squared']
    if name=='no_mean_cf': drop=['mean_cf_residual']
    if name=='no_demog_means':
        drop=[c for c in names if c=='mean_female' or c.startswith('mean_marital_')]
    if name=='no_price_means': drop=[c for c in names if c.startswith('mean_lnp_')]
    if name in ('no_year','no_time'): drop += [c for c in names if c.startswith('year_')]
    if name in ('no_season','no_time'): drop += [c for c in names if c.startswith('season_')]
    controls=controls.drop(columns=drop)
    rfdrop=set(drop)
    if name=='linear_income':
        rfdrop.update(n for n in old['rf_names'] if 'income_centered_squared' in n)
    keep=[i for i,n in enumerate(old['rf_names']) if n not in rfdrop]
    if len(keep)!=len(old['rf_names']):
        X=old['Xrf'][:,keep]; rf_names=[old['rf_names'][i] for i in keep]
        w=old['weights']/old['weights'].mean(); sw=np.sqrt(w)
        scale=X.std(0); scale[0]=1.
        coef,_,rank,_=np.linalg.lstsq(X/scale*sw[:,None],d.lnexp*sw,rcond=1e-11)
        assert rank==X.shape[1]
        coef/=scale; cf=d.lnexp-X@coef
        iv=[i for i,n in enumerate(rf_names) if n in ('ln_income_centered','ln_income_centered_squared')]
        X0=np.delete(X,iv,axis=1)
        c0=np.linalg.lstsq(X0*sw[:,None],d.lnexp*sw,rcond=1e-11)[0]
        rss=np.sum(w*cf**2); rss0=np.sum(w*(d.lnexp-X0@c0)**2)
        stage['Xrf']=X; stage['rf_names']=rf_names
        stage['first_stage']={
            'rank':int(rank),'columns':len(rf_names),
            'coefficients':dict(zip(rf_names,coef)),
            'r_squared':float(1-rss/np.sum(w*(d.lnexp-np.average(d.lnexp,weights=w))**2)),
            'excluded_current_income_partial_r_squared':float(1-rss/rss0),
            'excluded_current_income_classical_f':float((rss0-rss)/len(iv)/(rss/(len(b)-len(rf_names)))),
            'excluded_current_income_names':[rf_names[i] for i in iv],
        }
        d.control_function=cf
    else: cf=d.control_function.copy()
    vbar=base.hhmean(pd.DataFrame({'v':cf}),old['panel_ids']).v.to_numpy()
    if 'mean_cf_residual' in controls: controls['mean_cf_residual']=vbar
    cf_add=['mean_cf_residual'] if 'mean_cf_residual' in controls else []
    if name=='flexible_cf':
        controls['cf_squared']=cf**2
        controls['mean_cf_squared']=base.hhmean(pd.DataFrame({'v2':cf**2}),old['panel_ids']).v2
        controls['square_mean_cf']=vbar**2
        cf_add += ['cf_squared','mean_cf_squared','square_mean_cf']
    controls, redundant=base.identified(controls,np.column_stack([np.ones(len(b)),d.lnp,d.lnexp,cf]))
    sel=pd.DataFrame(d.lnp,columns=base.PN)
    sel['ln_expenditure']=d.lnexp
    sel=pd.concat([sel,controls],axis=1); sel['cf_residual']=cf
    sel, removed=base.identified(sel)
    assert list(sel)[:13]==base.PN+['ln_expenditure']
    rank=rank_audit(np.column_stack([np.ones(len(b)),sel]))
    assert rank['rank']==rank['columns']
    center=sel.mean().to_numpy(); scale=sel.std(ddof=0).to_numpy()
    X=(sel.to_numpy()-center)/scale
    tau=[]; indices=[]; diags=[]
    for i in range(12):
        # Keep the just-authorized bread participation correction in every model.
        keep=np.array([i!=1 or n not in ('marital_Bachelor','mean_marital_Bachelor') for n in sel])
        yy=(d.shares[:,i]>0).astype(float)
        if name=='survey_weighted':
            bt,meta=weighted_probit(yy,X[:,keep],old['weights'])
            ll=meta['log_likelihood']; nit=meta['iterations']
        else:
            fit,meta=finite_probit(yy,X[:,keep],tol=1e-10,max_iter=100)
            assert fit.converged and not fit.dropped
            bt=fit.b; ll=float(fit.llf); nit=int(fit.n_iter)
        raw=np.zeros(sel.shape[1]+1); raw[:-1][keep]=bt[:-1]/scale[keep]
        raw[-1]=bt[-1]-center[keep]@(bt[:-1]/scale[keep])
        tau.append(raw); indices.append(sel.to_numpy()@raw[:-1]+raw[-1])
        diags.append({'group':i+1,'converged':True,'iterations':nit,
                      'log_likelihood':ll,'participation_rate':float(yy.mean()),
                      'excluded_names':[n for n,k in zip(sel,keep) if not k],
                      'estimation_method':meta})
    tau=np.array(tau); index=np.array(indices).T
    Z,centers,scales=scale_controls(controls,old['weights'])
    additive=[list(controls).index(c) for c in cf_add if c in controls]
    for j in additive:
        centers[j]=0.; Z[:,j]=controls.iloc[:,j].to_numpy()/scales[j]
    sn=tuple(sel)
    layout=FirstStageLayout(sn,tuple(base.PN),{p:sn.index(p) for p in base.PN},
                           sn.index('ln_expenditure'),{},sn.index('cf_residual'),len(sn))
    stage.update(
        specification=dict(old['specification'],name=name),
        Z=Z,centers=centers,scales=scales,control_names=list(controls),
        level_names=[c for c in old['level_names'] if c in controls],
        mundlak_names=[c for c in controls if c.startswith('mean_')],
        additive_columns=additive,tau=tau,effective_tau=tau[None,:,:],
        selection_index=index,selection_names=list(sn),layout=layout,
        selection_diagnostics=diags,rank_selection=rank,
        sensitivity_removed=drop,sensitivity_redundant=redundant+removed,
    )
    # Above "keep" has become the Probit mask; use actual RF width to record it.
    stage['rf_reestimated']=stage['Xrf'].shape[1]!=old['Xrf'].shape[1]
    stage['data']=DemandData(d.lnp,d.lnexp,d.shares,np.zeros((len(b),1)),
                            norm.cdf(index),norm.pdf(index),d.a0,cf)
    return stage


def working_core(stage, weighted=False):
    """Exact weighted least squares via sqrt(w) scaling of y and fitted mean.

    The unscaled conditional mean remains Phi*g + delta*phi. The scaled working
    data only supplies sqrt(w)*(y-mu) to the unchanged package solver.
    """
    d=stage['data']
    if weighted:
        sw=np.sqrt(stage['weights']/stage['weights'].mean())
        d=DemandData(d.lnp,d.lnexp,d.shares*sw[:,None],d.demo,
                     d.cdf*sw[:,None],d.pdf*sw[:,None],d.a0,d.control_function)
    return SpecificationCore(d,stage['Z'],stage['additive_columns'])
