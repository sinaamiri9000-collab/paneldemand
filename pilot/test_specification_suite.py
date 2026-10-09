"""Independent checks of additive CF, restrictions and multistage derivatives."""
import unittest
import numpy as np
from scipy.stats import norm
from pyquaidsce.model import DemandData
from pyquaidsce.params import unpack
from specification_core import SpecificationCore
from panel_core import PanelCore
from staged_inference import residual_hessian, input_score_derivatives, probit_components


class SpecificationTests(unittest.TestCase):
    def setUp(self):
        r = np.random.default_rng(506); n,m,q=18,4,3
        self.k=r.normal(.5,.3,(n,m))
        self.d=DemandData(r.normal(0,.2,(n,m)),r.normal(3,.2,n),r.dirichlet(np.ones(m),n),
                 np.zeros((n,1)),norm.cdf(self.k),norm.pdf(self.k),1.,r.normal(0,.2,n))
        self.Z=r.normal(0,.3,(n,q))
        self.core=SpecificationCore(self.d,self.Z,[2])
        self.th=r.normal(0,.02,self.core.spec.n_free)
        self.th[self.core.base_slices['alpha']]=[.3,.2,.25]
        a=r.normal(size=(m,m));self.W=np.linalg.inv(a@a.T+np.eye(m))

    def score(self,theta=None):
        if theta is None:theta=self.th
        c=self.core;J=c.jacobian(theta);u=c.data.shares-c.fitted(theta)
        return np.einsum('nik,ni->k',J,u@self.W)

    def test_independent_algebra_and_restrictions(self):
        core=self.core;nt,eta=core.unpack(self.th);c=unpack(nt,core.native);L=self.d.lnp
        a=c.alpha+self.Z[:,:2]@eta[:2];ad=self.Z[:,2,None]*eta[2]
        A=self.d.a0+(a*L).sum(1)+.5*np.einsum('ni,ij,nj->n',L,c.gamma,L)
        q=self.d.lnexp-A
        f=a+L@c.gamma.T+q[:,None]*c.beta+np.exp(-L@c.beta)[:,None]*q[:,None]**2*c.lam
        augmented=f+self.d.control_function[:,None]*c.cfcoef+ad
        np.testing.assert_allclose(augmented.sum(1),1,atol=1e-13)
        expected=self.d.cdf*augmented+self.d.pdf*c.delta
        np.testing.assert_allclose(core.fitted(self.th),expected,atol=1e-13)
        # Additive mean CF never changes the translog index or real expenditure.
        before=core.quantities(self.th)[1].lnexp.copy()
        t=self.th.copy();t[-3:]+=.1
        np.testing.assert_array_equal(core.quantities(t)[1].lnexp,before)

    def test_no_additive_reproduces_previous_core(self):
        c=SpecificationCore(self.d,self.Z)
        old=PanelCore(self.d.lnp,self.d.lnexp,self.d.shares,self.d.cdf,self.d.pdf,
                      self.d.control_function,self.Z,self.d.a0)
        np.testing.assert_allclose(c.fitted(self.th),old.fitted(self.th),atol=1e-14)
        np.testing.assert_allclose(c.jacobian(self.th),old.jacobian(self.th),atol=1e-14)

    def test_analytic_jacobian_and_exact_gram(self):
        c=self.core;J=c.jacobian(self.th);eps=1e-6
        fd=np.zeros_like(J)
        for j in range(len(self.th)):
            e=np.zeros_like(self.th);e[j]=eps
            fd[:,:,j]=(c.fitted(self.th+e)-c.fitted(self.th-e))/(2*eps)
        np.testing.assert_allclose(J,fd,rtol=2e-6,atol=2e-9)
        P=np.linalg.cholesky(self.W).T
        jw=np.matmul(P,J).reshape(-1,c.spec.n_free)
        u=((self.d.shares-c.fitted(self.th))@P.T).ravel()
        G,g,obj=c.normal(self.th,self.d,c.spec,None,P,7)
        np.testing.assert_allclose(G,jw.T@jw,rtol=1e-11,atol=1e-12)
        np.testing.assert_allclose(g,jw.T@u,rtol=1e-11,atol=1e-12)
        self.assertAlmostEqual(obj,u@u,places=12)

    def test_observed_hessian_with_additive_block(self):
        c=self.core;J=c.jacobian(self.th);u=self.d.shares-c.fitted(self.th)
        G=np.einsum('nik,ij,njl->kl',J,self.W,J)
        bread=G-residual_hessian(c,self.th,slice(None),u@self.W)
        fd=np.zeros_like(bread)
        for j in range(len(self.th)):
            e=np.zeros_like(self.th);e[j]=1e-6
            fd[:,j]=-(self.score(self.th+e)-self.score(self.th-e))/(2e-6)
        np.testing.assert_allclose(bread,fd,rtol=3e-5,atol=2e-8)

    def test_additive_mean_cf_score_sensitivity(self):
        c=self.core
        result=input_score_derivatives(c,self.th,slice(None),self.k,self.W,2,1.7)
        sm=result[6];fm=result[9];eta=c.unpack(self.th)[1]
        np.testing.assert_allclose(fm,self.d.cdf*eta[2]/1.7,atol=1e-13)
        direction=np.linspace(-.3,.5,len(self.Z));old=c.Z[:,2].copy();values=[]
        for sign in [1,-1]:
            c.Z[:,2]=old+sign*1e-6*direction/1.7;values.append(self.score())
        c.Z[:,2]=old
        np.testing.assert_allclose(sm.T@direction,(values[0]-values[1])/2e-6,rtol=2e-5,atol=2e-8)
        absent=input_score_derivatives(c,self.th,slice(None),self.k,self.W,-1,1.)
        np.testing.assert_array_equal(absent[6],0);np.testing.assert_array_equal(absent[9],0)

    def test_probit_without_mean_cf_cross_derivative(self):
        r=np.random.default_rng(6);Xs=r.normal(size=(18,4));Xs[:,-1]=1
        tau=np.array([.2,.1,-.3,.4]);scale=np.array([.8,1.2,1.5]);cf=2
        Xr=r.normal(size=(18,3));Xbar=np.repeat(Xr.reshape(6,3,3).mean(1),3,axis=0)
        y=(np.arange(18)%3!=1).astype(float);q=2*y-1
        from pyquaidsce.probit import _lambda_ratio
        _,_,cross=probit_components(Xs,Xs@tau,y,Xr,Xbar,tau[cf]/scale[cf],0,cf,-1,scale)
        for j in range(3):
            val=[]
            for sign in [1,-1]:
                xp=Xs.copy();xp[:,cf]-=sign*1e-6*Xr[:,j]/scale[cf]
                val.append(xp.T@(q*_lambda_ratio(q*(xp@tau))))
            np.testing.assert_allclose(cross[:,j],(val[0]-val[1])/2e-6,rtol=2e-5,atol=2e-8)


class AggregateOutputTests(unittest.TestCase):
    def test_twelve_good_coefficients_and_additive_reference_elasticities(self):
        from types import SimpleNamespace
        from pyquaidsce.selection import FirstStageLayout
        from specification_suite import inference_design, coefficient_summary, SuiteElasticities
        from pyquaidsce.elasticities import Means, elasticities
        r=np.random.default_rng(106);n,m,q=18,12,3
        L=r.normal(0,.2,(n,m));y=r.normal(3,.2,n);raw=r.normal(0,.2,(n,q));cf=r.normal(0,.2,n)
        names=['household_size','mean_head_age','mean_cf_residual']
        xsel=np.column_stack([L,y,raw,cf]);tau=np.zeros((m,xsel.shape[1]+1));tau[:,-1]=1
        k=np.ones((n,m));data=DemandData(L,y,r.dirichlet(np.ones(m)*4,n),np.zeros((n,1)),norm.cdf(k),norm.pdf(k),1.,cf)
        core=SpecificationCore(data,raw,[2]);theta=np.zeros(core.spec.n_free)
        theta[core.base_slices['alpha']]=np.repeat(1/m,m-1)
        theta[core.base_slices['beta']]=r.normal(0,.004,m-1)
        theta[core.spec.nbase+2*11:]=r.normal(0,.005,11)
        fit=SimpleNamespace(theta=theta)
        ordered=tuple([f'lnp_{j+1}' for j in range(12)]+['ln_expenditure']+names+['cf_residual'])
        layout=FirstStageLayout(ordered,ordered[:12],{c:j for j,c in enumerate(ordered[:12])},12,
                   {c:13+j for j,c in enumerate(names)},len(ordered)-1,len(ordered))
        stage={'data':data,'Z':raw,'centers':np.zeros(q),'scales':np.ones(q),
               'control_names':names,'additive_columns':[2],'tau':tau,'selection_index':k,'layout':layout,
               'Xrf':np.column_stack([np.ones(n),r.normal(size=(n,2))]),'rf_names':['constant','z','z2'],
               'weights':np.ones(n),'first_stage':{'coefficients':{'constant':1.,'z':.2,'z2':.1}}}
        design=inference_design(stage);K=core.spec.n_free;Q=design.Xs.shape[1];R=design.Xr.shape[1]
        output=coefficient_summary(core,fit,stage,np.eye(K+12*Q+R))
        self.assertEqual(len(output['lambda']),12)
        self.assertEqual(output['standard_errors']['gamma'].shape,(12,12))
        np.testing.assert_allclose(output['cf_mean'].sum(),0,atol=1e-14)
        ref=SuiteElasticities(core,fit,stage,design);e=ref.evaluate(ref.point)
        nt,eta=core.unpack(theta);c=unpack(nt,core.native)
        additive=raw[:,2].mean()*eta[2]
        native=elasticities(c,core.native,Means(data.shares.mean(0),L.mean(0),float(y.mean()),np.zeros(1),
                   data.cdf.mean(0),data.pdf.mean(0),k.mean(0),0.),data.a0,tau=tau.ravel(),np_prob=Q,layout=layout)
        # With zero price/expenditure Probit slopes, additive CF changes only
        # the native corrected denominator, while structural derivatives agree.
        wbar=data.shares.mean(0);den=wbar*data.cdf.mean(0)+additive*data.cdf.mean(0)
        expected=1+(native.income-1)*(wbar*data.cdf.mean(0))/den
        np.testing.assert_allclose(e[:12],expected,atol=1e-13)


if __name__=='__main__':unittest.main()
