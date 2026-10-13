"""Rebuild the frozen priced CS samples, without estimating any model.

python -m pilot.cs_summary_comparison.prepare --inputs intermediate/pilot_inputs
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pilot.b1_fourteen import run as base
from pilot.common.prices import construct, digest


def sample_hash(frame):
    keys = '\n'.join(frame.panel_id.astype(str)+':'+frame.year.astype(str))
    return hashlib.sha256(keys.encode()).hexdigest()


def prepare(inputs, work):
    work.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((base.OUT/'manifest.json').read_text())
    for name, expected in base.SOURCE_HASHES.items():
        assert digest(inputs/name) == expected, name
    if all((work/f'sample_{s}.pkl').exists() for s in ('All', 'B')):
        for sample in ('All', 'B'):
            frame = pd.read_pickle(work/f'sample_{sample}.pkl')
            assert sample_hash(frame) == manifest['sample'][sample]['sample_hash']
        return
    frames = [pd.read_csv(inputs/name, dtype={'address_raw': str, 'head_education': str})
              for name in ('all_clean_1392_1403.csv.gz', 'panelB_clean_1392_1403.csv.zip')]
    mapping = pd.read_excel(inputs/'final_commodity_mapping_107.xlsx')
    mapping = mapping[mapping.p_var != 'p_11_4'].reset_index(drop=True)
    all_frame, panel, audit = construct(*frames, mapping, return_all=True)
    original = json.loads((base.REPO/'pilot/initial/results.json').read_text())['prices']
    np.testing.assert_allclose(audit['price_centers'], original['price_centers'], rtol=0, atol=2e-12)
    np.testing.assert_allclose([v['fixed_weight'] for v in audit['item_weights']],
                              [v['fixed_weight'] for v in original['item_weights']], rtol=0, atol=2e-12)
    assert audit['quality_regressions'] == original['quality_regressions']
    (work/'price_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2))
    for sample, frame in [('All', all_frame), ('B', panel)]:
        frame = frame.sort_values(['panel_id', 'year']).reset_index(drop=True)
        frame['exp_analysis_106'] = frame.exp_system_107-frame.exp_11_4
        for group in range(1, 13):
            columns = mapping.loc[mapping.group_id == group, 'exp_var']
            frame[f'w_{group}'] = frame[columns].sum(axis=1, min_count=len(columns))/frame.exp_analysis_106
        good = ((frame.food_matched == 1) & np.isfinite(frame.exp_analysis_106) & (frame.exp_analysis_106 > 0)
                & np.isfinite(frame.total_income_real) & (frame.total_income_real > 0)
                & frame.head_sex.isin(['Male', 'Female']) & np.isfinite(frame.head_age) & (frame.household_size > 0)
                & np.isfinite(frame.weight) & (frame.weight > 0)
                & np.isfinite(frame[base.PN]).all(axis=1)
                & np.isfinite(frame[[f'w_{g}' for g in range(1, 13)]]).all(axis=1))
        if sample == 'B':
            good = good.groupby(frame.panel_id).transform('all')
        frame = frame.loc[good].copy().reset_index(drop=True)
        frame['cohort'] = frame.groupby('panel_id').year.transform('min')
        frame['ln_exp'] = np.log(frame.exp_analysis_106)
        columns = ['panel_id', 'address_raw', 'year', 'cohort', 'urban_rural', 'region', 'season_number',
                   'head_age', 'head_sex', 'head_marital_status', 'household_size', 'weight',
                   'total_income_real', 'exp_analysis_106', 'ln_exp']+base.PN+[f'w_{g}' for g in range(1, 13)]
        frame = frame[columns]
        assert sample_hash(frame) == manifest['sample'][sample]['sample_hash']
        assert len(frame) == manifest['sample'][sample]['rows']
        frame.to_pickle(work/f'sample_{sample}.pkl')
        print('SAVED', sample, len(frame), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, default=base.INPUT)
    parser.add_argument('--work', type=Path, default=base.INPUT/'cs_summary_comparison')
    args = parser.parse_args()
    prepare(args.inputs, args.work)
