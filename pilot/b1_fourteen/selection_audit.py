"""Audit saved native Probits for hidden separation; repair only certified cases."""
import pickle
import numpy as np
from scipy.stats import norm
from pyquaidsce.probit import _lambda_ratio
from pilot.b1_fourteen.run import WORK,MODELS,save_pickle,regimes
from pilot.b1_fourteen.probit_adapter import separation_certificate,finite_probit


def selection_matrix(stage):
    d=stage['data']; raw=stage['Z']*stage['scales']+stage['centers']
    columns=dict(zip(stage['control_names'],raw.T))
    columns.update({f'lnp_{j+1}':d.lnp[:,j] for j in range(12)})
    columns['ln_expenditure']=d.lnexp; columns['cf_residual']=d.control_function
    for r in (1,2):
        for j in range(12): columns[f'history_{r}_lnp_{j+1}']=(stage['regimes']==r)*d.lnp[:,j]
        columns[f'history_{r}_ln_expenditure']=(stage['regimes']==r)*d.lnexp
    X=np.column_stack([columns[name] for name in stage['selection_names']])
    np.testing.assert_allclose(X@stage['tau'][:,:-1].T+stage['tau'][:,-1],stage['selection_index'],atol=2e-8,rtol=2e-9)
    return X


def audit():
    repaired=[]
    for spec in MODELS:
        name=spec['name']; path=WORK/f'{name}_stage.pkl'
        stage=pickle.load(path.open('rb')); X=selection_matrix(stage)
        center=X.mean(axis=0); scale=X.std(axis=0)
        Xs=(X-center)/scale; XX=np.column_stack([Xs,np.ones(len(X))]); changed=False
        for i,diag in enumerate(stage['selection_diagnostics']):
            method=diag.get('estimation_method',{})
            if method.get('method')=='Jeffreys_prior_penalized_probit': continue
            y=(stage['data'].shares[:,i]>0).astype(float); q=2*y-1
            z=q*stage['selection_index'][:,i]; lam=_lambda_ratio(z)
            I=XX.T@((lam*(lam+z))[:,None]*XX)
            try: maxvar=float(np.max(np.abs(np.diag(np.linalg.inv(I)))))
            except np.linalg.LinAlgError: maxvar=float('inf')
            score=XX.T@(q*lam); maxscore=float(max(abs(score)))
            try: decrement=float(score@np.linalg.solve(I,score))/(1+abs(diag['log_likelihood']))
            except np.linalg.LinAlgError: decrement=float('inf')
            method.setdefault('method','native_unpenalized_probit')
            method.setdefault('native_converged',True)
            method.setdefault('native_iterations',diag['iterations'])
            method.update(audited_maximum_variance=maxvar,audited_maximum_absolute_score=maxscore,
                          audited_relative_newton_decrement=decrement)
            if maxvar>=1e6 or not 0<=decrement<=1e-10:
                cert=separation_certificate(y,XX); method['separation_certificate']=cert
                if cert['separated'] or not 0<=decrement<=1e-10:
                    r,method=finite_probit(y,Xs,certificate=cert)
                    if cert['separated'] and method['method']!='Jeffreys_prior_penalized_probit':
                        raise RuntimeError('Separation was certified but not handled')
                    bt=np.r_[r.b[:-1]/scale,r.b[-1]-center@(r.b[:-1]/scale)]
                    stage['tau'][i]=bt; kk=X@bt[:-1]+bt[-1]
                    stage['selection_index'][:,i]=kk
                    stage['data'].cdf[:,i]=norm.cdf(kk); stage['data'].pdf[:,i]=norm.pdf(kk)
                    diag.update(iterations=r.n_iter,converged=True,log_likelihood=float(r.llf))
                    changed=True; print('REPAIR',name,'group',i+1,flush=True)
            diag['estimation_method']=method
        hist=spec['history']; stage['effective_tau']=np.repeat(stage['tau'][None,:,:],3 if hist else 1,axis=0)
        if hist:
            sn=stage['selection_names']
            for code in (1,2):
                for j,pn in enumerate([f'lnp_{g}' for g in range(1,13)]+['ln_expenditure']):
                    term=f'history_{code}_{pn}'
                    if term in sn: stage['effective_tau'][code,:,j]+=stage['tau'][:,sn.index(term)]
        stage['selection_audit_complete']=True
        save_pickle(path,stage)
        if changed:
            fp=WORK/f'{name}_fit.pkl'; fp.replace(WORK/f'{name}_native_point_backup.pkl')
            rp=WORK/f'{name}_result.json'; rp.replace(WORK/f'{name}_native_result_backup.json')
            repaired.append(name)
        print('AUDITED',name,'reestimate',changed,flush=True)
    print('REESTIMATE',repaired,flush=True)


if __name__=='__main__': audit()
