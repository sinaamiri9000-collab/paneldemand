"""Independent checks for slope contrasts and the restricted-model nesting."""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import unittest
import numpy as np
from scipy.stats import norm
from pilot.common.panel_core import PanelCore
from pilot.common.regime_core import RegimeCore
from pyquaidsce.params import unpack


class RegimeTests(unittest.TestCase):
    def setUp(self):
        r=np.random.default_rng(1400);n,m,q=18,4,2
        x=r.normal(3,.2,n);L=r.normal(0,.15,(n,m));k=r.normal(1,.3,(n,m))
        self.base=PanelCore(L,x,r.dirichlet(np.ones(m),n),norm.cdf(k),norm.pdf(k),
                            r.normal(0,.1,n),r.normal(size=(n,q)),1)
        self.core=RegimeCore(self.base.data,self.base.Z,np.arange(n)%3)
        self.th=r.normal(0,.012,self.base.spec.n_free)
        self.th[self.base.base_slices['alpha']]=[.3,.2,.25]

    def test_nesting_and_restrictions_each_regime(self):
        th=self.core.warm_start(self.th)
        np.testing.assert_allclose(self.core.fitted(th),self.base.fitted(self.th),atol=2e-15)
        th[self.core.common_base:self.core.spec.nbase]=.02
        for reg in range(3):
            nt,_=self.core.unpack(th,reg);c=unpack(nt,self.core.native)
            self.assertAlmostEqual(c.alpha.sum(),1)
            self.assertAlmostEqual(c.beta.sum(),0)
            self.assertAlmostEqual(c.lam.sum(),0)
            np.testing.assert_allclose(c.gamma,c.gamma.T,atol=2e-15)
            np.testing.assert_allclose(c.gamma.sum(1),0,atol=2e-15)

    def test_full_jacobian_and_gram(self):
        th=self.core.warm_start(self.th)
        th[self.core.common_base:self.core.spec.nbase]=.008
        J=self.core.jacobian(th)
        for j in range(len(th)):
            d=np.zeros_like(th);d[j]=1e-6
            fd=(self.core.fitted(th+d)-self.core.fitted(th-d))/(2e-6)
            np.testing.assert_allclose(J[:,:,j],fd,rtol=2e-5,atol=2e-8)
        a=np.random.default_rng(86).normal(size=(self.core.spec.neqn,self.core.spec.neqn))
        P=np.linalg.inv(np.linalg.cholesky(a@a.T+np.eye(self.core.spec.neqn)))
        G,g,obj=self.core.normal(th,self.core.data,self.core.spec,None,P,6)
        flat=(P@J).reshape(-1,len(th));res=((self.core.data.shares-self.core.fitted(th))@P.T).ravel()
        np.testing.assert_allclose(G,flat.T@flat,rtol=1e-12,atol=1e-12)
        np.testing.assert_allclose(g,flat.T@res,rtol=1e-12,atol=1e-12)
        self.assertAlmostEqual(obj,float(res@res),places=12)


if __name__=='__main__':unittest.main()
