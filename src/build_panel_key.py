"""Design-based pilot candidates. No demographic variables used in any key.

These are diagnostic keys, not certified permanent family identifiers.
Replacement details distinguish respondent locations within a sample slot.
No speculative mapping from household row to rotation group is permitted.
"""
from audit_raw_panel_identifiers import ROOT, WORK, OUT, YEARS
import pandas as pd
import json

METHODS=['HBSIR_ID','Raw_Address','Frame_Address','Original_Only','Respondent_Location']
def frame(y): return '1389' if y<1392 else '1392' if y<1397 else '1397'
def candidates(y):
    h=pd.read_parquet(WORK/f'raw_household_{y}.parquet').dropna(subset=['Raw_Address']).copy()
    h['HBSIR_ID']=pd.to_numeric(h.Raw_Address).astype('UInt64').astype('string')
    h['Frame_Address']=frame(y)+'|'+h.Raw_Address
    original=h.Takmil.str.strip().eq('1') & ~h.Jaygozin.str.strip().eq('1').fillna(False)
    h['Original_Only']=h.Frame_Address.where(original)
    h['Respondent_Location']=(h.Frame_Address+'|original').where(original)
    alt=h.Takmil.str.strip().eq('2') & h.Jaygozin.str.strip().eq('1')
    complete=alt & h.BlkAbdJaygozin.str.strip().str.fullmatch('[0-9]+').fillna(False) & h.RadifJaygozin.str.strip().str.fullmatch('[0-9]+').fillna(False)
    # Retain original formatting of substitution fields, including leading zeroes.
    h.loc[complete,'Respondent_Location']=h.Frame_Address+'|substitute|'+h.BlkAbdJaygozin+'|'+h.RadifJaygozin
    return h

def main():
    hs={y:candidates(y) for y in YEARS}; overlaps=[];lengths=[];dup=[];long=[]
    for method in METHODS:
        history={}
        for y,h in hs.items():
            keys=h[method].dropna(); ndup=int(keys.duplicated().sum())
            dup.append(dict(Method=method,Year=y,All_HH=len(h),Eligible_HH=len(keys),Missing_Key=int(h[method].isna().sum()),Duplicate_Key_Rows=ndup))
            if ndup: raise AssertionError((method,y,ndup))
            for k in keys: history.setdefault(k,[]).append(y)
            for lag in [1,2]:
                if y+lag not in hs:continue
                a=set(keys);b=set(hs[y+lag][method].dropna());common=len(a&b)
                overlaps.append(dict(Method=method,Year_t=y,Year_next=y+lag,Lag=lag,N_t=len(a),N_next=len(b),N_common=common,Overlap_from_t=common/len(a) if a else None,Overlap_from_next=common/len(b) if b else None,Jaccard=common/len(a|b) if a|b else None,Boundary_Crossed=frame(y)!=frame(y+lag),Scope='raw_pilot'))
        for b in [1,2,3,4,5]:
            lengths.append(dict(Method=method,Observed_Years_Bin=str(b) if b<5 else '5+',Key_Count=sum(len(v)==b if b<5 else len(v)>=b for v in history.values()),Scope='pilot_noncontiguous_years'))
        for k,v in history.items():
            if len(v)>3:long.append(dict(Method=method,Candidate_Key=k,Years=';'.join(map(str,v)),Observed_Years=len(v),Scope='raw_pilot'))
    pd.DataFrame(overlaps).to_csv(OUT/'panel_key_candidate_overlap.csv',index=False)
    pd.DataFrame(lengths).to_csv(OUT/'panel_candidate_length_distribution.csv',index=False)
    pd.DataFrame(dup).to_csv(OUT/'panel_candidate_key_integrity.csv',index=False)
    pd.concat([h.assign(Year=y) for y,h in hs.items()],ignore_index=True).to_parquet(OUT/'panel_pilot_candidate_keys.parquet',index=False)
    pd.DataFrame(long).to_parquet(WORK/'pilot_over_three_keys.parquet',index=False)
    print(json.dumps({'methods':METHODS,'pilot_years':YEARS,'certified':False},ensure_ascii=False))

if __name__=='__main__': main()
