"""Finite Probit estimates when the native MLE faces verified separation.

Kosmidis & Firth (2021), Biometrika 108:71--82, DOI 10.1093/biomet/asaa052,
Section 3 (including probit in Table 1) and Section 4. This is Jeffreys-prior
penalized Probit, NOT a claim that generic probit equals Firth mean-bias reduction.
Unpenalized native likelihood is retained wherever a finite regular MLE exists.
"""
import importlib
import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize, linprog
from scipy.stats import norm
from pyquaidsce.probit import probit, ProbitResult, _lambda_ratio


def separation_certificate(y, X):
    A=(2*y-1)[:,None]*X
    fit=linprog(-A.sum(axis=0),A_ub=-A,b_ub=np.zeros(len(A)),
                bounds=[(-1,1)]*X.shape[1],method='highs',options={'time_limit':60})
    if not fit.success: raise RuntimeError('Separation LP could not certify overlap or separation')
    margins=A@fit.x
    separated=margins.min()>=-1e-7 and margins.sum()>1e-5
    return {'separated':bool(separated),'minimum_signed_margin':float(margins.min()),
            'sum_signed_margin':float(margins.sum()),
            'strictly_positive_rows':int((margins>1e-7).sum()),
            'direction':fit.x.tolist() if separated else None}


def penalized_objective(beta,y,X):
    eta=X@beta; q=2*y-1
    lw=2*norm.logpdf(eta)-norm.logcdf(eta)-norm.logcdf(-eta)
    w=np.exp(lw); I=X.T@(w[:,None]*X)
    chol=cho_factor(I,lower=True,check_finite=False)
    logdet=2*np.log(np.diag(chol[0])).sum()
    h=w*np.einsum('ij,ij->i',X,cho_solve(chol,X.T,check_finite=False).T)
    dlw=-2*eta-_lambda_ratio(eta)+_lambda_ratio(-eta)
    ll=norm.logcdf(q*eta).sum()
    score=X.T@(q*_lambda_ratio(q*eta)+.5*h*dlw)
    return -float(ll+.5*logdet),-score


def finite_probit(y,X,tol=1e-10,max_iter=100,certificate=None):
    """Use native MLE; certify problematic cases before any estimator change."""
    pm=importlib.import_module('pyquaidsce.probit'); original=pm._drop_collinear
    try:
        pm._drop_collinear=lambda X,tol=1e-11: []
        try: r=probit(y,X,tol=tol,max_iter=max_iter)
        except np.linalg.LinAlgError:
            k=X.shape[1]+1
            r=ProbitResult(np.zeros(k),np.diag(np.full(k,np.inf)),
                           float('-inf'),len(y),max_iter,False,[])
    finally: pm._drop_collinear=original
    meta={'method':'native_unpenalized_probit','native_converged':bool(r.converged),
          'native_iterations':int(r.n_iter),'native_max_variance':float(np.max(np.abs(np.diag(r.V))))}
    XX=np.column_stack([X,np.ones(len(X))])
    q=2*y-1; native_score=XX.T@(q*_lambda_ratio(q*(XX@r.b)))
    meta['native_maximum_absolute_score']=float(max(abs(native_score)))
    decrement=float(native_score@r.V@native_score)/(1+abs(r.llf)) if np.isfinite(r.V).all() else float('inf')
    meta['native_relative_newton_decrement']=decrement
    if (certificate is None and r.converged and meta['native_max_variance']<1e6 and
            0<=decrement<=tol): return r,meta
    cert=certificate if certificate is not None else separation_certificate(y,XX)
    meta['separation_certificate']=cert
    if not cert['separated'] and r.converged and 0<=decrement<=tol: return r,meta
    if cert['separated']:
        # Directly optimize the source's objective l + 1/2 logdet expected I.
        b0=np.zeros(XX.shape[1]); b0[-1]=norm.ppf(np.clip(y.mean(),1e-6,1-1e-6))
        fit=minimize(penalized_objective,b0,args=(y,XX),method='BFGS',jac=True,
                     options={'gtol':1e-7,'maxiter':400})
        loss,score=penalized_objective(fit.x,y,XX)
        if np.max(np.abs(score))>2e-5 or not np.isfinite(fit.x).all():
            raise RuntimeError(f'Jeffreys Probit stationarity failed: {fit.message}; score {max(abs(score))}')
        eta=XX@fit.x
        w=np.exp(2*norm.logpdf(eta)-norm.logcdf(eta)-norm.logcdf(-eta))
        I=XX.T@(w[:,None]*XX)
        r=ProbitResult(fit.x,np.linalg.inv(I),float(norm.logcdf(q*eta).sum()),
                       len(y),int(fit.nit),True,[])
        meta.update(method='Jeffreys_prior_penalized_probit',penalty_logdet_multiplier=.5,
                    penalized_log_likelihood=-loss,maximum_absolute_penalized_score=float(max(abs(score))),
                    optimizer_success=bool(fit.success),optimizer_message=str(fit.message),
                    expected_information_min_eigenvalue=float(np.linalg.eigvalsh(I).min()),
                    reference='Kosmidis-Firth 2021, DOI 10.1093/biomet/asaa052, sections 3-4')
        return r,meta
    # A numerical failure without separation keeps exactly the same ML objective.
    def loss(beta):
        z=q*(XX@beta)
        return -float(norm.logcdf(z).sum()),-XX.T@(q*_lambda_ratio(z))
    fit=minimize(loss,r.b,method='BFGS',jac=True,options={'gtol':1e-7,'maxiter':400})
    eta=XX@fit.x; lam=_lambda_ratio(q*eta); info=XX.T@((lam*(lam+q*eta))[:,None]*XX)
    refined_decrement=float(fit.jac@np.linalg.solve(info,fit.jac))/(1+abs(fit.fun))
    if refined_decrement>tol or refined_decrement<0 or np.linalg.eigvalsh(info).min()<=0:
        raise RuntimeError('Unpenalized Probit refinement did not meet stationarity')
    meta.update(method='unpenalized_probit_BFGS_refinement',maximum_absolute_score=float(max(abs(fit.jac))),
                relative_newton_decrement=refined_decrement,
                optimizer_success=bool(fit.success),optimizer_message=str(fit.message))
    return ProbitResult(fit.x,np.linalg.inv(info),-float(fit.fun),len(y),int(fit.nit),True,[]),meta
