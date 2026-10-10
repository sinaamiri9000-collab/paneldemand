"""Change evaluation points only: no RF, Probit, IFGNLS or bootstrap fitting."""
if __package__ in (None, ''):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import argparse
import hashlib
import json
import pickle
from pathlib import Path
import numpy as np
from pilot.common.specification_core import SpecificationCore
from pilot.specification_suite.specification_suite import inference_design, GROUPS
from pilot.specification_followup.direct_elasticities import DirectReference, micro_direct, finite_difference_audit
from pilot.common.frame_results import unpack_e

OUT=Path(__file__).parent
MODELS=('B1_no_season_means','B2_no_season_means')


def one_point(core,fit,stage,design,rows):
    ref=DirectReference(core,fit,stage,design,rows=rows)
    indices=np.flatnonzero(rows)
    record={'observations':len(indices),'households':len(np.unique(stage['panel_ids'][rows])),
            'year_counts':dict(zip(*np.unique(stage['year'][rows],return_counts=True))),
            'cohort_counts':dict(zip(*np.unique(stage['cohort'][rows],return_counts=True))),
            'reference_inputs':{'log_prices':core.data.lnp[rows].mean(0),'log_expenditure':float(core.data.lnexp[rows].mean()),
                'scaled_controls':core.Z[rows].mean(0),'raw_controls':(core.Z[rows]*stage['scales']+stage['centers']).mean(0),
                'cf_residual':float(core.data.control_function[rows].mean()),
                'probit_index':stage['selection_index'][rows].mean(0)}}
    record['elasticities']=unpack_e(ref.evaluate(ref.point),12)
    record['reference_diagnostics']=ref.point_diagnostics()
    # Independent finite differences at this actual representative point.
    theta,tau,k=ref.inputs(ref.point)
    local_stage={'selection_index':k,'tau':tau,'layout':stage['layout']}
    record['derivative_validation']=finite_difference_audit(ref.core,fit,local_stage,np.array([0]))
    if record['derivative_validation']['max_absolute_error']>1e-7:raise RuntimeError('Reference derivative validation failed')
    sub=SpecificationCore(core.data.subset(rows),core.Z[rows],stage['additive_columns'])
    micro_stage={'selection_index':stage['selection_index'][rows],'tau':stage['tau'],'layout':stage['layout']}
    record['micro']=micro_direct(sub,fit,micro_stage)
    return record


def range_summary(records,kind):
    values=np.array([r['elasticities'][kind] for r in records.values()])
    if kind=='marshallian':values=np.diagonal(values,axis1=1,axis2=2)
    keys=list(records)
    return {'minimum':values.min(0),'maximum':values.max(0),'range':np.ptp(values,axis=0),
            'minimum_at':[keys[i] for i in values.argmin(0)],'maximum_at':[keys[i] for i in values.argmax(0)]}


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);args=p.parse_args()
    previous=json.loads((OUT.parent/'specification_followup/results.json').read_text())
    output={'version':'fixed-parameter-reference-points-v1','sample':previous['sample'],'groups':GROUPS,
            'pyquaidsce_commit':previous['pyquaidsce_commit'],'priced_panel_sha256':previous['priced_panel_sha256'],
            'method':'same complete fitted parameter vectors, RF and Probits; original scales/centers/a0 and household means over all three waves; unweighted arithmetic log-input reference means; conditional current partials with means/CF fixed',
            'inference':'descriptive point estimates only; no new SE, significance test or refit', 'models':{}}
    assert hashlib.sha256((args.inputs/'priced_panel_106.parquet').read_bytes()).hexdigest()==output['priced_panel_sha256']
    for name in MODELS:
        stage_path=args.inputs/f'suite_{name}_stage.pkl';fit_path=args.inputs/f'suite_{name}_point.pkl'
        stage=pickle.load(stage_path.open('rb'));fit=pickle.load(fit_path.open('rb'))
        assert fit.converged
        core=SpecificationCore(stage['data'],stage['Z'],stage['additive_columns']);design=inference_design(stage)
        frozen=fit.theta.copy();tau=stage['tau'].copy();Z=stage['Z'].copy()
        assert len(set(zip(stage['panel_ids'],stage['year'])))==137814
        assert np.all(stage['panel_ids'].reshape(-1,3)==stage['panel_ids'].reshape(-1,3)[:,:1])
        assert np.array_equal(np.unique(stage['year']),np.arange(1392,1404))
        assert len(np.unique(stage['cohort']))==8
        result={'source_point_sha256':hashlib.sha256(fit_path.read_bytes()).hexdigest(),
                'source_stage_sha256':hashlib.sha256(stage_path.read_bytes()).hexdigest(),
                'theta_sha256':hashlib.sha256(frozen.tobytes()).hexdigest(),
                'coefficients':previous['models'][name]['coefficients'],'control_names':stage['control_names'],
                'global':{},'years':{},'cohorts':{}}
        result['global']=one_point(core,fit,stage,design,np.ones(core.data.nobs,bool))
        old=previous['models'][name]['direct_elasticities']
        for kind,values in old['point'].items():np.testing.assert_allclose(result['global']['elasticities'][kind],values,atol=2e-12,rtol=2e-12)
        for kind in ('individual_expenditure','individual_marshallian'):
            np.testing.assert_allclose(result['global']['micro'][kind]['median'],old['micro'][kind]['median'],atol=2e-12,rtol=2e-12)
        for kind,column in [('years','year'),('cohorts','cohort')]:
            for value in np.unique(stage[column]):
                print(name,kind,int(value),flush=True)
                result[kind][str(value)]=one_point(core,fit,stage,design,stage[column]==value)
            assert sum(x['observations'] for x in result[kind].values())==137814
        np.testing.assert_array_equal(fit.theta,frozen);np.testing.assert_array_equal(stage['tau'],tau);np.testing.assert_array_equal(stage['Z'],Z)
        result['ranges']={kind:{metric:range_summary(result[kind],metric) for metric in ('expenditure','marshallian')} for kind in ('years','cohorts')}
        output['models'][name]=result
    # Convert integer dictionary keys (count tables) and NumPy values before strict JSON output.
    def clean(v):
        if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
        if isinstance(v,(list,tuple)):return [clean(x) for x in v]
        if isinstance(v,np.ndarray):return clean(v.tolist())
        if isinstance(v,np.generic):return v.item()
        return v
    (OUT/'results.json').write_text(json.dumps(clean(output),ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    print('DONE',OUT/'results.json',flush=True)

if __name__=='__main__':main()
