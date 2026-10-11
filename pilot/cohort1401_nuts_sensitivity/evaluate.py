"""Conditional input derivatives, distributions and distinct aggregations.

No estimated household mean or CF input is updated by a current expenditure
shock. No elasticities or observations are trimmed, winsorized or clipped.
"""
from pilot.b1_fourteen import run as base
import numpy as np
from scipy.stats import norm
from pyquaidsce.model import DemandData, _inner
from pyquaidsce.params import unpack
from pyquaidsce.elasticities import Means, elasticities
from pilot.common.specification_core import SpecificationCore

NUT=8


def point(stage, theta, rows=None, weights=None, overrides=None, audit=True):
    d=stage['data']; rows=np.ones(d.nobs,bool) if rows is None else np.asarray(rows)
    w=None if weights is None else np.asarray(weights)[rows]
    avg=lambda x: np.average(x[rows],axis=0,weights=w)
    lp=avg(d.lnp); y=float(avg(d.lnexp)); Z=avg(stage['Z'])
    cf=float(avg(d.control_function))
    if overrides:
        lp=np.asarray(overrides.get('log_prices',lp)); y=float(overrides.get('log_expenditure',y))
    raw=dict(zip(stage['control_names'],Z*stage['scales']+stage['centers']))
    raw.update(dict(zip(base.PN,lp))); raw['ln_expenditure']=y; raw['cf_residual']=cf
    X=np.array([raw[n] for n in stage['selection_names']])
    tau=stage['tau']; k=(tau[:,:-1]@X+tau[:,-1])[None,:]
    data=DemandData(lp[None,:],np.array([y]),avg(d.shares)[None,:],np.zeros((1,1)),
                   norm.cdf(k),norm.pdf(k),d.a0,np.array([cf]))
    core=SpecificationCore(data,Z[None,:],stage['additive_columns'])
    mu=core.fitted(theta)[0]
    dx,dp=core.fitted_derivatives(theta,tau,stage['layout'],k)
    valid=mu>0
    ex=np.full(12,np.nan); mar=np.full((12,12),np.nan)
    ex[valid]=1+dx[0,valid]/mu[valid]
    mar[valid]=dp[0,valid]/mu[valid,None]-np.eye(12)[valid]
    nt,dd,translate,additive=core.quantities(theta)
    c=unpack(nt,core.native); inn=_inner(c,dd,core.native)
    f=inn.wstar[0]+translate[0]+additive[0]+cf*c.cfcoef
    pi=data.cdf[0]; pdf=data.pdf[0]; kx=tau[:,stage['layout'].expenditure_position]
    extensive=np.divide(pdf*kx,pi,out=np.full(12,np.nan),where=pi>0)
    conditional=ex-extensive
    frozen=1+np.divide(pi*inn.S[0],mu,out=np.full(12,np.nan),where=valid)
    latent=1+np.divide(inn.S[0],f,out=np.full(12,np.nan),where=f>0)
    derivative_error=0.
    if audit:
        h=1e-5; lp0=data.lnp.copy(); y0=data.lnexp.copy()
        for j in range(13):
            vals=[]
            for sign in (1,-1):
                data.lnp[:]=lp0; data.lnexp[:]=y0
                if j<12: data.lnp[0,j]+=sign*h
                else: data.lnexp[0]+=sign*h
                kk=k+sign*h*tau[:,j][None,:]
                data.cdf[:]=norm.cdf(kk); data.pdf[:]=norm.pdf(kk)
                vals.append(core.fitted(theta)[0])
            analytic=dp[0,:,j] if j<12 else dx[0]
            derivative_error=max(derivative_error,float(np.abs((vals[0]-vals[1])/(2*h)-analytic).max()))
        data.lnp[:]=lp0; data.lnexp[:]=y0
        data.cdf[:]=norm.cdf(k); data.pdf[:]=norm.pdf(k)
        assert derivative_error<1e-6
    # Preserve the previous package convention as a labelled comparison:
    # observed mean shares and averages of CDF/PDF, rather than fitted mu.
    cc=unpack(nt,core.native)
    cc.alpha += translate[0]
    cc.cfcoef=cc.cfcoef*cf+additive[0]
    means=Means(avg(d.shares),lp,y,np.zeros(1),avg(d.cdf),avg(d.pdf),
                avg(stage['selection_index']),1.)
    # Zero observed mean shares make the native ratio undefined. Preserve
    # that fact as null in JSON; do not replace zero shares or trim samples.
    with np.errstate(divide='ignore',invalid='ignore'):
        legacy=elasticities(cc,core.native,means,d.a0,tau=tau.ravel(),
                            np_prob=stage['layout'].width,layout=stage['layout'])
    legacy_nuts=float(legacy.income[NUT]) if means.w[NUT]>0 else np.nan
    return {
        'expenditure':ex,'marshallian':mar,'predicted_shares':mu,
        'nuts_expenditure':float(ex[NUT]),'nuts_own_price':float(mar[NUT,NUT]),
        'nuts_probability':float(pi[NUT]),'nuts_observed_share':float(avg(d.shares)[NUT]),
        'nuts_predicted_share':float(mu[NUT]),
        'nuts_conditional_buyer_expenditure':float(conditional[NUT]),
        'nuts_extensive_contribution':float(extensive[NUT]),
        'nuts_fixed_participation_expenditure':float(frozen[NUT]),
        'nuts_augmented_latent_expenditure':float(latent[NUT]),
        'nuts_augmented_latent_share':float(f[NUT]),
        'nuts_SY_adjustment':float(pdf[NUT]*c.delta[NUT]),
        'nuts_legacy_package_expenditure':legacy_nuts,
        'log_prices':lp,'log_expenditure':y,'max_derivative_absolute_error':derivative_error,
        'predicted_share_sum':float(mu.sum()),'nonpositive_share_groups':np.flatnonzero(~valid).tolist(),
    }


def distribution(a, weights=None):
    a=np.asarray(a); valid=np.isfinite(a); a=a[valid]
    if not len(a): return {'valid_count':0}
    levels=np.array([.01,.05,.1,.25,.5,.75,.9,.95,.99])
    if weights is None:
        q=np.quantile(a,levels); mean=a.mean()
    else:
        w=np.asarray(weights)[valid]; order=np.argsort(a); a=a[order]; w=w[order]
        q=np.interp(levels,(np.cumsum(w)-.5*w)/w.sum(),a); mean=np.average(a,weights=w)
    return {'valid_count':int(len(a)),'mean':float(mean),'min':float(a.min()),
            'max':float(a.max()),'quantiles':dict(zip(map(str,levels),q))}


def micro(stage,theta,b):
    core=base.core_for(stage); d=core.data; n=d.nobs
    mu=np.empty(n); slope=np.empty(n)
    for start in range(0,n,3000):
        sl=slice(start,min(start+3000,n))
        mu[sl]=core.fitted(theta,sl)[:,NUT]
        dx,_=core.fitted_derivatives(theta,stage['tau'],stage['layout'],stage['selection_index'],sl)
        slope[sl]=dx[:,NUT]
    valid=np.isfinite(mu)&np.isfinite(slope)&(mu>0)
    ex=np.full(n,np.nan); ex[valid]=1+slope[valid]/mu[valid]
    xp=np.exp(d.lnexp-d.lnp[:,NUT]); wt=stage['weights']
    def aggregate(mask,weights=None):
        w=np.ones(n) if weights is None else np.asarray(weights)
        Q=np.sum(w[mask]*xp[mask]*mu[mask])
        if Q<=0: return None
        return float(1+np.sum(w[mask]*xp[mask]*slope[mask])/Q)
    allrows=np.ones(n,bool); purchased=b.X_9.to_numpy()>0
    pattern=purchased.reshape(-1,3).sum(1)
    subsets={'observed_buyers':purchased,'observed_nonbuyers':~purchased,
             'always_buy':np.repeat(pattern==3,3),
             'always_zero':np.repeat(pattern==0,3),
             'switchers':np.repeat((pattern>0)&(pattern<3),3)}
    subsets.update({f'year_{y}':b.year.to_numpy()==y for y in sorted(b.year.unique())})
    results={'individual_unweighted':distribution(ex),
             'individual_survey_weighted':distribution(ex,wt),
             'nonpositive_predicted_share_count':int((mu<=0).sum()),
             'positive_share_below_1e_6_count':int(((mu>0)&(mu<1e-6)).sum()),
             'absolute_elasticity_over_10_count':int((np.abs(ex)>10).sum()),
             'negative_elasticity_count':int((ex<0).sum()),
             'elasticity_above_one_fraction_of_valid':float(np.mean(ex[valid]>1)),
             'aggregate_quantity':aggregate(allrows),
             'aggregate_quantity_survey_weighted':aggregate(allrows,wt),
             'aggregate_positive_predictions_only':aggregate(valid),
             'subgroups':{},
             'definition':'current expenditure changes proportionally; household means, CF and weights fixed; all signed fitted entries retained in total-quantity aggregation'}
    for name,mask in subsets.items():
        if mask.any():
            results['subgroups'][name]={'rows':int(mask.sum()),'individual':distribution(ex[mask]),
                'nonpositive_predicted_share_count':int(((mu<=0)&mask).sum()),
                'negative_elasticity_count':int(((ex<0)&mask).sum()),
                'aggregate_quantity':aggregate(mask),
                'at_means':point(stage,theta,mask,audit=False)}
    quartile=np.asarray(__import__('pandas').qcut(d.lnexp,4,labels=False))
    results['observed_expenditure_quartile_diagnostics']={}
    for q in range(4):
        mask=quartile==q
        results['observed_expenditure_quartile_diagnostics'][str(q+1)]={
            'rows':int(mask.sum()),'individual':distribution(ex[mask]),
            'nonpositive_predicted_share_count':int(((mu<=0)&mask).sum()),
            'negative_elasticity_count':int(((ex<0)&mask).sum()),
            'purchase_rate':float(purchased[mask].mean())}
    # Independently differentiate the actual aggregate quantity function.
    h=1e-5; oldy=d.lnexp.copy(); oldcdf=d.cdf.copy(); oldpdf=d.pdf.copy()
    k=stage['selection_index']; kx=stage['tau'][:,stage['layout'].expenditure_position]
    quantities=[]
    try:
        for sign in (1,-1):
            d.lnexp[:]=oldy+sign*h
            d.cdf[:]=norm.cdf(k+sign*h*kx); d.pdf[:]=norm.pdf(k+sign*h*kx)
            values=core.fitted(theta)[:,NUT]
            quantities.append(np.sum(np.exp(d.lnexp-d.lnp[:,NUT])*values))
    finally:
        d.lnexp[:]=oldy; d.cdf[:]=oldcdf; d.pdf[:]=oldpdf
    if min(quantities)>0 and results['aggregate_quantity'] is not None:
        fd=(np.log(quantities[0])-np.log(quantities[1]))/(2*h)
        results['aggregate_finite_difference_error']=float(abs(fd-results['aggregate_quantity']))
        assert results['aggregate_finite_difference_error']<1e-6
    else: results['aggregate_finite_difference_error']=None
    return results


def fixed_calculations(stage,theta,b):
    d=stage['data']; ref=point(stage,theta)
    out={'at_geometric_mean':ref,'at_survey_weighted_log_means':point(stage,theta,weights=stage['weights']),
         'at_arithmetic_level_means':point(stage,theta,overrides={
             'log_expenditure':np.log(np.exp(d.lnexp).mean()),
             'log_prices':np.log(np.exp(d.lnp).mean(axis=0))}),
         'by_year':{str(y):point(stage,theta,b.year.to_numpy()==y) for y in sorted(b.year.unique())},
         'micro':micro(stage,theta,b)}
    # Representative profiles vary current expenditure only. Their means/CF
    # are deliberately fixed conditioning controls, not household histories.
    out['current_expenditure_profile']={}
    for q in (.01,.05,.1,.25,.5,.75,.9,.95,.99):
        out['current_expenditure_profile'][str(q)]=point(
            stage,theta,overrides={'log_expenditure':np.quantile(d.lnexp,q)})
    qgroup=np.asarray(__import__('pandas').qcut(d.lnexp,4,labels=False))
    out['observed_expenditure_quartiles']={
        str(q+1):point(stage,theta,qgroup==q) for q in range(4)}
    # A genuinely observed representative household-year avoids fractional
    # dummies. Select it without looking at its elasticity.
    x=np.column_stack([d.lnexp,d.lnp])
    z=(x-np.median(x,axis=0))/np.maximum(x.std(0),1e-12)
    idx=int(np.argmin(np.sum(z*z,axis=1)))
    mask=np.arange(len(b))==idx
    representative=point(stage,theta,mask)
    # Publish only model-derived elasticity outputs, not this observation's
    # expenditure, prices, actual shares or household identifier.
    out['observed_representative']={key:representative[key] for key in (
        'nuts_expenditure','nuts_own_price','nuts_conditional_buyer_expenditure',
        'nuts_extensive_contribution','max_derivative_absolute_error')}
    out['observed_representative']['year']=int(b.year.iloc[idx])
    out['observed_representative']['selection_rule']='closest standardized price/expenditure vector to component medians, without using the elasticity'
    return out
