"""Fast one-to-one matching of raw P1 rosters, without permanent person IDs."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'intermediate/three_wave_validation/private'

def roster_map(year, addresses=None):
    """Compact per-household numpy blocks; Address is used only to prelink homes."""
    d=pd.read_parquet(PRIVATE/f'raw_roster_{year}.parquet')
    d['Address_Raw']=d.Address_Raw.astype('string')
    if addresses is not None:d=d[d.Address_Raw.isin(set(map(str,addresses)))].copy()
    d['_rel']=d.Relationship_Code.fillna('').astype(str)
    d['_sex']=d.Sex_Code.fillna('').astype(str)
    d['_age']=pd.to_numeric(d.Age_Raw,errors='coerce')
    d['_member']=d.Member_Number.fillna('').astype(str)
    out={}
    for a,g in d.groupby('Address_Raw',sort=False):
        rel=g._rel.to_numpy(dtype=object,copy=True)
        sex=g._sex.to_numpy(dtype=object,copy=True)
        age=g._age.to_numpy(dtype=float,na_value=np.nan,copy=True)
        member=g._member.to_numpy(dtype=object,copy=True)
        hi=np.flatnonzero(rel=='1')
        out[str(a)]={'rel':rel,'sex':sex,'age':age,'member':member,'head':int(hi[0]) if len(hi)==1 else -1}
    return out

def compatible_relation(a,b):
    return (a==b) or ({a,b}<={'1','2'}) or ({a,b}<={'1','3'})

def maximum_matching(valid,costs):
    """Maximum-cardinality bipartite matching; deterministic among equal optima."""
    n,m=valid.shape
    adjacency=[sorted(np.flatnonzero(valid[i]).tolist(),key=lambda j:(costs[i,j],j)) for i in range(n)]
    assigned={}
    def augment(i,seen):
        for j in adjacency[i]:
            if j in seen:continue
            seen.add(j)
            if j not in assigned or augment(assigned[j],seen):
                assigned[j]=i
                return True
        return False
    for i in sorted(range(n),key=lambda i:(len(adjacency[i]),i)):augment(i,set())
    return sorted((i,j) for j,i in assigned.items())

def assign_pair(a,b,gap):
    n,m=len(a['age']),len(b['age'])
    if not n or not m:return 0,[],0
    lo,hi=max(0,gap-1),gap
    delta=b['age'][None,:]-a['age'][:,None]
    sexok=(a['sex'][:,None]==b['sex'][None,:]) & np.isin(a['sex'][:,None],['1','2'])
    rel0=a['rel'][:,None];rel1=b['rel'][None,:]
    relok=(rel0==rel1)|(((rel0=='1')|(rel0=='2'))&((rel1=='1')|(rel1=='2')))|(((rel0=='1')|(rel0=='3'))&((rel1=='1')|(rel1=='3')))
    valid=sexok&relok&np.isfinite(delta)&(delta>=lo)&(delta<=hi)
    same_no=(a['member'][:,None]==b['member'][None,:])&(a['member'][:,None]!='')
    costs=np.where(rel0==rel1,0.0,1.0)+np.abs(delta-(lo+hi)/2)*.01
    pairs=maximum_matching(valid,costs)
    number_matches=len(maximum_matching(valid&same_no,costs))
    return len(pairs),pairs,number_matches

def pair_result(g0,g1,gap):
    a=g0 or {'rel':np.array([],dtype=object),'sex':np.array([],dtype=object),'age':np.array([],dtype=float),'member':np.array([],dtype=object),'head':-1}
    b=g1 or {'rel':np.array([],dtype=object),'sex':np.array([],dtype=object),'age':np.array([],dtype=float),'member':np.array([],dtype=object),'head':-1}
    n0,n1=len(a['age']),len(b['age'])
    matched,pairs,number_matched=assign_pair(a,b,gap)
    h0,h1=a['head'],b['head']
    head_avail=(h0>=0 and h1>=0)
    sx0=a['sex'][h0] if h0>=0 else None;sx1=b['sex'][h1] if h1>=0 else None
    age0=a['age'][h0] if h0>=0 else np.nan;age1=b['age'][h1] if h1>=0 else np.nan
    lo,hi=max(0,gap-1),gap
    sexok=bool(sx0 in ('1','2') and sx0==sx1)
    delta=age1-age0
    ageok=bool(np.isfinite(delta) and lo<=delta<=hi)
    transition=False;transition_source=''
    if head_avail:
        for i,j in pairs:
            if j==h1 and i!=h0 and a['rel'][i] in ('2','3'):
                transition=True;transition_source='spouse' if a['rel'][i]=='2' else 'child';break
    rate0=matched/n0 if n0 else np.nan
    rate1=matched/n1 if n1 else np.nan
    sym=min(rate0,rate1) if np.isfinite(rate0) and np.isfinite(rate1) else np.nan
    nrate0=number_matched/n0 if n0 else np.nan
    nrate1=number_matched/n1 if n1 else np.nan
    return dict(Matched_Members=matched,Members_t=n0,Members_t1=n1,Match_Rate_From_t=rate0,Match_Rate_From_t1=rate1,
        Symmetric_Roster_Match_Rate=sym,Number_Matched=number_matched,Number_Match_Rate_From_t=nrate0,Number_Match_Rate_From_t1=nrate1,
        Head_Sex_Consistent=sexok,Head_Age_Consistent=ageok,Plausible_Head_Transition=transition,
        Plausible_Head_Transition_Source=transition_source,Head0_Age=float(age0) if np.isfinite(age0) else np.nan,
        Head1_Age=float(age1) if np.isfinite(age1) else np.nan,Head0_Sex=sx0,Head1_Sex=sx1,
        Head0_Relationship=a['rel'][h0] if h0>=0 else None,Head1_Relationship=b['rel'][h1] if h1>=0 else None,
        _pairs=pairs,_n0=n0,_n1=n1)

def roster_matching_table(addresses,y0,y1,maps=None):
    maps=maps or {y0:roster_map(y0,addresses),y1:roster_map(y1,addresses)}
    rows=[]
    for address in addresses:
        z=pair_result(maps[y0].get(str(address)),maps[y1].get(str(address)),y1-y0)
        z.update(Address_Raw=str(address),Year_t=y0,Year_t1=y1);rows.append(z)
    return pd.DataFrame(rows)

if __name__=='__main__':
    raise SystemExit('Import functions from validate_three_wave_panels.py')
