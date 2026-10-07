"""Thin translated CRE layer over pyquaidsce 1.7.0, no package fork.

The native QUAIDS/SY algebra, analytic Jacobian and IFGNLS/LM solver are reused.
Affine maps impose latent adding up on alpha/beta/lambda/control coefficients.
Controls translate alpha AND the translog index, preserving integrability.
Scoped solver adapters are restored on exit; ordinary package calls are intact.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import importlib
import os
import numpy as np
from pyquaidsce.params import Spec,free_slices,unpack
from pyquaidsce.model import DemandData,fitted_shares,_inner
from pyquaidsce.jacfree import make_cache,jacobian_free
from pyquaidsce.elasticities import fitted_share_derivatives
from pyquaidsce._timing import check_deadline

solver=importlib.import_module('pyquaidsce.nlsur')

@dataclass
class PanelSpec:
    nshift:int
    neqn:int=12
    @property
    def nbase(self): return 3*(self.neqn-1)+self.neqn*(self.neqn-1)//2+2*self.neqn-1
    @property
    def n_free(self): return self.nbase+self.nshift*(self.neqn-1)
    @property
    def n_eq_estimated(self): return self.neqn

class PanelCore:
    def __init__(self,lnp,lnexp,shares,cdf,pdf,cf,Z,a0):
        self.Z=np.asarray(Z,float)
        self.spec=PanelSpec(self.Z.shape[1],shares.shape[1])
        n=self.spec.neqn
        self.native=Spec(n,1,True,True,True)
        self.data=DemandData(lnp,lnexp,shares,np.zeros((len(lnexp),1)),cdf,pdf,a0,cf)
        self.cache=make_cache(self.native)
        xs=free_slices(self.native)
        self.T=np.zeros((self.native.n_free,self.spec.nbase));self.offset=np.zeros(self.native.n_free)
        B=np.vstack([np.eye(n-1),-np.ones((1,n-1))])
        self.B=B
        self.base_slices={};j=0
        for name in ['alpha','beta','gamma','lambda','delta','cfcoef']:
            width=n*(n-1)//2 if name=='gamma' else (n if name=='delta' else n-1)
            self.base_slices[name]=slice(j,j+width)
            self.T[xs[name],j:j+width]=np.eye(width) if name in ['gamma','delta'] else B
            j+=width
        self.offset[xs['alpha'].stop-1]=1
        assert j==self.spec.nbase

    def unpack(self,theta):
        n=self.spec.neqn;k=self.spec.nbase
        native=self.offset+self.T@theta[:k]
        eta=theta[k:].reshape(self.spec.nshift,n-1)@self.B.T
        return native,eta

    def chunk(self,theta,rows):
        nt,eta=self.unpack(theta)
        d=self.data.subset(rows)
        shift=self.Z[rows]@eta
        d.lnexp=d.lnexp-np.einsum('ti,ti->t',d.lnp,shift)
        return nt,d,shift

    def fitted(self,theta,rows=slice(None)):
        nt,d,shift=self.chunk(theta,rows)
        return fitted_shares(nt,d,self.native)+d.cdf*shift

    def derivative_blocks(self,theta,rows):
        nt,d,shift=self.chunk(theta,rows)
        J=jacobian_free(nt,d,self.native,self.cache)@self.T
        inn=_inner(unpack(nt,self.native),d,self.native)
        # d fitted_i/d translation_k = Phi_i [B_ik - S_i (ln p_k-ln p_n)]
        H=d.cdf[:,:,None]*(self.B[None,:,:]-inn.S[:,:,None]*(d.lnp@self.B)[:,None,:])
        return J,H

    def jacobian(self,theta,rows=slice(None)):
        J,H=self.derivative_blocks(theta,rows)
        return np.concatenate([J,(self.Z[rows,None,:,None]*H[:,:,None,:]).reshape(len(J),self.spec.neqn,-1)],axis=2)

    def fitted_derivatives(self,theta,tau,layout,selection_index,rows=slice(None)):
        """Conditional derivatives; all translations and CF residuals fixed."""
        nt,d,shift=self.chunk(theta,rows)
        dx,dp=fitted_share_derivatives(nt,d,self.native,tau=tau,layout=layout,
                                      selection_index=selection_index[rows])
        inn=_inner(unpack(nt,self.native),d,self.native)
        # lnexp_native = lnexp - lnprice @ translation, so its price derivative
        # contributes -Phi*S*translation. The original Probit index is retained.
        dp-=d.cdf[:,:,None]*inn.S[:,:,None]*shift[:,None,:]
        # The native helper excludes the additive Phi*translation term itself.
        tm=np.array([layout.coefficient(tau,i,layout.expenditure_position) for i in range(self.spec.neqn)])
        tp=np.array([[layout.coefficient(tau,i,layout.price_position(j))
                     for j in range(self.spec.neqn)] for i in range(self.spec.neqn)])
        dx+=d.pdf*shift*tm
        dp+=d.pdf[:,:,None]*shift[:,:,None]*tp[None,:,:]
        return dx,dp

    def normal(self,theta,d,spec,cache,P,chunk,deadline=None):
        # Structured Gram accumulation avoids a huge dense Jacobian for controls.
        k0,q,m=self.spec.nbase,self.spec.nshift,self.spec.neqn
        h=m-1;K=self.spec.n_free
        G=np.zeros((K,K));g=np.zeros(K);obj=0.
        for start in range(0,d.nobs,chunk):
            check_deadline(deadline);rows=slice(start,min(start+chunk,d.nobs))
            u=(d.shares[rows]-self.fitted(theta,rows))@P.T
            J,H=self.derivative_blocks(theta,rows)
            J=np.matmul(P,J);H=np.matmul(P,H);z=self.Z[rows]
            J2=J.reshape(-1,k0)
            G[:k0,:k0]+=J2.T@J2;g[:k0]+=J2.T@u.ravel()
            if q:
                cross=np.einsum('tik,tij->tkj',J,H,optimize=True)
                cross=(z.T@cross.reshape(len(z),-1)).reshape(q,k0,h).transpose(1,0,2).reshape(k0,q*h)
                G[:k0,k0:]+=cross;G[k0:,:k0]+=cross.T
                hh=np.einsum('tik,tij->tkj',H,H,optimize=True)
                zz=np.einsum('tr,ts->trs',z,z,optimize=True)
                block=(zz.reshape(len(z),-1).T@hh.reshape(len(z),-1)).reshape(q,q,h,h).transpose(0,2,1,3)
                G[k0:,k0:]+=block.reshape(q*h,q*h)
                score=np.einsum('tik,ti->tk',H,u,optimize=True)
                g[k0:]+=(z.T@score).ravel()
            obj+=float(np.sum(u*u))
        return G,g,obj

    @contextmanager
    def adapters(self):
        old={name:getattr(solver,name) for name in ['make_cache','residuals','_fitted_chunk','_normal_equations']}
        solver.make_cache=lambda spec:None
        solver.residuals=lambda th,d,spec:d.shares-self.fitted(th)
        solver._fitted_chunk=lambda th,d,spec,sl:self.fitted(th,sl)
        solver._normal_equations=self.normal
        try: yield
        finally:
            for name,value in old.items():setattr(solver,name,value)

    def fit(self,theta0=None,sigma0=None,log=print,max_outer=100,max_iter=200,algorithm='gn',gn_tol=1e-8):
        if theta0 is None:
            theta0=np.zeros(self.spec.n_free)
            theta0[self.base_slices['alpha']]=self.data.shares.mean(0)[:-1]
        with self.adapters():
            result=solver.nlsur(self.data,self.spec,theta0=theta0,sigma0=sigma0,
              method='ifgnls',algorithm=algorithm,max_outer=max_outer,max_iter=max_iter,
              param_tol=1e-7,objective_tol=1e-9,gn_tol=gn_tol,outer_param_tol=1e-5,
              chunk=3000,log=log,gn_log=log,blas_threads=int(os.environ.get('PILOT_BLAS_THREADS','1')))
        result.pilot_numerical_settings={'algorithm':algorithm,'gn_tol':gn_tol,
           'param_tol':1e-7,'objective_tol':1e-9,'outer_param_tol':1e-5,'blas_threads':int(os.environ.get('PILOT_BLAS_THREADS','1'))}
        return result
