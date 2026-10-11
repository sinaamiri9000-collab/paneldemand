"""Independent checks of weighted objectives and conditional elasticity targets."""
import unittest
from .design import working_core, weighted_probit, rf_diagnostics
from .evaluate import point, NUT
import numpy as np
from scipy.stats import norm
from pyquaidsce.model import DemandData
from pyquaidsce.selection import FirstStageLayout
from pilot.common.specification_core import SpecificationCore
from pilot.b1_fourteen.probit_adapter import finite_probit


class Checks(unittest.TestCase):
    def setUp(self):
        r=np.random.default_rng(1401); n,m,q=24,12,3
        lp=r.normal(0,.12,(n,m)); y=r.normal(3,.2,n)
        Z=r.normal(0,.15,(n,q)); cf=r.normal(0,.1,n)
        controls=['household_size','mean_head_age','mean_cf_residual']
        names=[f'lnp_{i+1}' for i in range(m)]+['ln_expenditure']+controls+['cf_residual']
        X=np.column_stack([lp,y,Z,cf])
        tau=r.normal(0,.025,(m,len(names)+1)); tau[:,-1]=.6
        k=X@tau[:,:-1].T+tau[:,-1]
        d=DemandData(lp,y,r.dirichlet(np.ones(m)*3,n),np.zeros((n,1)),
                     norm.cdf(k),norm.pdf(k),1.,cf)
        layout=FirstStageLayout(tuple(names),tuple(names[:m]),
            {c:i for i,c in enumerate(names[:m])},m,{},len(names)-1,len(names))
        self.stage=dict(data=d,Z=Z,control_names=controls,centers=np.zeros(q),
            scales=np.ones(q),additive_columns=[2],selection_names=names,
            selection_index=k,tau=tau,layout=layout,weights=np.exp(r.normal(size=n)))
        self.core=SpecificationCore(d,Z,[2])
        self.theta=r.normal(0,.002,self.core.spec.n_free)
        self.theta[self.core.base_slices['alpha']]=1/m

    def test_weighted_normal_matches_independent_dense_gls(self):
        d=self.stage['data']; core=self.core; th=self.theta
        weights=self.stage['weights']/np.mean(self.stage['weights'])
        sw=np.sqrt(weights)
        scaled=working_core(self.stage,True)
        mu=core.fitted(th); J=core.jacobian(th)
        np.testing.assert_allclose(scaled.fitted(th),sw[:,None]*mu,atol=1e-14)
        # Non-diagonal equation covariance verifies weights and whitening together.
        r=np.random.default_rng(3); A=r.normal(size=(12,12))
        P=np.linalg.cholesky(np.linalg.inv(A@A.T+np.eye(12))).T
        denseJ=(np.matmul(P,J)*sw[:,None,None]).reshape(-1,len(th))
        denseu=((d.shares-mu)@P.T*sw[:,None]).ravel()
        G,g,obj=scaled.normal(th,scaled.data,scaled.spec,None,P,7)
        np.testing.assert_allclose(G,denseJ.T@denseJ,atol=2e-12,rtol=2e-11)
        np.testing.assert_allclose(g,denseJ.T@denseu,atol=2e-12,rtol=2e-11)
        self.assertAlmostEqual(obj,denseu@denseu,places=12)
        np.testing.assert_array_equal(self.stage['data'].shares,d.shares)

    def test_buyer_conditional_quantity_derivative_independently(self):
        ref=point(self.stage,self.theta); h=1e-5
        y=self.stage['data'].lnexp.mean(); vals=[]
        for sign in (1,-1):
            p=point(self.stage,self.theta,overrides={'log_expenditure':y+sign*h})
            vals.append(np.exp(y+sign*h)*p['nuts_predicted_share']/p['nuts_probability'])
        fd=(np.log(vals[0])-np.log(vals[1]))/(2*h)
        self.assertAlmostEqual(fd,ref['nuts_conditional_buyer_expenditure'],places=8)
        self.assertAlmostEqual(ref['nuts_expenditure'],
            ref['nuts_conditional_buyer_expenditure']+ref['nuts_extensive_contribution'],places=13)
        self.assertLess(ref['max_derivative_absolute_error'],1e-8)

    def test_zero_observed_share_keeps_native_ratio_undefined(self):
        self.stage['data'].shares[:,NUT]=0
        ref=point(self.stage,self.theta)
        self.assertTrue(np.isnan(ref['nuts_legacy_package_expenditure']))
        self.assertTrue(np.isfinite(ref['nuts_expenditure']))

    def test_weighted_probit_matches_native_and_weight_normalization(self):
        r=np.random.default_rng(19); X=r.normal(size=(800,3))
        y=(r.random(800)<norm.cdf(X@np.array([.3,-.2,.15])+.1)).astype(float)
        native,_=finite_probit(y,X,tol=1e-10,max_iter=100)
        equal,meta=weighted_probit(y,X,np.ones(len(y)))
        np.testing.assert_allclose(equal,native.b,atol=2e-7,rtol=2e-7)
        w=np.exp(r.normal(0,.4,len(y)))
        a,ma=weighted_probit(y,X,w); b,mb=weighted_probit(y,X,17*w)
        np.testing.assert_allclose(a,b,atol=1e-12,rtol=1e-12)
        self.assertLess(ma['relative_newton_decrement'],1e-10)

    def test_rf_relevance_against_independent_partial_regression(self):
        r=np.random.default_rng(110); n=24
        x=r.normal(size=n); z=r.normal(size=n)
        X=np.column_stack([np.ones(n),x,z,z*z])
        y=X@np.array([3.,.2,.5,-.1])+r.normal(0,.15,n)
        w=self.stage['weights']/self.stage['weights'].mean(); sw=np.sqrt(w)
        coef=np.linalg.lstsq(X*sw[:,None],y*sw,rcond=None)[0]
        names=['constant','control','ln_income_centered','ln_income_centered_squared']
        self.stage.update(Xrf=X,rf_names=names,panel_ids=np.repeat(np.arange(8),3),
            first_stage={'coefficients':dict(zip(names,coef)),
                         'excluded_current_income_partial_r_squared':0.})
        self.stage['data'].lnexp=y
        self.stage['data'].control_function=y-X@coef
        before=self.stage['data'].control_function.copy()
        out=rf_diagnostics(self.stage)
        # Residualize excluded instruments against included controls first.
        A=X[:,:2]*sw[:,None]; Z=X[:,2:]*sw[:,None]
        Zr=Z-A@np.linalg.lstsq(A,Z,rcond=None)[0]
        extra=np.linalg.norm(Zr@coef[2:])**2
        rss=np.sum(w*before**2)
        expected=(extra/2)/(rss/(n-X.shape[1]))
        self.assertAlmostEqual(out['excluded_current_income_classical_f'],expected,places=10)
        self.assertGreater(out['excluded_current_income_partial_r_squared'],0)
        self.assertGreater(out['excluded_current_income_panel_cluster_wald'],0)
        np.testing.assert_array_equal(before,self.stage['data'].control_function)


if __name__=='__main__': unittest.main()
