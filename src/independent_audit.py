"""Independent read-only checks; never changes the collector's data."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import pandas as pd
import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = args.root
    checks, counts, households = [], [], {}

    def record(name, status, **details):
        checks.append(dict(check=name, status=status, **details))

    files = [p for p in root.rglob('*.parquet') if '.venv' not in p.parts]
    for year in range(1390, 1404):
        candidates = [p for p in files if p.name == 'household.parquet' and str(year) in p.parts]
        if len(candidates) != 1:
            record(f'year_{year}_household', 'blocked', n_candidates=len(candidates))
            continue
        base = candidates[0].parent
        frames = {}
        for name in ['household', 'members', 'food', 'income_wage',
                     'income_self_employed', 'income_other', 'housing']:
            p = base / f'{name}.parquet'
            if not p.exists():
                record(f'{year}_{name}_exists', 'fail')
                continue
            try:
                df = pd.read_parquet(p)
                frames[name] = df
                record(f'{year}_{name}_readable', 'pass', rows=len(df), columns=len(df.columns),
                       sha256=sha256(p))
                required = {'Year', 'ID'}
                if name == 'food':
                    required |= {'Commodity_Code', 'Amount', 'Price', 'Expenditure', 'Provision_Method'}
                if name == 'members':
                    required |= {'Member_Number', 'Relationship', 'Sex', 'Age', 'Education_Level',
                                 'Activity_Status', 'Marital_Status'}
                missing = sorted(required - set(df.columns))
                record(f'{year}_{name}_required_columns', 'fail' if missing else 'pass', missing=missing)
                if 'Year' in df:
                    bad = int(df['Year'].isna().sum() + df['Year'].dropna().ne(year).sum())
                    record(f'{year}_{name}_year_values', 'fail' if bad else 'pass', n_bad=bad)
            except Exception as e:
                record(f'{year}_{name}_readable', 'fail', error=str(e))
        if 'household' not in frames:
            continue
        hh = frames['household']
        ids = set(hh['ID'].dropna().astype(str))
        households[year] = ids
        dup = int(hh.duplicated(['Year', 'ID']).sum())
        record(f'{year}_household_unique', 'fail' if dup else 'pass', duplicates=dup)
        summary = dict(Year=year, households=len(ids), household_rows=len(hh))
        for name, df in frames.items():
            summary[name + '_rows'] = len(df)
            if 'ID' in df:
                unmatched = set(df['ID'].dropna().astype(str)) - ids
                record(f'{year}_{name}_foreign_key', 'fail' if unmatched else 'pass',
                       n_unmatched_ids=len(unmatched))
        if 'members' in frames:
            mem = frames['members']
            dup = int(mem.duplicated(['Year', 'ID', 'Member_Number']).sum())
            record(f'{year}_members_unique', 'fail' if dup else 'pass', duplicates=dup)
        if 'food' in frames:
            food = frames['food']
            summary['food_unique_codes'] = int(food['Commodity_Code'].nunique())
            for col in ['Amount', 'Price', 'Expenditure']:
                val = pd.to_numeric(food[col], errors='coerce')
                summary[col + '_valid_records'] = int((np.isfinite(val) & val.gt(0)).sum())
        counts.append(summary)
        checksum_file = base / 'checksums.sha256'
        if checksum_file.exists():
            bad, checked = [], 0
            for line in checksum_file.read_text().splitlines():
                match = re.match(r'^([0-9a-fA-F]{64})\s+\*?(.+)$', line)
                if not match:
                    continue
                p = base / match.group(2)
                checked += 1
                if not p.exists() or sha256(p).lower() != match.group(1).lower():
                    bad.append(match.group(2))
            record(f'{year}_checksums', 'fail' if bad or not checked else 'pass', checked=checked, bad=bad)
        else:
            record(f'{year}_checksums', 'fail', error='missing')

    # Independent ID overlap calculations. No assumption about family identity.
    overlap = []
    history = {}
    for year, ids in households.items():
        for household_id in ids:
            history.setdefault(household_id, []).append(year)
        for lag in [1, 2]:
            if year + lag in households:
                later = households[year + lag]
                n = len(ids & later)
                overlap.append(dict(Year=year, lag=lag, n_t=len(ids), n_later=len(later), n_common=n,
                                    rate_t=n / len(ids) if ids else None,
                                    rate_later=n / len(later) if later else None))
    distribution = {}
    for years in history.values():
        distribution[len(years)] = distribution.get(len(years), 0) + 1
    record('coverage_all_years', 'pass' if len(households) == 14 else 'blocked',
           years=sorted(households), n_years=len(households))
    record('id_reuse_over_three_years', 'warning' if any(n > 3 for n in distribution) else 'pass',
           counts=distribution)

    # Combined row counts must match annual exports, with complete year coverage.
    for name in ['household', 'members', 'food']:
        candidates = [p for p in files if p.name == f'{name}_1390_1403.parquet']
        if len(candidates) != 1:
            record(f'combined_{name}', 'blocked', n_candidates=len(candidates))
            continue
        try:
            df = pd.read_parquet(candidates[0], columns=['Year'])
            actual = {int(y): int(n) for y, n in df['Year'].value_counts().items()}
            expected = {r['Year']: r[name + '_rows'] for r in counts if name + '_rows' in r}
            record(f'combined_{name}_counts', 'pass' if actual == expected else 'fail',
                   expected=expected, actual=actual)
        except Exception as e:
            record(f'combined_{name}_counts', 'fail', error=str(e))

    args.output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(counts).to_csv(args.output / 'independent_yearly_counts.csv', index=False)
    pd.DataFrame(overlap).to_csv(args.output / 'independent_panel_overlap.csv', index=False)
    result = dict(checks=checks, id_presence_distribution=distribution,
                  note='Only existence and calculations backed by available files are verified. '
                       'Raw-to-standard mapping and destination readback require separate evidence.')
    (args.output / 'independent_checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    statuses = {}
    for c in checks:
        statuses[c['status']] = statuses.get(c['status'], 0) + 1
    print(json.dumps(dict(statuses=statuses, available_years=sorted(households)), ensure_ascii=False))


if __name__ == '__main__':
    main()
