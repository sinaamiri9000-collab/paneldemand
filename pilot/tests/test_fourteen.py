"""Independent checks of historical B1 algebra, exact Gram, and input partials."""
import unittest
import numpy as np
from scipy.stats import norm
from pyquaidsce.model import DemandData
from pyquaidsce.params import unpack
from pyquaidsce.selection import FirstStageLayout
from pilot.common.specification_core import SpecificationCore
from pilot.b1_fourteen.historical_core import HistoricalCore
from pilot.b1_fourteen.run import identified, hhmean, regimes, MODELS
from pilot.b1_fourteen.probit_adapter import penalized_objective, separation_certificate


class HistoricalB1Tests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(218)
        n,m,q = 18,4,3
        L = rng.normal(0,.12,(n,m)); y = rng.normal(3,.2,n)
        Z = rng.normal(0,.2,(n,q)); cf = rng.normal(0,.1,n)
        self.codes = np.arange(n)%3
        self.tau = rng.normal(0,.04,(3,m,m+2))
        self.k = np.array([self.tau[c]@np.r_[L[i],y[i],1]
                           for i,c in enumerate(self.codes)])
        d = DemandData(L,y,rng.dirichlet(np.ones(m)*3,n),np.zeros((n,1)),
                       norm.cdf(self.k),norm.pdf(self.k),1.,cf)
        self.base = SpecificationCore(d,Z,[2])
        self.core = HistoricalCore(d,Z,self.codes,[2])
        th = rng.normal(0,.006,self.base.spec.n_free)
        th[self.base.base_slices['alpha']] = [.3,.25,.2]
        self.theta = self.core.warm_start(th)
        self.common = th
        pn = tuple(f'p{i}' for i in range(m)); sn = pn+('y',)
        self.layout = FirstStageLayout(sn,pn,{p:i for i,p in enumerate(pn)},m,{},None,len(sn))

    def test_nesting_and_restrictions(self):
        np.testing.assert_allclose(self.core.fitted(self.theta),self.base.fitted(self.common),atol=2e-15)
        self.theta[self.core.common_base:self.core.spec.nbase] = .009
        for r in range(3):
            nt,eta = self.core.unpack(self.theta,r); c = unpack(nt,self.core.native)
            np.testing.assert_allclose([c.alpha.sum(),c.beta.sum(),c.lam.sum()],[1,0,0],atol=1e-14)
            np.testing.assert_allclose(c.gamma.sum(axis=1),0,atol=1e-14)
            np.testing.assert_allclose(c.gamma,c.gamma.T,atol=1e-14)
            np.testing.assert_allclose(eta.sum(axis=1),0,atol=1e-14)

    def test_parameter_derivatives_and_exact_gram(self):
        self.theta[self.core.common_base:self.core.spec.nbase] = .004
        J = self.core.jacobian(self.theta)
        for j in range(len(self.theta)):
            e = np.zeros_like(self.theta); e[j] = 1e-6
            fd = (self.core.fitted(self.theta+e)-self.core.fitted(self.theta-e))/(2e-6)
            np.testing.assert_allclose(J[:,:,j],fd,rtol=1e-5,atol=3e-9)
        P = np.array([[1,.1,0,.2],[0,1,.15,0],[0,0,1,.1],[0,0,0,1]])
        G,g,obj = self.core.normal(self.theta,self.core.data,self.core.spec,None,P,5)
        A = (P@J).reshape(-1,len(self.theta))
        u = ((self.core.data.shares-self.core.fitted(self.theta))@P.T).ravel()
        np.testing.assert_allclose(G,A.T@A,rtol=1e-12,atol=1e-12)
        np.testing.assert_allclose(g,A.T@u,rtol=1e-12,atol=1e-12)
        self.assertAlmostEqual(obj,float(u@u),places=12)

    def test_current_input_partials_means_and_cf_fixed(self):
        self.theta[self.core.common_base:self.core.spec.nbase] = .004
        d = self.core.data; L = d.lnp.copy(); y = d.lnexp.copy()
        dx,dp = self.core.fitted_derivatives(self.theta,self.tau,self.layout,self.k)
        h = 1e-6
        for j in range(5):
            val = []
            for sign in (1,-1):
                d.lnp[:] = L; d.lnexp[:] = y
                if j<4: d.lnp[:,j] += sign*h
                else: d.lnexp[:] += sign*h
                kk = self.k+sign*h*self.tau[self.codes,:,j]
                d.cdf[:] = norm.cdf(kk); d.pdf[:] = norm.pdf(kk)
                val.append(self.core.fitted(self.theta))
            expected = dp[:,:,j] if j<4 else dx
            np.testing.assert_allclose((val[0]-val[1])/(2*h),expected,rtol=2e-6,atol=2e-9)

    def test_interaction_means_and_declared_design(self):
        import pandas as pd
        x = pd.DataFrame({'x':[0,2,3,4,0,0]})
        means = hhmean(x,[1,1,1,2,2,2])
        np.testing.assert_allclose(means.x,[5/3]*3+[4/3]*3)
        d, dropped = identified(pd.DataFrame({'a':[0,1,2,3], 'b':[0,2,4,6], 'c':[0,0,1,0]}))
        self.assertEqual(list(d),['a','c']); self.assertEqual(dropped[0]['name'],'b')
        np.testing.assert_array_equal(regimes([1396,1397,1398,1399,1403]),[0,1,1,2,2])
        self.assertEqual(len(MODELS),14)
        self.assertEqual(sum(m['history'] for m in MODELS),3)

    def test_jeffreys_probit_gradient_and_separation_certificate(self):
        from scipy.optimize import minimize
        rng=np.random.default_rng(612)
        X=np.column_stack([rng.normal(size=120),np.r_[np.ones(12),np.zeros(108)],np.ones(120)])
        y=(rng.random(120)<.55).astype(float); y[:12]=1
        beta=np.array([.2,.3,.1]); _,grad=penalized_objective(beta,y,X)
        for j in range(3):
            e=np.zeros(3); e[j]=1e-6
            fd=(penalized_objective(beta+e,y,X)[0]-penalized_objective(beta-e,y,X)[0])/2e-6
            self.assertAlmostEqual(grad[j],fd,places=6)
        self.assertTrue(separation_certificate(y,X)['separated'])
        fit=minimize(penalized_objective,np.zeros(3),args=(y,X),method='BFGS',jac=True,
                     options={'gtol':1e-7})
        self.assertTrue(np.isfinite(fit.x).all())
        self.assertLess(np.max(np.abs(penalized_objective(fit.x,y,X)[1])),1e-6)


if __name__ == '__main__': unittest.main()
