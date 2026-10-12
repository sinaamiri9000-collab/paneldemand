"""Check historical warm starts and XLSX handling of undefined elasticities."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from .run import base,trim_controls,warm_start,is_square_mean
import numpy as np
from scipy.stats import norm
from pyquaidsce.model import DemandData
from pyquaidsce.params import unpack
from pilot.b1_fourteen.export import workbook


class Checks(unittest.TestCase):
    def test_historical_warm_start_preserves_every_slope_and_mean_alpha(self):
        r=np.random.default_rng(1410); n,m=36,12
        names=['household_size','mean_ln_expenditure','mean_centered_ln_expenditure_squared',
            'mean_history_1_centered_ln_expenditure_squared','mean_history_2_centered_ln_expenditure_squared','mean_cf_residual']
        Z=r.normal(0,.15,(n,len(names))); centers=r.normal(size=len(names)); scales=np.exp(r.normal(size=len(names)))
        centers[-1]=0
        lp=r.normal(0,.1,(n,m)); y=r.normal(3,.2,n); cf=r.normal(0,.1,n)
        selection=base.PN+['ln_expenditure']+names+['cf_residual']
        X=np.column_stack([lp,y,Z*scales+centers,cf])
        tau=r.normal(0,.02,(m,len(selection)+1)); k=X@tau[:,:-1].T+tau[:,-1]
        d=DemandData(lp,y,r.dirichlet(np.ones(m)*3,n),np.zeros((n,1)),norm.cdf(k),norm.pdf(k),1.,cf)
        stage=dict(data=d,Z=Z,centers=centers,scales=scales,control_names=names,
            selection_names=selection,tau=tau,selection_index=k,regimes=np.repeat(np.arange(3),12),
            additive_columns=[5],mundlak_names=names[1:],rf_names=['constant','ln_income_centered'],
            specification={'history':True})
        oldcore=base.core_for(stage); th=r.normal(0,.002,oldcore.spec.n_free)
        th[oldcore.base_slices['alpha']]=1/m
        fit=type('Fit',(),{'theta':th})()
        newstage=copy.deepcopy(stage); XX=trim_controls(newstage); newcore=base.core_for(newstage)
        newtheta=warm_start(newcore,newstage,fit,stage)
        self.assertEqual(oldcore.spec.n_free-newcore.spec.n_free,33)
        np.testing.assert_array_equal(XX[:,:13],X[:,:13])
        self.assertTrue('mean_ln_expenditure' in newstage['control_names'])
        self.assertFalse(any(is_square_mean(x) for x in newstage['control_names']))
        for code in range(3):
            nt,oe=oldcore.unpack(th,code); on=unpack(nt,oldcore.native)
            nt,ne=newcore.unpack(newtheta,code); nn=unpack(nt,newcore.native)
            for field in ('beta','gamma','lam','delta','cfcoef'):
                np.testing.assert_array_equal(getattr(on,field),getattr(nn,field))
            oa=on.alpha+Z.mean(0)[~oldcore.additive_columns]@oe[~oldcore.additive_columns]
            na=nn.alpha+newstage['Z'].mean(0)[~newcore.additive_columns]@ne[~newcore.additive_columns]
            np.testing.assert_allclose(oa,na,atol=2e-16)

    def test_workbook_undefined_values_and_dynamic_removed_control_metadata(self):
        results=json.loads((base.OUT/'results.json').read_text())['runs']
        results[0]['elasticities']['overall']['marshallian'][2][3]=None
        results[0]['elasticities']['overall']['expenditure'][2]=None
        for result in results:
            if result['specification']['panel']:
                for key in ('control_names','mundlak_names'):
                    result[key]=[x for x in result[key] if not is_square_mean(x)]
        with tempfile.TemporaryDirectory() as td:
            path=workbook(results,Path(td)/'test.xlsx')
            import openpyxl
            wb=openpyxl.load_workbook(path,data_only=True)
            self.assertEqual(wb['CS_All_common']['E10'].value,'نامعتبر')
            self.assertEqual(wb['CS_All_common']['N10'].value,'نامعتبر')
            self.assertIn('میانگین مربع لگاریتم مخارج حذف شده',wb['Panel_B_history']['A2'].value)
            self.assertTrue(all(ws.freeze_panes is None for ws in wb))


if __name__=='__main__': unittest.main()
