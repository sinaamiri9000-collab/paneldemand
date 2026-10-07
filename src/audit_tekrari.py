"""Direct-Access audit of Tekrari and original/substitute response fields."""
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'intermediate/three_wave_validation'
PRIVATE = WORK / 'private'
AUDIT = ROOT / 'audit'
YEARS = list(range(1392, 1404))
COHORTS = [(1392,1393,1394),(1393,1394,1395),(1394,1395,1396),
           (1397,1398,1399),(1398,1399,1400),(1399,1400,1401),
           (1400,1401,1402),(1401,1402,1403)]
FRAME = lambda y: 'Frame_1392_1396' if y <= 1396 else 'Frame_1397_1403'
ITEMS = {
    **{y: (19, 20) for y in range(1392, 1397)},
    **{y: (18, 19) for y in range(1397, 1404)},
}

def s(v):
    if pd.isna(v): return None
    v = str(v).strip()
    return v if v else None

def code(v): return s(v) or '<MISSING>'

def response_state(t, j):
    t, j = s(t), s(j)
    if t == '1':
        return 'Original_responded' if j != '1' else 'Original_responded_substitute_also_marked_yes'
    if t == '2' and j == '1': return 'Original_nonresponse_substitute_responded'
    if t == '2' and j == '2': return 'Original_nonresponse_substitute_nonresponse'
    if t == '2': return 'Original_nonresponse_substitute_status_missing'
    if t is None and j == '1': return 'Substitute_responded_original_status_missing'
    if t is None and j == '2': return 'Substitute_nonresponse_original_status_missing'
    return 'Both_statuses_missing_or_unrecognized'

def respondent_kind(t, j):
    t, j = s(t), s(j)
    if t == '1': return 'Original'
    if j == '1': return 'Substitute'
    if t == '2' and j == '2': return 'No_Completed_Interview'
    return 'Ambiguous'

def main():
    schema = pd.read_csv(WORK / 'raw_access_schema_1392_1403.csv', dtype='string')
    annual, codebook, cross, tekrari = {}, [], [], []
    for y in YEARS:
        d = pd.read_parquet(PRIVATE / f'raw_household_{y}.parquet').copy()
        for col in ('Takmil', 'Jaygozin', 'Tekrari'):
            if col not in d: d[col] = pd.NA
        d['Address_Raw'] = d['Address_Raw'].astype('string')
        d['Urban_Rural'] = np.where(d['Raw_Table'].astype('string').str.startswith('U'), 'Urban', 'Rural')
        d['Takmil_Code'] = d.Takmil.map(code)
        d['Jaygozin_Code'] = d.Jaygozin.map(code)
        d['Tekrari_Code'] = d.Tekrari.map(code)
        d['Response_State'] = [response_state(t, j) for t, j in zip(d.Takmil, d.Jaygozin)]
        d['Respondent_Kind'] = [respondent_kind(t, j) for t, j in zip(d.Takmil, d.Jaygozin)]
        annual[y] = d
        t_item, j_item = ITEMS[y]
        doc = next((p for p in PRIVATE.glob(f'doc_{y}_*.txt') if 'پرسشنامه' in p.name or 'Questionnaire' in p.name), None)
        for var, field, q, farsi in [
            ('Takmil', 'Takmil_Code', t_item, 'آیا این پرسشنامه برای خانوار اصلی تکمیل شده است؟'),
            ('Jaygozin', 'Jaygozin_Code', j_item, 'آیا این پرسشنامه برای خانوار جایگزین تکمیل شده است؟'),
        ]:
            g = d.groupby([field, 'Urban_Rural'], dropna=False).size()
            totals = d[field].value_counts(dropna=False).to_dict()
            for val, n in totals.items():
                val = str(val)
                codebook.append(dict(Year=y, Frame=FRAME(y), Variable=var, Raw_Code='' if val == '<MISSING>' else val,
                    Count=int(n), Urban_Count=int(g.get((val, 'Urban'), 0)), Rural_Count=int(g.get((val, 'Rural'), 0)),
                    Missing=(val == '<MISSING>'), Questionnaire_Item=f'Q{q}', Questionnaire_Text=farsi,
                    Document=doc.name if doc else 'Questionnaire text unavailable',
                    Meaning='1 = بله؛ 2 = خیر (طبق پرسشنامه همان سال)' if val in ('1','2') else 'کد خالی/ناشناخته؛ معنایی به آن نسبت داده نشده'))
        tek_presence = bool(schema[(schema.Year == str(y)) & (schema.Column.str.casefold() == 'tekrari')].shape[0])
        for val, g in d.groupby('Tekrari_Code', dropna=False):
            tekrari.append(dict(Year=y, Frame=FRAME(y), Record_Type='Code_by_area', Tekrari_Code=val,
                N=len(g), Urban=int(g.Urban_Rural.eq('Urban').sum()), Rural=int(g.Urban_Rural.eq('Rural').sum()),
                Tekrari_Field_In_Access=tek_presence, Missing=(val == '<MISSING>')))
        for (tv, tc), n in d.groupby(['Tekrari_Code','Takmil_Code'], dropna=False).size().items():
            cross.append(dict(Year=y, Frame=FRAME(y), Cross='Tekrari × Takmil', Tekrari_Code=tv, Status_Code=tc, N=int(n)))
        for (tv, jc), n in d.groupby(['Tekrari_Code','Jaygozin_Code'], dropna=False).size().items():
            cross.append(dict(Year=y, Frame=FRAME(y), Cross='Tekrari × Jaygozin', Tekrari_Code=tv, Status_Code=jc, N=int(n)))
        for (tc, jc), n in d.groupby(['Takmil_Code','Jaygozin_Code'], dropna=False).size().items():
            cross.append(dict(Year=y, Frame=FRAME(y), Cross='Takmil × Jaygozin', Tekrari_Code=tc, Status_Code=jc, N=int(n)))
        print(y, 'Tekrari present:', tek_presence, 'counts:', d.Tekrari_Code.value_counts(dropna=False).to_dict(), flush=True)

    # Assess actual raw Address recurrences strictly inside each design frame.
    frame_years = {fr: [y for y in YEARS if FRAME(y) == fr] for fr in sorted({FRAME(y) for y in YEARS})}
    year_sets = {y: set(annual[y].Address_Raw.dropna()) for y in YEARS}
    for y, d in annual.items():
        ys = frame_years[FRAME(y)]
        ix = ys.index(y)
        has_prev, has_next = ix > 0, ix < len(ys)-1
        prev_y, next_y = (ys[ix-1] if has_prev else None), (ys[ix+1] if has_next else None)
        prevset = year_sets[prev_y] if has_prev else set()
        nextset = year_sets[next_y] if has_next else set()
        d['Seen_Previous_Within_Frame'] = d.Address_Raw.isin(prevset) if has_prev else pd.Series(pd.NA, index=d.index, dtype='boolean')
        d['Seen_Next_Within_Frame'] = d.Address_Raw.isin(nextset) if has_next else pd.Series(pd.NA, index=d.index, dtype='boolean')
        d['Seen_Both_Neighbors'] = d.Seen_Previous_Within_Frame.eq(True) & d.Seen_Next_Within_Frame.eq(True)
        d['Address_State'] = 'Interior_Only_Current'
        if has_prev: d.loc[d.Seen_Previous_Within_Frame.eq(True), 'Address_State'] = 'Previous_And_Current'
        if has_next: d.loc[d.Seen_Next_Within_Frame.eq(True), 'Address_State'] = 'Current_And_Next'
        if has_prev and has_next:
            d.loc[d.Seen_Both_Neighbors, 'Address_State'] = 'Previous_Current_Next'
            d.loc[d.Seen_Previous_Within_Frame.eq(False) & d.Seen_Next_Within_Frame.eq(False), 'Address_State'] = 'Only_Current_Year'
        if not has_prev: d['Address_State'] = d.Address_State.replace({'Interior_Only_Current':'Frame_First_Year_Next_Observable','Current_And_Next':'Frame_First_Year_Also_Next'})
        if not has_next: d['Address_State'] = d.Address_State.replace({'Interior_Only_Current':'Frame_Last_Year_Previous_Observable','Previous_And_Current':'Frame_Last_Year_Also_Previous'})
        observed = {}
        for a in d.Address_Raw.dropna().unique():
            present = [q for q in ys if a in year_sets[q]]
            observed[a] = present.index(y) + 1
        d['Observed_Wave'] = pd.Series([observed.get(a, pd.NA) for a in d.Address_Raw], index=d.index, dtype='Int8')
        d['Repeated_Address_Observable'] = d.Seen_Previous_Within_Frame.fillna(False) | d.Seen_Next_Within_Frame.fillna(False)
        tekcol = d.Tekrari_Code
        for tv, g in d.groupby(tekcol, dropna=False):
            n = len(g)
            pd_prev = int(g.Seen_Previous_Within_Frame.eq(True).sum())
            pd_next = int(g.Seen_Next_Within_Frame.eq(True).sum())
            prevden = int(g.Seen_Previous_Within_Frame.notna().sum())
            nextden = int(g.Seen_Next_Within_Frame.notna().sum())
            repeated = int(g.Repeated_Address_Observable.sum())
            repden = int(d.Repeated_Address_Observable.sum())
            tekrari.append(dict(Year=y, Frame=FRAME(y), Record_Type='Address_prediction_by_Tekrari', Tekrari_Code=tv, N=n,
                Previous_Address_N=pd_prev, P_Previous_Given_Tekrari=pd_prev/prevden if prevden else np.nan,
                Next_Address_N=pd_next, P_Next_Given_Tekrari=pd_next/nextden if nextden else np.nan,
                Repeated_Address_N=repeated, P_Tekrari_Given_Repeated_Address=repeated/repden if repden else np.nan,
                Both_Neighbors=int(g.Seen_Both_Neighbors.sum()), Only_Current=int(g.Address_State.eq('Only_Current_Year').sum()),
                Previous_Observable=has_prev, Next_Observable=has_next))
            for st, nst in g.Address_State.value_counts(dropna=False).items():
                tekrari.append(dict(Year=y, Frame=FRAME(y), Record_Type='Address_state_by_Tekrari', Tekrari_Code=tv,
                    Address_State=st, N=int(nst), Previous_Observable=has_prev, Next_Observable=has_next))
            for wave, nw in g.Observed_Wave.value_counts(dropna=False).items():
                tekrari.append(dict(Year=y, Frame=FRAME(y), Record_Type='Observed_wave_by_Tekrari', Tekrari_Code=tv,
                    Observed_Wave=wave, N=int(nw), Previous_Observable=has_prev, Next_Observable=has_next))
        annual[y] = d

    # Test whether a nonmissing code behaves like first/middle/last position
    # specifically among complete three-year raw-Address candidates.
    for c in COHORTS:
        aset=set(annual[c[0]].Address_Raw.dropna()) & set(annual[c[1]].Address_Raw.dropna()) & set(annual[c[2]].Address_Raw.dropna())
        for position,y in enumerate(c,1):
            d=annual[y][annual[y].Address_Raw.isin(aset)]
            for tv,n in d.Tekrari_Code.value_counts(dropna=False).items():
                tekrari.append(dict(Year=y,Frame=FRAME(y),Record_Type='Tekrari_By_Cohort_Position',Cohort=f'{c[0]}_{c[2]}',
                    Cohort_Position=position,Tekrari_Code=tv,N=int(n),Address_Field_Present=('Tekrari' in d.columns and bool(schema[(schema.Year==str(y))&(schema.Column.str.casefold()=='tekrari')].shape[0]))))

    pd.DataFrame(codebook).to_csv(AUDIT / 'original_substitute_codebook.csv', index=False)
    pd.DataFrame(cross).to_csv(AUDIT / 'tekrari_response_crosstabs.csv', index=False)
    pd.DataFrame(tekrari).to_csv(AUDIT / 'tekrari_cross_validation.csv', index=False)
    pd.concat([d.assign(Year=y) for y,d in annual.items()], ignore_index=True).to_parquet(PRIVATE / 'tekrari_household_states.parquet', index=False)

if __name__ == '__main__': main()
