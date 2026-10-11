"""Explicitly provisional, conditional household-cluster slope Wald tests.

CF, Probit and estimated Sigma are fixed here. This is NOT the full three-stage
covariance, and the output cannot be used as final historical-change evidence.
Only projected 176-dimensional cluster scores are retained, not microdata.
"""
import argparse
import pickle
import numpy as np
import pandas as pd
from pilot.common.run import dump, wald
from pilot.b1_fourteen.run import WORK, MODEL_MAP, core_for


def conditional_test(name):
    if not MODEL_MAP[name]['history']: raise ValueError('Historical model required')
    stage=pickle.load(open(WORK/f'{name}_stage.pkl','rb'))
    fit=pickle.load(open(WORK/f'{name}_fit.pkl','rb')); assert fit.converged
    core=core_for(stage); n=core.data.nobs
    P=np.linalg.inv(np.linalg.cholesky(fit.sigma)); W=np.linalg.inv(fit.sigma)
    G,grad,obj=core.normal(fit.theta,core.data,core.spec,None,P,3000)
    ids=np.arange(core.common_base,core.spec.nbase)
    sc=np.sqrt(np.maximum(np.diag(G),1e-300))
    GG=G/sc[:,None]/sc[None,:]
    eigen=np.linalg.eigvalsh(GG)
    if eigen.min() <= 1e-11:
        raise RuntimeError(f'{name}: conditional information is too singular for a reliable Wald test: {eigen.min()}')
    # Rows of G^-1 corresponding to slope contrasts, solved in scaled units.
    selector=np.eye(core.spec.n_free)[:,ids]
    L=(np.linalg.solve(GG,selector/sc[:,None])/sc[:,None]).T
    group,H=pd.factorize(stage['panel_ids'],sort=False); H=len(H)
    cluster=np.zeros((H,len(ids)))
    for start in range(0,n,300):
        rows=slice(start,min(start+300,n))
        J=core.jacobian(fit.theta,rows)
        u=core.data.shares[rows]-core.fitted(fit.theta,rows)
        scores=np.einsum('nik,ni->nk',J,u@W,optimize=True)
        np.add.at(cluster,group[rows],scores@L.T)
    covariance=(cluster.T@cluster)*(H/(H-1))
    # Report five requested/related blocks from the same unrestricted fit.
    b=np.r_[np.arange(0,11),np.arange(88,99)]
    g=np.r_[np.arange(11,77),np.arange(99,165)]
    lam=np.r_[np.arange(77,88),np.arange(165,176)]
    tests={k:wald(fit.theta[ids],covariance,v) for k,v in {
        'beta':b,'Gamma':g,'lambda':lam,'expenditure_beta_lambda':np.r_[b,lam],
        'joint_beta_Gamma_lambda':np.arange(176)}.items()}
    for test in tests.values():
        test['qualification']='PROVISIONAL: CF and 12 Probits and Sigma fixed; conditional GN household-cluster covariance; no price-construction uncertainty'
    import json
    path=WORK/f'{name}_result.json'; result=json.loads(path.read_text())
    result['conditional_historical_tests']=tests
    result['conditional_test_diagnostics']={'clusters':H,'observations':n,
        'minimum_scaled_information_eigenvalue':float(eigen.min()),'contrast_covariance_rank':int(np.linalg.matrix_rank(covariance)),
        'inference_scope':'conditional, not the final multistage test'}
    dump(path,result); print(name,tests,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('model',choices=[m for m in MODEL_MAP if m.endswith('_history')])
    conditional_test(ap.parse_args().model)
