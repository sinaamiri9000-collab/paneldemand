"""Validate existing design-key links; demographics never create links.

Pilot member variables are read directly from Access exports. Member numbers
are provisional roster positions, never permanent person IDs. Quality flags
and time-aware age checks are diagnostics, not automatic deletions.
"""
from build_panel_key import ROOT, WORK, OUT, YEARS, METHODS, candidates, frame
import pandas as pd
import numpy as np
import json
from collections import Counter
from bssir.data_cleaner import _general_cleaning

REL={'1':'Head','2':'Spouse','3':'Child','4':'Child_in_Law','5':'Grand_Child','6':'Parent','7':'Sibling','8':'Other_Family','9':'Non_Family'}

def raw_members(y):
    m=pd.read_parquet(WORK/f'raw_members_{y}.parquet')
    d=pd.DataFrame({'ID':pd.to_numeric(_general_cleaning(m.Address),errors='raise').astype('UInt64').astype('string'),
        'Member_Number':pd.to_numeric(_general_cleaning(m.DYCOL01),errors='raise'),
        'Relationship':_general_cleaning(m.DYCOL03).map(REL),
        'Sex':_general_cleaning(m.DYCOL04).map({'1':'Male','2':'Female'}),
        'Age':pd.to_numeric(_general_cleaning(m.DYCOL05),errors='raise')})
    s=pd.read_parquet(ROOT/f'yearly/{y}/members.parquet')[d.columns].copy();s.ID=s.ID.astype('string')
    def counts(f): return Counter(tuple(None if pd.isna(v) else str(v) for v in r) for r in f.itertuples(index=False,name=None))
    # Compare numeric columns as numbers, avoiding '42.0' vs '42' formatting.
    for f in [d,s]:
        for c in ['Age','Member_Number']:f[c]=pd.to_numeric(f[c]).astype('Int64')
        for c in ['Relationship','Sex']:f[c]=f[c].astype('string')
    assert counts(d)==counts(s),(y,'raw roster differs from normalized reference')
    return d

def heads(m):
    h=m[m.Relationship.eq('Head')].copy();n=h.groupby('ID').size()
    h=h[h.ID.map(n).eq(1)].set_index('ID')[['Member_Number','Sex','Age']]
    return h,n

def evaluate(a,b,ma,mb,lag):
    # a/b uniquely indexed by the design candidate; missing candidate keys excluded.
    linked=a[['HBSIR_ID','MahMorajeh']].join(b[['HBSIR_ID','MahMorajeh']],how='inner',lsuffix='_t',rsuffix='_next')
    ht,nt=heads(ma);hn,nn=heads(mb)
    for side,hh,n in [('t',ht,nt),('next',hn,nn)]:
        ids=linked['HBSIR_ID_'+side]
        linked['Head_Count_'+side]=ids.map(n).fillna(0).astype(int)
        for c in ['Member_Number','Sex','Age']:linked['Head_'+c+'_'+side]=ids.map(hh[c])
    linked['Lag']=lag
    delta=linked.Head_Age_next-linked.Head_Age_t
    linked['Head_Age_Difference']=delta
    known=linked.Head_Age_t.notna() & linked.Head_Age_next.notna()
    linked['Head_Age_Known']=known
    linked['Head_Age_Consistent']=delta.isin([0,1] if lag==1 else [1,2]).astype('boolean').where(known)
    sexknown=linked.Head_Sex_t.notna() & linked.Head_Sex_next.notna()
    linked['Head_Sex_Known']=sexknown
    linked['Head_Sex_Consistent']=linked.Head_Sex_t.eq(linked.Head_Sex_next).astype('boolean').where(sexknown)
    linked['Both_Known']=known & sexknown
    linked['Head_Both_Consistent']=(linked.Head_Age_Consistent & linked.Head_Sex_Consistent).where(linked.Both_Known)
    linked['Possible_Head_Change']=((linked.Head_Member_Number_t!=linked.Head_Member_Number_next) | (linked.Head_Sex_Consistent.eq(False)) | linked.Head_Age_Consistent.eq(False)).where(linked.Both_Known)
    # Raw MahMorajeh=01 refers to next Farvardin in a May-April survey year.
    mt=pd.to_numeric(linked.MahMorajeh_t,errors='coerce')
    mn=pd.to_numeric(linked.MahMorajeh_next,errors='coerce')
    mt=mt.where(mt.between(1,12)).replace({1:13})
    mn=mn.where(mn.between(1,12)).replace({1:13})
    elapsed=lag*12+mn-mt;linked['Approx_Elapsed_Months']=elapsed
    # Month-only observations imply an elapsed duration interval of +/- one month.
    lower=np.floor((elapsed-1)/12);upper=np.ceil((elapsed+1)/12)
    linked['Head_Age_Time_Plausible']=delta.between(lower,upper).where(known & elapsed.notna())
    linked['Head_Age_Outside_Default_But_Time_Plausible']=(linked.Head_Age_Consistent.eq(False)&linked.Head_Age_Time_Plausible.eq(True))
    # Test roster position AND relationship without creating a household match.
    left=ma.merge(linked.reset_index()[['Candidate_Key','HBSIR_ID_t']],left_on='ID',right_on='HBSIR_ID_t')
    right=mb.merge(linked.reset_index()[['Candidate_Key','HBSIR_ID_next']],left_on='ID',right_on='HBSIR_ID_next')
    pairs=left.merge(right,on=['Candidate_Key','Member_Number','Relationship'],suffixes=('_t','_next'))
    avail=pairs.Age_t.notna()&pairs.Age_next.notna()&pairs.Sex_t.notna()&pairs.Sex_next.notna()
    pairs=pairs[avail].copy()
    pairs['Consistent']=(pairs.Age_next-pairs.Age_t).isin([0,1] if lag==1 else [1,2])&pairs.Sex_t.eq(pairs.Sex_next)
    gp=pairs.groupby('Candidate_Key').Consistent.agg(['size','mean'])
    linked['Provisional_Member_Pairs']=linked.index.map(gp['size']).fillna(0).astype(int)
    linked['Provisional_Member_Consistency']=pd.to_numeric(pd.Series(linked.index.map(gp['mean']),index=linked.index),errors='coerce')
    linked['Severe_Roster_Inconsistency']=(linked.Provisional_Member_Consistency<.5).where(linked.Provisional_Member_Pairs>=2)
    linked['Members_t']=linked.HBSIR_ID_t.map(ma.groupby('ID').size()).fillna(0)
    linked['Members_next']=linked.HBSIR_ID_next.map(mb.groupby('ID').size()).fillna(0)
    linked['Design_Certified']=False
    linked['Diagnostic_Score_0_100']=(40*linked.Head_Age_Consistent.astype('Float64')+20*linked.Head_Sex_Consistent.astype('Float64')+40*linked.Provisional_Member_Consistency).where(linked.Both_Known & linked.Provisional_Member_Consistency.notna())
    linked['Panel_Link_Confidence']='D'
    linked['Demographic_Quality']=np.select([(linked.Head_Both_Consistent.eq(True).fillna(False)&~linked.Severe_Roster_Inconsistency.eq(True).fillna(False)).to_numpy(dtype=bool),linked.Head_Both_Consistent.eq(True).fillna(False).to_numpy(dtype=bool)],['consistent','head_consistent_roster_warning'],default='review_or_missing')
    linked['Panel_Link_Warning']='Uncertified longitudinal design key; possible head changes are warnings; member numbers provisional'
    return linked.reset_index()

def summary(d,method,y,ny,scope):
    r=dict(Method=method,Year_t=y,Year_next=ny,Lag=ny-y,Scope=scope,Links=len(d))
    for c in ['Head_Age_Consistent','Head_Sex_Consistent','Head_Both_Consistent','Possible_Head_Change','Severe_Roster_Inconsistency','Head_Age_Time_Plausible']:
        r[c+'_Evaluable']=int(d[c].notna().sum());r[c+'_Count']=int(d[c].fillna(False).sum());r[c+'_Rate']=float(d[c].mean()) if d[c].notna().any() else None
    r['Head_Change_Confirmed_Count']=None
    r['Head_Change_Interpretation']='Possible only; permanent person identifier absent'
    r['Time_Plausible_Outside_Default']=int(d.Head_Age_Outside_Default_But_Time_Plausible.sum())
    return r

def main():
    ms={y:raw_members(y) for y in YEARS};hs={y:candidates(y) for y in YEARS};rows=[];links=[];samples=[]
    for method in METHODS:
        for y in YEARS:
            for lag in [1,2]:
                ny=y+lag
                if ny not in YEARS:continue
                def idx(h):return h.dropna(subset=[method]).set_index(method,drop=False).rename_axis('Candidate_Key')
                d=evaluate(idx(hs[y]),idx(hs[ny]),ms[y],ms[ny],lag)
                d['Method']=method;d['Year_t']=y;d['Year_next']=ny;d['Design_Period']=frame(y)
                rows.append(summary(d,method,y,ny,'direct_raw_pilot'));links.append(d)
    all_links=pd.concat(links,ignore_index=True)
    all_links.to_parquet(OUT/'panel_pilot_link_diagnostics.parquet',index=False)
    # Fixed, reproducible representative sample; one method avoids duplicate aliases.
    for (period,lag),g in all_links[all_links.Method.eq('Respondent_Location')].groupby(['Design_Period','Lag']):
        samples.append(g.sample(n=min(500,len(g)),random_state=20261007))
    pd.concat(samples,ignore_index=True).to_parquet(OUT/'panel_link_validation_sample.parquet',index=False)
    pd.DataFrame(rows).to_csv(OUT/'panel_link_demographic_validation.csv',index=False)
    all_links.groupby(['Method','Year_t','Year_next','Demographic_Quality']).size().rename('Links').reset_index().to_csv(OUT/'panel_link_quality_summary.csv',index=False)
    all_links[all_links.Method.eq('Respondent_Location')].groupby(['Design_Period','Lag']).size().rename('Available_Links').reset_index().assign(Sample_Limit=500).to_csv(OUT/'panel_validation_sample_summary.csv',index=False)
    # Existing 14-year ID history is an anomaly diagnostic, not extension of a certified key.
    hist=pd.read_parquet(OUT/'panel_household_history.parquet');long=hist[hist.Number_of_Observed_Years>3].copy()
    records=[];fullmembers={};fullhh={}
    for y in range(1390,1404):
        ids=set(long.ID.astype('string'))
        m=pd.read_parquet(ROOT/f'yearly/{y}/members.parquet');m.ID=m.ID.astype('string');fullmembers[y]=m[m.ID.isin(ids)]
        h=pd.read_parquet(ROOT/f'yearly/{y}/household.parquet');h.ID=h.ID.astype('string');fullhh[y]=h[h.ID.isin(ids)]
    for r in long.itertuples():
        years=list(map(int,r.Years_Present.split(';')));hid=str(r.ID)
        for a,b in zip(years,years[1:]):
            ha,_=heads(fullmembers[a]);hb,_=heads(fullmembers[b]);ar=ha.loc[hid] if hid in ha.index else None;br=hb.loc[hid] if hid in hb.index else None
            da=float(br.Age-ar.Age) if ar is not None and br is not None and pd.notna(ar.Age) and pd.notna(br.Age) else None
            records.append(dict(Method='HBSIR_ID',Candidate_Key=hid,Year_t=a,Year_next=b,Observed_Years=len(years),Years_Present=r.Years_Present,Consecutive=b==a+1,Maximum_Consecutive_Run=r.Maximum_Consecutive_Run,Crosses_1391_1392=a<=1391<b,Crosses_1396_1397=a<=1396<b,Head_Age_Difference=da,Head_Age_Default_Consistent=da in ([0,1] if b-a==1 else [1,2]) if da is not None and b-a in [1,2] else None,Head_Sex_Consistent=(ar.Sex==br.Sex) if ar is not None and br is not None and pd.notna(ar.Sex) and pd.notna(br.Sex) else None,Interpretation='reuse_or_unexplained_design_exception; demographic compatibility does not prove identity',Scope='existing_standardized_14year_anomaly_only'))
    longdiag=pd.DataFrame(records)
    # Include every pilot candidate's >3-year keys; the 14-year diagnostic remains
    # separately scoped and does not certify or extend a pilot key.
    pilot_long=pd.read_parquet(WORK/'pilot_over_three_keys.parquet')
    pd.concat([longdiag,pilot_long],ignore_index=True).to_parquet(OUT/'id_over_three_years.parquet',index=False)
    result={'distinct_ids':len(long),'transitions':len(longdiag),'consecutive_transitions':int(longdiag.Consecutive.sum()),'max_consecutive_run_distribution':long.Maximum_Consecutive_Run.value_counts().sort_index().to_dict(),'cross_boundary_1391_1392_ids':int(longdiag[longdiag.Crosses_1391_1392].Candidate_Key.nunique()),'cross_boundary_1396_1397_ids':int(longdiag[longdiag.Crosses_1396_1397].Candidate_Key.nunique()),'consecutive_age_default_evaluable':int(longdiag.loc[longdiag.Consecutive,'Head_Age_Default_Consistent'].notna().sum()),'consecutive_age_default_rate':float(longdiag.loc[longdiag.Consecutive,'Head_Age_Default_Consistent'].mean()),'sex_evaluable':int(longdiag.Head_Sex_Consistent.notna().sum()),'sex_rate':float(longdiag.Head_Sex_Consistent.mean()),'confirmed_reuse_count':None,'confirmed_same_family_count':None}
    (OUT/'id_over_three_years_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=int))
    # Detailed reproducible inspection of source rows for 24 sampled links.
    sample=pd.concat(samples,ignore_index=True);review=[]
    for (period,lag),g in sample.groupby(['Design_Period','Lag']):
        for r in g.sample(n=min(6,len(g)),random_state=73).itertuples():
            ha=hs[r.Year_t].set_index('HBSIR_ID').loc[r.HBSIR_ID_t]
            hb=hs[r.Year_next].set_index('HBSIR_ID').loc[r.HBSIR_ID_next]
            assert ha.Respondent_Location==hb.Respondent_Location==r.Candidate_Key
            review.append(dict(Candidate_Key=r.Candidate_Key,Year_t=r.Year_t,Year_next=r.Year_next,Lag=lag,Design_Period=period,Raw_Key_Checked=True,Raw_Takmil_t=ha.Takmil,Raw_Takmil_next=hb.Takmil,Raw_Jaygozin_t=ha.Jaygozin,Raw_Jaygozin_next=hb.Jaygozin,Head_Age_t=r.Head_Age_t,Head_Age_next=r.Head_Age_next,Head_Sex_t=r.Head_Sex_t,Head_Sex_next=r.Head_Sex_next,Age_Default_Consistent=r.Head_Age_Consistent,Sex_Consistent=r.Head_Sex_Consistent,Review_Type='mechanical_partial_source_row_review_not_human_adjudication'))
    pd.DataFrame(review).to_parquet(OUT/'panel_link_partial_source_review.parquet',index=False)
    print(pd.DataFrame(rows)[['Method','Year_t','Year_next','Links','Head_Both_Consistent_Rate']].to_string(index=False),flush=True)

if __name__=='__main__':main()
