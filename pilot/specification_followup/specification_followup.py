"""Prespecified matched Pooled and season-mean follow-ups; direct S&Y derivatives.

Independent point fits may run concurrently with --threads 1. The shared
inference lock bounds memory. Previous fitted models are never re-estimated.
Private stages and household influence arrays stay in intermediate/pilot_inputs.

python pilot/specification_followup/specification_followup.py --inputs intermediate/pilot_inputs \
    --model B1_no_season_means --threads 1
python pilot/specification_followup/specification_followup.py --inputs intermediate/pilot_inputs \
    --direct-old B0 B1 B2 --threads 3
python pilot/specification_followup/specification_followup.py --inputs intermediate/pilot_inputs --assemble
"""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
import fcntl
import hashlib
import json
import pickle
import time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm
from threadpoolctl import threadpool_limits
from pilot.specification_suite import specification_suite as suite
from pilot.common.specification_core import SpecificationCore
from pilot.specification_followup.direct_elasticities import DirectReference, micro_direct, finite_difference_audit
from pilot.common.staged_inference import stacked_covariance
from pilot.common.frame_results import unpack_e, holm

VERSION = 'specification-followup-v1'
NEW = ('P0_matched', 'B1_no_season_means', 'B2_no_season_means')
OLD = ('B0', 'B1', 'B2')
OUT = Path(__file__).parent


def prepare(root, b, name):
    z, means, rf_means, changes = suite.designs(b, 'B0')
    if name == 'P0_matched':
        b0 = pickle.load(open(root/'suite_B0_stage.pkl', 'rb'))
        z['mean_head_age'] = b.head_age.groupby(b.panel_id).transform('mean')
        empty = pd.DataFrame(index=b.index)
        stage = suite.make_stage(b, name, z, empty, empty, rf_stage=b0,
                                 mean_cf=False, mean_expenditure=False)
        stage['rf_shared_with'] = 'B0'
        np.testing.assert_array_equal(stage['Xrf'], b0['Xrf'])
        np.testing.assert_array_equal(stage['data'].control_function, b0['data'].control_function)
        a = stage['control_names'].index('mean_head_age'); aa = b0['control_names'].index('mean_head_age')
        np.testing.assert_array_equal(stage['Z'][:,a], b0['Z'][:,aa])
        assert stage['first_stage'] == b0['first_stage']
        stage['common_rf_age_checks'] = {'rf_matrix_identical':True, 'cf_identical':True,
             'rf_coefficients_identical':True, 'age_column_identical':True}
        return stage, 'B0'
    base = name[:2]; assert base in ('B1', 'B2')
    drop = [f'mean_season_{s}' for s in (2,3,4)]
    means = means.drop(columns=drop); rf_means = rf_means.drop(columns=drop)
    stage = suite.make_stage(b, name, z, means, rf_means,
                             mean_cf=True, mean_expenditure=base == 'B2')
    assert not set(drop).intersection(stage['control_names']+stage['rf_names'])
    assert all(f'season_{s}' in stage['control_names'] for s in (2,3,4))
    stage['removed_season_means_all_stages'] = drop
    stage['merge_season_mean_start'] = True
    return stage, base


def direct_path(root, name): return root/f'follow_{name}_direct.npz'


def store_direct(root, name, core, fit, stage, design, covariance, IF):
    started = time.time(); print(name, 'DIRECT reference and multistage uncertainty', flush=True)
    ref = DirectReference(core, fit, stage, design)
    point = ref.evaluate(ref.point); J = ref.jacobian()
    if not np.isfinite(J).all(): raise RuntimeError(f'{name}: nonfinite direct elasticity gradient')
    se = np.sqrt(np.maximum(np.einsum('ij,ij->i', J@covariance, J), 0))
    EIF = IF@J[:156].T
    ids = [0, core.base_slices['gamma'].start, core.spec.nbase,
           core.spec.n_free+design.cf_pos, len(ref.point)-1]
    if design.mean_z >= 0: ids += [core.spec.nbase+design.mean_z*11]
    checks = []
    for j in ids:
        h = 3e-6*max(1.,abs(ref.point[j])); e = np.zeros_like(ref.point); e[j] = h
        fd = (ref.evaluate(ref.point+e)-ref.evaluate(ref.point-e))/(2*h)
        checks.append(float(np.abs(fd-J[:,j]).max()))
    ref.evaluate(ref.point)
    diag = ref.point_diagnostics()
    rows = np.unique(np.linspace(0,core.data.nobs-1,120).astype(int))
    audit = finite_difference_audit(core, fit, stage, rows)
    if audit['max_error_scaled_by_one_plus_derivative'] > 1e-7:
        raise RuntimeError(f'{name}: direct derivative numeric validation failed: {audit}')
    print(name, 'DIRECT all observation derivatives', flush=True)
    micro = micro_direct(core, fit, stage)
    summary = {'model':name, 'definition':'direct log derivative of actual fitted S&Y conditional mean; household means and CF inputs fixed for current partials',
               'reference':'arithmetic mean log prices/log expenditure and raw controls; Phi/PDF at mean Probit index; actual positive fitted share denominator',
               'point':unpack_e(point,12), 'standard_errors':unpack_e(se,12),
               'reference_diagnostics':diag, 'micro':micro,
               'validation':{'current_input_numeric_derivative':audit,
                    'parameter_delta_gradient_max_step_difference':max(checks)},
               'inference':'full WLS/12-Probit/IFGNLS including Sigma multistage panel-cluster sandwich; empirical reference inputs/scales and generated prices held fixed; descriptive micro and quantity summaries have no CI',
               'hicksian_qualification':'Slutsky diagnostic using fitted shares; raw S&Y not exactly adding-up; not established compensated utility demand',
               'seconds':time.time()-started}
    serial = json.dumps(summary, ensure_ascii=False, default=lambda v:v.tolist() if isinstance(v,np.ndarray) else v.item())
    temporary = direct_path(root,name).with_suffix('.part.npz')
    np.savez_compressed(temporary, theta=fit.theta, point=point,
                        se=se, influence=EIF, summary=serial)
    os.replace(temporary,direct_path(root,name))
    print(name, 'DIRECT done', round(summary['seconds'],1), flush=True)


def direct_existing(root, name):
    fit = pickle.load(open(root/f'suite_{name}_point.pkl','rb'))
    if direct_path(root,name).exists():
        np.testing.assert_array_equal(np.load(direct_path(root,name))['theta'],fit.theta)
        print(name,'DIRECT cached',flush=True); return
    stage = pickle.load(open(root/f'suite_{name}_stage.pkl','rb'))
    core = SpecificationCore(stage['data'],stage['Z'],stage['additive_columns'])
    design = suite.inference_design(stage)
    def log(msg): print(name,msg,flush=True)
    # Recover household parameter influences from unchanged old estimates.
    # Do not call a point estimator, RF fitter or Probit fitter here.
    with open(root/'suite_inference.lock','a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cov, conditional, diag, IF = stacked_covariance(core,fit,stage,design,
                                                       log=log,return_influence=True)
        old = np.load(root/f'suite_{name}_inference.npz')
        np.testing.assert_array_equal(old['theta'],fit.theta)
        np.testing.assert_allclose(cov,old['covariance'],rtol=2e-7,atol=2e-10)
        store_direct(root,name,core,fit,stage,design,cov,IF)


def paired(root, before, after, direct=False):
    if direct:
        aa = np.load(direct_path(root,before)); bb = np.load(direct_path(root,after))
        ea,eb,ia,ib = aa['point'],bb['point'],aa['influence'],bb['influence']
    else:
        aa = np.load(root/f'suite_{before}_inference.npz'); bb = np.load(root/f'suite_{after}_inference.npz')
        ea,eb,ia,ib = aa['elasticities'],bb['elasticities'],aa['elasticity_influence'],bb['elasticity_influence']
    diff = eb[:156]-ea[:156]; influence = ib-ia; H = len(influence)
    se = np.sqrt((influence*influence).sum(0)*H/(H-1))
    p = 2*norm.sf(np.divide(np.abs(diff),se,out=np.full_like(se,np.inf),where=se>0))
    main = np.r_[np.arange(12),12+np.arange(12)*13]
    return {'before':before,'after':after,'definition':'direct fitted mean reference' if direct else 'native pyquaidsce at-means convention',
            'difference_expenditure':diff[:12], 'difference_marshallian':diff[12:].reshape(12,12),
            'standard_error_expenditure':se[:12], 'standard_error_marshallian':se[12:].reshape(12,12),
            'ci95_lower_expenditure':(diff-1.96*se)[:12], 'ci95_upper_expenditure':(diff+1.96*se)[:12],
            'ci95_lower_marshallian':(diff-1.96*se)[12:].reshape(12,12),
            'ci95_upper_marshallian':(diff+1.96*se)[12:].reshape(12,12),
            'pvalue_main24':p[main], 'pvalue_main24_holm':holm(p[main]),
            'illustrative_economic_margin':.1,
            'main24_ci95_outside_plus_minus_0_1':np.abs(diff[main])-1.96*se[main]>.1,
            'main24_ci90_inside_plus_minus_0_1':np.abs(diff[main])+norm.ppf(.95)*se[main]<.1,
            'inference':'paired multistage household influences; cross-model correlation included'}


def assemble(root):
    previous = json.loads((Path(__file__).parents[1]/'specification_suite/results.json').read_text())
    models = {}
    for name in NEW:
        path = OUT/f'{name}.json'
        cache = root/f'follow_{name}_result.json'
        if path.exists(): cache.write_text(path.read_text())
        models[name] = json.loads(cache.read_text())
    models.update({name:previous['models'][name] for name in OLD})
    for name, result in models.items():
        direct_saved = np.load(direct_path(root,name))
        fit = pickle.load(open(root/f'suite_{name}_point.pkl','rb'))
        np.testing.assert_array_equal(direct_saved['theta'],fit.theta)
        result['direct_elasticities'] = json.loads(str(direct_saved['summary']))
        stage = pickle.load(open(root/f'suite_{name}_stage.pkl','rb'))
        result['fixed_a0'] = stage['data'].a0
        result['direct_elasticities']['reference_diagnostics'].update({
            'mean_log_prices':stage['data'].lnp.mean(0),
            'mean_log_expenditure':float(stage['data'].lnexp.mean()),
            'mean_scaled_controls':stage['Z'].mean(0),
            'mean_cf_residual':float(stage['data'].control_function.mean()),
            'fixed_a0':stage['data'].a0})
        assert result['sample_hash']==previous['sample']['sample_hash']
    output = {'version':VERSION,'sample':previous['sample'],'groups':suite.GROUPS,
              'source_input_hashes':previous['source_input_hashes'],
              'priced_panel_sha256':hashlib.sha256((root/'priced_panel_106.parquet').read_bytes()).hexdigest(),
              'pyquaidsce_commit':previous['pyquaidsce_commit'],
              'previous_report':'pilot/specification_suite/report.md',
              'household_change_counts':previous['household_change_counts'],'models':models,
              'comparisons_native':{},'comparisons_direct':{}}
    assert output['priced_panel_sha256']==previous['priced_panel_sha256']
    for before,after in [('P0_matched','B0'),('B1','B2'),('B1','B1_no_season_means'),
                         ('B2','B2_no_season_means'),('B1_no_season_means','B2_no_season_means')]:
        key = f'{after}_minus_{before}'
        output['comparisons_native'][key] = paired(root,before,after)
        output['comparisons_direct'][key] = paired(root,before,after,direct=True)
    p0 = pickle.load(open(root/'suite_P0_matched_stage.pkl','rb'))
    output['matched_pooled_checks'] = p0['common_rf_age_checks']
    output['matched_pooled_qualification'] = 'Pooled participation/demand sharing mean age and the complete B0 CRE expenditure reduced form; not a fully pooled three-stage estimator'
    suite.dump(OUT/'results.json',output)
    # Compact single results file after successful assembly.
    (OUT/'results.json').write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'),
                              default=lambda v:v.tolist() if isinstance(v,np.ndarray) else v.item())+'\n')
    for name in NEW: (OUT/f'{name}.json').unlink(missing_ok=True)
    print('ASSEMBLED', OUT/'results.json',flush=True)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--model',choices=NEW); p.add_argument('--direct-old',nargs='+',choices=OLD)
    p.add_argument('--assemble',action='store_true'); p.add_argument('--threads',type=int,default=1)
    args = p.parse_args(); root = args.inputs; OUT.mkdir(exist_ok=True)
    os.environ['PILOT_BLAS_THREADS'] = str(args.threads)
    with threadpool_limits(limits=args.threads):
        if args.assemble: assemble(root); return
        if args.direct_old:
            for name in args.direct_old: direct_existing(root,name)
            return
        if not args.model: p.error('choose --model, --direct-old, or --assemble')
        b, oldstage, baseline = suite.load_sample(root)
        print('PREPARE',args.model,flush=True)
        stage,start = prepare(root,b,args.model)
        result = suite.fit_model(root,b,oldstage,args.model,baseline,OUT,
                     prepared_stage=stage,start_model=start,
                     influence_consumer=lambda *values:store_direct(root,args.model,*values))
        if not direct_path(root,args.model).exists(): direct_existing(root,args.model)
        if args.model=='P0_matched':
            result['common_rf_age_checks']=stage['common_rf_age_checks']
            result['specification']['common_reduced_form_with']='B0'
            result['specification']['qualification']='Pooled participation/demand with shared CRE reduced form and mean-age control'
        else: result['specification']['removed_season_means_all_stages']=stage['removed_season_means_all_stages']
        suite.dump(OUT/f'{args.model}.json',result)
        print('DONE',args.model,flush=True)


if __name__=='__main__': main()
