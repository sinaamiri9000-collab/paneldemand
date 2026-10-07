"""Independent algebra/derivative checks for the estimator extension."""
import unittest
import numpy as np
from scipy.stats import norm
from panel_core import PanelCore,solver
from pyquaidsce.params import unpack
from pyquaidsce.model import fitted_shares
from pyquaidsce.selection import FirstStageLayout


class PanelCoreTests(unittest.TestCase):
    def setUp(self):
        r=np.random.default_rng(107)
        N,n,q=19,4,3
        L=r.normal(0,.2,(N,n));x=r.normal(3,.3,N)
        k=r.normal(1,.5,(N,n));w=r.dirichlet(np.ones(n),N)
        self.core=PanelCore(L,x,w,norm.cdf(k),norm.pdf(k),r.normal(0,.2,N),r.normal(size=(N,q)),1.)
        self.theta=r.normal(0,.015,self.core.spec.n_free)
        self.theta[self.core.base_slices['alpha']]=[.3,.2,.25]

    def test_independent_translated_quaids_and_restrictions(self):
        core=self.core;native,eta=core.unpack(self.theta);c=unpack(native,core.native)
        L=core.data.lnp;a=c.alpha+core.Z@eta
        A=core.data.a0+np.sum(L*a,axis=1)+.5*np.einsum('ti,ij,tj->t',L,c.gamma,L)
        D=core.data.lnexp-A
        latent=a+L@c.gamma.T+D[:,None]*c.beta+np.exp(-L@c.beta)[:,None]*D[:,None]**2*c.lam
        self.assertTrue(np.allclose(latent.sum(1),1,atol=1e-13))
        predicted=core.data.cdf*(latent+core.data.control_function[:,None]*c.cfcoef)+core.data.pdf*c.delta
        np.testing.assert_allclose(core.fitted(self.theta),predicted,atol=1e-13)
        np.testing.assert_allclose(eta.sum(1),0,atol=1e-14)
        np.testing.assert_allclose(c.gamma.sum(1),0,atol=1e-14)
        np.testing.assert_allclose(c.gamma,c.gamma.T,atol=1e-14)
        self.assertAlmostEqual(c.cfcoef.sum(),0,places=14)
        # A common nominal price/expenditure change leaves latent shares fixed.
        shift=.4;newL=L+shift
        newA=core.data.a0+np.sum(newL*a,axis=1)+.5*np.einsum('ti,ij,tj->t',newL,c.gamma,newL)
        newD=core.data.lnexp+shift-newA
        newlatent=a+newL@c.gamma.T+newD[:,None]*c.beta+np.exp(-newL@c.beta)[:,None]*newD[:,None]**2*c.lam
        np.testing.assert_allclose(newlatent,latent,atol=1e-13)

    def test_analytic_jacobian_against_finite_difference(self):
        c=self.core;t=self.theta;J=c.jacobian(t);eps=1e-6
        fd=np.empty_like(J)
        for j in range(len(t)):
            plus=t.copy();minus=t.copy();plus[j]+=eps;minus[j]-=eps
            fd[:,:,j]=(c.fitted(plus)-c.fitted(minus))/(2*eps)
        np.testing.assert_allclose(J,fd,atol=2e-9,rtol=2e-7)

    def test_structured_solver_normal_equations(self):
        c=self.core;t=self.theta;P=np.array([[2,.1,0,0],[0,1,.1,0],[0,0,1.2,.1],[0,0,0,1.5]])
        J=np.matmul(P,c.jacobian(t)).reshape(-1,c.spec.n_free)
        u=((c.data.shares-c.fitted(t))@P.T).ravel()
        G,g,obj=c.normal(t,c.data,c.spec,None,P,7)
        np.testing.assert_allclose(G,J.T@J,atol=2e-12,rtol=1e-11)
        np.testing.assert_allclose(g,J.T@u,atol=2e-12,rtol=1e-11)
        self.assertAlmostEqual(obj,u@u,places=12)

    def test_package_hooks_restored_on_exception(self):
        names=['make_cache','residuals','_fitted_chunk','_normal_equations']
        before={n:getattr(solver,n) for n in names}
        with self.assertRaisesRegex(RuntimeError,'test exception'):
            with self.core.adapters():
                raise RuntimeError('test exception')
        for name,old in before.items():self.assertIs(getattr(solver,name),old)
        native,_=self.core.unpack(self.theta)
        self.assertTrue(np.isfinite(fitted_shares(native,self.core.data,self.core.native)).all())

    def test_conditional_price_expenditure_derivatives(self):
        c=self.core;d=c.data;n=c.spec.neqn;eps=1e-6
        names=tuple(f'p{i}' for i in range(n))
        layout=FirstStageLayout(names+('lnx',),names,{v:i for i,v in enumerate(names)},n,{},None,n+1)
        tau=np.random.default_rng(8).normal(0,.1,(n,n+2))
        k=norm.ppf(d.cdf);dx,dp=c.fitted_derivatives(self.theta,tau.ravel(),layout,k)
        oldL=d.lnp.copy();oldx=d.lnexp.copy();oldcdf=d.cdf.copy();oldpdf=d.pdf.copy()
        try:
            for j in range(n+1):
                predictions=[]
                for sign in [1,-1]:
                    d.lnp=oldL.copy();d.lnexp=oldx.copy()
                    if j<n:d.lnp[:,j]+=sign*eps
                    else:d.lnexp+=sign*eps
                    newk=k+sign*eps*tau[:,j]
                    d.cdf=norm.cdf(newk);d.pdf=norm.pdf(newk)
                    predictions.append(c.fitted(self.theta))
                fd=(predictions[0]-predictions[1])/(2*eps)
                np.testing.assert_allclose(fd,dp[:,:,j] if j<n else dx,atol=2e-9,rtol=2e-7)
        finally:d.lnp=oldL;d.lnexp=oldx;d.cdf=oldcdf;d.pdf=oldpdf


if __name__=='__main__':unittest.main()
