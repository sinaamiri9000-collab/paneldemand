# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import unittest
from types import SimpleNamespace
import numpy as np
from pilot.cohort_annual_stability.stability_path import score_family


class PathTests(unittest.TestCase):
    def test_block_scores_eliminate_common_null_not_other_restricted_blocks(self):
        rng=np.random.default_rng(721); n=600
        X=np.column_stack([np.ones(n),rng.normal(size=n)])
        added=rng.normal(size=(n,4)); added[:,1] += .8*added[:,0]
        full=np.column_stack([X,added])
        y=X@np.array([.2,.4])+.1*added[:,0]+rng.normal(size=n)*(1+abs(X[:,1]))
        u=y-X@np.linalg.lstsq(X,y,rcond=None)[0]
        scores=(full*u[:,None]).reshape(-1,3,6).sum(1)
        core=SimpleNamespace(common_base=2,slope_width=2,blocks=('beta','lambda'),
            base_slices={'beta':slice(0,1),'lambda':slice(1,2)},
            spec=SimpleNamespace(nbase=6,n_free=6,ncontrast=2))
        actual=score_family(core,full.T@full,scores,full.T@u,float(u@u))
        for name,ids in [('beta',[0,2]),('lambda',[1,3]),('all',[0,1,2,3])]:
            z=added[:,ids]; zr=z-X@np.linalg.lstsq(X,z,rcond=None)[0]
            s=(zr*u[:,None]).reshape(-1,3,len(ids)).sum(1)
            m=s.sum(0); expected=m@np.linalg.solve(s.T@s,m)*199/200
            self.assertAlmostEqual(actual['tests'][name]['statistic'],expected,places=8)
            self.assertEqual(actual['tests'][name]['df'],len(ids))

    def test_annual_levels_rank_and_year_means_spanned_by_entry_cohort(self):
        cohorts=np.repeat([1392,1393,1394,1397,1398,1399,1400,1401],9)
        years=cohorts+np.tile([0,1,2],len(cohorts)//3)
        C=np.column_stack([np.ones(len(years))]+[(cohorts==c) for c in np.unique(cohorts)[1:]])
        T=np.column_stack([(years==y) for y in np.unique(years)[1:]])
        self.assertEqual(np.linalg.matrix_rank(np.column_stack([C,T])),C.shape[1]+T.shape[1]-1)
        keep=[j for j,y in enumerate(np.unique(years)[1:]) if y!=1397]
        good=np.column_stack([C,T[:,keep]])
        self.assertEqual(np.linalg.matrix_rank(good),good.shape[1])
        means=T.reshape(-1,3,T.shape[1]).mean(1).repeat(3,axis=0)
        np.testing.assert_allclose(C@np.linalg.lstsq(C,means,rcond=None)[0],means,atol=1e-14)


if __name__=='__main__': unittest.main()
