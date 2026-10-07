"""Build and validate the eight raw-Address three-wave HBS cohorts.

The sole household link is (design frame, exact raw Access Address). No
demographics, member numbers, or HBSIR-cleaned identifiers create links.
"""
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
from validate_roster_continuity import roster_map, pair_result

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'intermediate/three_wave_validation/private'
AUDIT=ROOT/'audit'
FRAMES={'Frame_1392_1396':range(1392,1397),'Frame_1397_1403':range(1397,1404)}
COHORTS=[(1392,1393,1394),(1393,1394,1395),(1394,1395,1396),
         (1397,1398,1399),(1398,1399,1400),(1399,1400,1401),
         (1400,1401,1402),(1401,1402,1403)]

def missing(v): return pd.isna(v) or str(v).strip()==''
def txt(v): return None if missing(v) else str(v)
def response_state(t,j):
    t,j=txt(t),txt(j)
    if t=='1': return 'Original_responded' if j!='1' else 'Conflicting_original_and_substitute_yes'
    if t=='2' and j=='1': return 'Original_nonresponse_substitute_responded'
    if t=='2' and j=='2': return 'Original_nonresponse_substitute_nonresponse'
    if t=='2': return 'Original_nonresponse_substitute_status_missing'
    if t is None and j=='1': return 'Substitute_responded_original_status_missing'
    if t is None and j=='2': return 'Substitute_nonresponse_original_status_missing'
    return 'Ambiguous_or_missing'
def respondent_kind(t,j):
    t,j=txt(t),txt(j)
    if t=='1': return 'Original'
    if j=='1': return 'Substitute'
    if t=='2' and j=='2': return 'No_Completed_Interview'
    return 'Ambiguous'
def status_complete(t,j):
    t,j=txt(t),txt(j)
    return (t=='1' and j!='1') or (t=='2' and j in ('1','2'))
def frame(y): return 'Frame_1392_1396' if y<=1396 else 'Frame_1397_1403'
def cohort_name(c): return f'{c[0]}_{c[2]}'

def load_years():
    records = {}
    for y in range(1392,1404):
        d=pd.read_parquet(PRIVATE/f'raw_household_{y}.parquet').copy()
        d['Address_Raw']=d.Address_Raw.astype('string')
        if d.Address_Raw.isna().any() or d.Address_Raw.duplicated().any():
            raise AssertionError(f'Address is missing or duplicated in direct Access {y}')
        d=d[[c for c in ('Address_Raw','Raw_Table','Takmil','Jaygozin') if c in d.columns]].copy()
        d['Urban_Rural']=np.where(d.Raw_Table.astype('string').str.startswith('U'),'Urban','Rural')
        # Province and cluster are covariates/placebo strata parsed from raw
        # Address positions; the complete raw string remains the only key.
        d['Province_Code']=d.Address_Raw.str.slice(1,3)
        d['Cluster_Code']=d.Address_Raw.str.slice(0,9)
        d['Household_Status']=[response_state(t,j) for t,j in zip(d.Takmil if 'Takmil' in d else [None]*len(d),d.Jaygozin if 'Jaygozin' in d else [None]*len(d))]
        d['Respondent_Kind']=[respondent_kind(t,j) for t,j in zip(d.Takmil if 'Takmil' in d else [None]*len(d),d.Jaygozin if 'Jaygozin' in d else [None]*len(d))]
        d['Status_Complete']=[status_complete(t,j) for t,j in zip(d.Takmil if 'Takmil' in d else [None]*len(d),d.Jaygozin if 'Jaygozin' in d else [None]*len(d))]
        # Read each large P1 file only long enough to create vectorized head and
        # household-size summaries; full rosters are loaded on demand per pair.
        m=pd.read_parquet(PRIVATE/f'raw_roster_{y}.parquet')
        m['Address_Raw']=m.Address_Raw.astype('string')
        is_head=m.Relationship_Code.fillna('').astype(str).eq('1')
        hs=m[is_head].copy()
        hc=hs.groupby('Address_Raw').size()
        hs=hs[hs.Address_Raw.isin(hc[hc.eq(1)].index)].drop_duplicates('Address_Raw').set_index('Address_Raw')
        head=hs[['Sex_Code','Age_Raw','Education_Raw']].rename(columns={'Sex_Code':'Head_Sex','Age_Raw':'Head_Age','Education_Raw':'Head_Education_Raw'})
        head['Head_Age']=pd.to_numeric(head.Head_Age,errors='coerce')
        sizes=m.groupby('Address_Raw').size().rename('Household_Size')
        base=d.set_index('Address_Raw').join(head,how='left').join(sizes,how='left')
        records[y]=base
    return records

def bool_or_na(v):
    if v is None or pd.isna(v): return pd.NA
    return bool(v)

def main():
    AUDIT.mkdir(exist_ok=True)
    records=load_years()
    yearly=[]
    for y,d in records.items():
        a=d.index
        yearly.append(dict(Year=y,Frame=frame(y),Access_Household_Rows=len(d),Access_Member_Rows=int(pd.read_parquet(PRIVATE/f'raw_roster_{y}.parquet').shape[0]),
            Address_Unique=a.nunique(),Address_Duplicate_Rows=int(a.duplicated().sum()),Blank_Address=int(a.isna().sum()),
            Urban=int(d.Urban_Rural.eq('Urban').sum()),Rural=int(d.Urban_Rural.eq('Rural').sum()),
            Takmil_1=int(d.get('Takmil',pd.Series(index=d.index,dtype=object)).astype('string').eq('1').sum()),
            Tekrari_Field_Present=('Tekrari' in pd.read_parquet(PRIVATE/f'raw_household_{y}.parquet').columns)))
    pd.DataFrame(yearly).to_csv(AUDIT/'yearly_sample_summary_1392_1403.csv',index=False)
    # Frame-scoped address histories and interrupted returns.
    hist=defaultdict(list)
    for y,d in records.items():
        for a in d.index: hist[(frame(y),str(a))].append(y)
    hist_rows=[]
    for (fr,a),ys in hist.items():
        ys=sorted(ys)
        hist_rows.append(dict(Frame=fr,Address_Raw=a,Years=ys,Appearances=len(ys),
            Gap_Return=any(b-a>1 for a,b in zip(ys,ys[1:])),Adjacent_1392_1394=(fr=='Frame_1392_1396' and 1392 in ys and 1394 in ys and 1393 not in ys),
            Adjacent_t_t2_without_t1=any((b-a==2 and a+1 not in ys) for a,b in zip(ys,ys[1:]))))
    histdf=pd.DataFrame(hist_rows)
    rec=[]
    for (fr,n),g in histdf.groupby(['Frame','Appearances']): rec.append(dict(Frame=fr,Record_Type='Years_Present',Value=int(n),Address_Count=len(g)))
    for fr,g in histdf.groupby('Frame'):
        for col,label in [('Gap_Return','Any_gap_then_return'),('Adjacent_1392_1394','1392_and_1394_without_1393'),('Adjacent_t_t2_without_t1','Any_t_and_t2_without_t1')]:
            rec.append(dict(Frame=fr,Record_Type=label,Value='Yes',Address_Count=int(g[col].sum())))
    pd.DataFrame(rec).to_csv(AUDIT/'within_frame_address_recurrence.csv',index=False)
    # Household-level recurrence contains exact raw Address and stays private/Drive-only.
    histdf.to_parquet(PRIVATE/'within_frame_address_history.parquet',index=False)

    out=[]; pair_rows=[]; pair_cache={}
    for c in COHORTS:
        y0,y1,y2=c; fr=frame(y0); assert frame(y0)==frame(y1)==frame(y2)
        sets=[set(records[y].index) for y in c]
        addrs=sorted(sets[0]&sets[1]&sets[2])
        for y_a,y_b in ((y0,y1),(y1,y2)):
            key=(y_a,y_b)
            if key not in pair_cache: pair_cache[key]={}
            todo=[a for a in addrs if a not in pair_cache[key]]
            if todo:
                maps={y_a:roster_map(y_a,todo),y_b:roster_map(y_b,todo)}
                for a in todo: pair_cache[key][a]=pair_result(maps[y_a].get(str(a)),maps[y_b].get(str(a)),y_b-y_a)
        for a in addrs:
            d0,d1,d2=(records[y].loc[a] for y in c)
            source_states=[d.Household_Status for d in (d0,d1,d2)]
            b_all=all(str(records[y].loc[a].Takmil)=='1' if 'Takmil' in records[y] else False for y in c)
            c_all=all(bool(records[y].loc[a].Status_Complete) for y in c)
            p01,p12=pair_cache[(y0,y1)][a],pair_cache[(y1,y2)][a]
            headsex=[txt(d.Head_Sex) for d in (d0,d1,d2)]
            headages=[pd.to_numeric(pd.Series([d.Head_Age]),errors='coerce').iloc[0] for d in (d0,d1,d2)]
            sex_valid=all(x in ('1','2') for x in headsex)
            sex_consistent=bool(sex_valid and len(set(headsex))==1)
            age_valid=all(np.isfinite(x) for x in headages)
            pair_age=[bool(p01['Head_Age_Consistent']),bool(p12['Head_Age_Consistent'])]
            pair_sex=[bool(p01['Head_Sex_Consistent']),bool(p12['Head_Sex_Consistent'])]
            transitions=[bool(p01['Plausible_Head_Transition']),bool(p12['Plausible_Head_Transition'])]
            heads_available=all(x is not None and not pd.isna(x) for x in headages) and sex_valid
            age_path=bool(heads_available and all(pair_age))
            trans=any(transitions)
            sex_path_supported=all(sx or tr for sx,tr in zip(pair_sex,transitions))
            age_path_supported=all(ag or tr for ag,tr in zip(pair_age,transitions))
            demographic_path=bool(heads_available and all((sx and ag) or tr for sx,ag,tr in zip(pair_sex,pair_age,transitions)))
            cont=[p01['Symmetric_Roster_Match_Rate'],p12['Symmetric_Roster_Match_Rate']]
            continuity=min(cont) if all(np.isfinite(x) for x in cont) else np.nan
            mean_cont=float(np.mean(cont)) if all(np.isfinite(x) for x in cont) else np.nan
            l1=bool(b_all and demographic_path and all(np.isfinite(x) and x>=.75 for x in cont))
            l2=bool(b_all and demographic_path and all(np.isfinite(x) and x>=.50 for x in cont))
            l3=bool(c_all)
            score_parts=[float(sex_path_supported),float(age_path_supported),mean_cont]
            score=float(np.mean(score_parts)) if np.isfinite(mean_cont) else np.nan
            q='Strong_demographic_roster_support' if l1 else ('Moderate_demographic_roster_support' if l2 else ('Address_only_or_weak' if not c_all else 'Status_complete_demographic_support_unconfirmed'))
            row=dict(Panel_ID=f'{fr}:{a}',Address=str(a),Frame=fr,Cohort=cohort_name(c),Year_1=y0,Year_2=y1,Year_3=y2,
                Sample_A=True,Sample_B=b_all,Sample_C=c_all,Original_All_Three=b_all,
                Status_Complete_All_Three=c_all,Head_Sex_Consistent=sex_consistent if heads_available else pd.NA,
                Head_Age_Consistent=age_path if heads_available else pd.NA,Plausible_Head_Transition=trans,
                Head_Sex_Path_Supported=sex_path_supported if heads_available else pd.NA,
                Head_Age_Path_Supported=age_path_supported if heads_available else pd.NA,
                Demographic_Path_Acceptable=demographic_path if heads_available else pd.NA,
                Roster_Continuity=continuity,Mean_Roster_Continuity=mean_cont,
                Sample_Level_1=l1,Sample_Level_2=l2,Sample_Level_3=l3,Linkage_Quality=q,Linkage_Score=score,
                Urban_Rural=d0.Urban_Rural,Province_Code=d0.Province_Code,Household_Size_1=d0.Household_Size,
                Head_Age_1=d0.Head_Age,Head_Sex_1=d0.Head_Sex,Head_Education_Raw_1=d0.Head_Education_Raw)
            for i,(y,d) in enumerate(zip(c,(d0,d1,d2)),1):
                row[f'Takmil_{y}']=txt(d.get('Takmil'));row[f'Jaygozin_{y}']=txt(d.get('Jaygozin'))
                row[f'Response_State_{y}']=d.Household_Status;row[f'Respondent_Kind_{y}']=d.Respondent_Kind
                row[f'Urban_Rural_{y}']=d.Urban_Rural;row[f'Province_Code_{y}']=d.Province_Code
                row[f'Household_Size_{y}']=d.Household_Size;row[f'Head_Age_{y}']=d.Head_Age
                row[f'Head_Sex_{y}']=d.Head_Sex;row[f'Head_Education_Raw_{y}']=d.Head_Education_Raw
            for lab,p in [('12',p01),('23',p12)]:
                for k,v in p.items():
                    if k.startswith('_'): continue
                    row[f'{k}_{lab}']=v
            out.append(row)
            for pair_no,(ya,yb,p) in enumerate(((y0,y1,p01),(y1,y2,p12)),1):
                pair_rows.append(dict(Panel_ID=row['Panel_ID'],Address=str(a),Frame=fr,Cohort=cohort_name(c),Year_t=ya,Year_t1=yb,
                    Respondent_t=records[ya].loc[a].Respondent_Kind,Respondent_t1=records[yb].loc[a].Respondent_Kind,
                    Response_State_t=records[ya].loc[a].Household_Status,Response_State_t1=records[yb].loc[a].Household_Status,
                    **{k:v for k,v in p.items() if not k.startswith('_')}))

    cand=pd.DataFrame(out)
    cohort_counts=[]
    for c in COHORTS:
        name=cohort_name(c); y0=c[0]; g=cand[cand.Cohort.eq(name)]; n0=len(records[y0])
        b=int(g.Sample_B.sum()); cohort_counts.append(dict(Frame=frame(y0),Cohort=name,Year_1=y0,Year_2=c[1],Year_3=c[2],
            Candidate_A=int(len(g)),Candidate_B=b,Candidate_C=int(g.Sample_C.sum()),
            B_Percent_of_First_Year=100*b/n0 if n0 else np.nan,Theoretical_One_Third_First_Year=n0/3,
            B_Percent_of_Theoretical_One_Third=100*b/(n0/3) if n0 else np.nan,
            Level_1=int(g.Sample_Level_1.sum()),Level_2=int(g.Sample_Level_2.sum()),Level_3=int(g.Sample_Level_3.sum()),
            Head_Sex_Consistent_N=int(g[g.Sample_B].Head_Sex_Consistent.fillna(False).sum()),
            Head_Age_Consistent_N=int(g[g.Sample_B].Head_Age_Consistent.fillna(False).sum()),
            Plausible_Head_Transition_N=int(g[g.Sample_B].Plausible_Head_Transition.sum()),
            Roster_Median_B=float(g[g.Sample_B].Roster_Continuity.median()) if b else np.nan,
            Roster_GE50_B=float(g[g.Sample_B].Roster_Continuity.ge(.5).mean()*100) if b else np.nan,
            Roster_GE75_B=float(g[g.Sample_B].Roster_Continuity.ge(.75).mean()*100) if b else np.nan,
            Roster_LT25_B=float(g[g.Sample_B].Roster_Continuity.lt(.25).mean()*100) if b else np.nan))
        # One file per cohort includes all A candidates and independent A/B/C flags.
        g.to_parquet(AUDIT/f'three_wave_{y0}_{c[2]}.parquet',index=False)
    pd.DataFrame(cohort_counts).to_csv(AUDIT/'three_wave_cohort_counts.csv',index=False)
    cand.to_parquet(AUDIT/'panel_candidates_1392_1403.parquet',index=False)
    pd.DataFrame(pair_rows).to_parquet(PRIVATE/'three_wave_pairwise_roster_diagnostics.parquet',index=False)

    # Cohort membership collisions are measured, not silently reassigned.
    overlaps=cand.groupby(['Frame','Panel_ID']).Cohort.nunique().reset_index(name='Cohort_Count')
    coll=overlaps[overlaps.Cohort_Count.gt(1)]
    pd.DataFrame([dict(Frame=fr,Candidate_Keys=int(cand[cand.Frame.eq(fr)].Panel_ID.nunique()),
        Keys_In_Multiple_Cohorts=int(coll[coll.Frame.eq(fr)].shape[0]),Extra_Cohort_Memberships=int((coll[coll.Frame.eq(fr)].Cohort_Count-1).sum())) for fr in sorted(cand.Frame.unique())]).to_csv(AUDIT/'cohort_overlap_integrity.csv',index=False)
    coll.to_parquet(PRIVATE/'cohort_overlap_household_keys.parquet',index=False)

    # Main/substitute vs respondent-type pair comparisons.
    pairs=pd.DataFrame(pair_rows)
    cmp=[]
    for (cname,ya,yb,r0,r1),g in pairs.groupby(['Cohort','Year_t','Year_t1','Respondent_t','Respondent_t1'],dropna=False):
        cmp.append(dict(Cohort=cname,Year_t=ya,Year_t1=yb,Respondent_t=r0,Respondent_t1=r1,N=len(g),
            Head_Sex_Consistent_Pct=100*g.Head_Sex_Consistent.mean(),Head_Age_Consistent_Pct=100*g.Head_Age_Consistent.mean(),
            Plausible_Head_Transition_N=int(g.Plausible_Head_Transition.sum()),Median_Roster_Continuity=g.Symmetric_Roster_Match_Rate.median(),
            Roster_GE50_Pct=100*g.Symmetric_Roster_Match_Rate.ge(.5).mean(),Roster_GE75_Pct=100*g.Symmetric_Roster_Match_Rate.ge(.75).mean()))
    pd.DataFrame(cmp).to_csv(AUDIT/'original_substitute_pair_comparison.csv',index=False)

    # Compare sample profiles using raw Access design and P1 codes, not HBSIR output.
    profiles=[]
    for cname,g in cand.groupby('Cohort'):
        for level,maskcol in [('Level_1','Sample_Level_1'),('Level_2','Sample_Level_2'),('Level_3','Sample_Level_3')]:
            z=g[g[maskcol].fillna(False)]
            for val,n in z.Urban_Rural.value_counts(dropna=False).items():profiles.append(dict(Cohort=cname,Level=level,Profile='Urban_Rural',Value=str(val),Count=int(n),Percent=100*n/len(z) if len(z) else np.nan,N=len(z)))
            for val,n in z.Province_Code.value_counts(dropna=False).items():profiles.append(dict(Cohort=cname,Level=level,Profile='Province_Code_Raw_Address_Pos_2_3',Value=str(val),Count=int(n),Percent=100*n/len(z) if len(z) else np.nan,N=len(z)))
            for var in ('Household_Size_1','Head_Age_1'):
                x=pd.to_numeric(z[var],errors='coerce').dropna()
                profiles.append(dict(Cohort=cname,Level=level,Profile=var,Value='summary',Count=len(x),Percent=np.nan,N=len(z),Mean=x.mean(),Median=x.median()))
            for val,n in z.Head_Sex_1.value_counts(dropna=False).items():profiles.append(dict(Cohort=cname,Level=level,Profile='Head_Sex_Raw_Code',Value=str(val),Count=int(n),Percent=100*n/len(z) if len(z) else np.nan,N=len(z)))
            for val,n in z.Head_Education_Raw_1.value_counts(dropna=False).items():profiles.append(dict(Cohort=cname,Level=level,Profile='Head_Education_Raw_DYCOL08',Value=str(val),Count=int(n),Percent=100*n/len(z) if len(z) else np.nan,N=len(z)))
    pd.DataFrame(profiles).to_csv(AUDIT/'sample_level_profiles.csv',index=False)

    # Middle-wave absence and return; kept separate from balanced panels.
    middle=[]
    for c in COHORTS:
        y0,y1,y2=c; absent=sorted((set(records[y0].index)&set(records[y2].index))-set(records[y1].index))
        maps={y0:roster_map(y0,absent),y2:roster_map(y2,absent)} if absent else {y0:{},y2:{}}
        for a in absent:
            p=pair_result(maps[y0].get(str(a)),maps[y2].get(str(a)),y2-y0)
            d0,d2=records[y0].loc[a],records[y2].loc[a]
            middle.append(dict(Frame=frame(y0),Cohort=cohort_name(c),Address=str(a),Year_Present_1=y0,Year_Missing=y1,Year_Return=y2,
                Respondent_Kind_1=d0.Respondent_Kind,Response_State_1=d0.Household_Status,Takmil_1=txt(d0.get('Takmil')),Jaygozin_1=txt(d0.get('Jaygozin')),
                Respondent_Kind_3=d2.Respondent_Kind,Response_State_3=d2.Household_Status,Takmil_3=txt(d2.get('Takmil')),Jaygozin_3=txt(d2.get('Jaygozin')),
                Urban_Rural=d0.Urban_Rural,Province_Code=d0.Province_Code,Household_Size_1=d0.Household_Size,Household_Size_3=d2.Household_Size,
                Head_Age_1=d0.Head_Age,Head_Age_3=d2.Head_Age,Head_Sex_1=d0.Head_Sex,Head_Sex_3=d2.Head_Sex,
                **{k:v for k,v in p.items() if not k.startswith('_')}))
    middledf=pd.DataFrame(middle)
    if len(middledf):
        middledf.to_parquet(PRIVATE/'middlewave_absence_returns.parquet',index=False)
        ms=[]
        for (cn,r0,r2),g in middledf.groupby(['Cohort','Respondent_Kind_1','Respondent_Kind_3'],dropna=False):
            ms.append(dict(Cohort=cn,Respondent_Kind_1=r0,Respondent_Kind_3=r2,N=len(g),Median_Roster_Continuity=g.Symmetric_Roster_Match_Rate.median(),
                Head_Sex_Consistent_Pct=100*g.Head_Sex_Consistent.mean(),Head_Age_Consistent_Pct=100*g.Head_Age_Consistent.mean()))
        pd.DataFrame(ms).to_csv(AUDIT/'middlewave_nonresponse_summary.csv',index=False)
    else:
        middledf.to_parquet(PRIVATE/'middlewave_absence_returns.parquet',index=False)
        pd.DataFrame(columns=['Cohort','Respondent_Kind_1','Respondent_Kind_3','N']).to_csv(AUDIT/'middlewave_nonresponse_summary.csv',index=False)
    middle_summary=pd.read_csv(AUDIT/'middlewave_nonresponse_summary.csv')
    persisted_middle=pd.read_parquet(PRIVATE/'middlewave_absence_returns.parquet')
    summarized_n=int(pd.to_numeric(middle_summary['N'],errors='coerce').fillna(0).sum())
    if summarized_n != len(persisted_middle):
        raise AssertionError(f'middlewave summary sum(N)={summarized_n} != household rows={len(persisted_middle)}')

    # Best/worst B cases are anonymous: only code fields and year/relationship/sex/age.
    extremes=[]; chosen={}
    for c in COHORTS:
        name=cohort_name(c);g=cand[(cand.Cohort==name)&cand.Sample_B].copy()
        g=g.sort_values(['Linkage_Score','Address'],ascending=[False,True],na_position='last')
        best=g.head(100).copy();best['Case_Set']='Best';best['Rank']=np.arange(1,len(best)+1)
        worst=g.sort_values(['Linkage_Score','Address'],ascending=[True,True],na_position='first').head(100).copy();worst['Case_Set']='Worst';worst['Rank']=np.arange(1,len(worst)+1)
        chosen[name]=pd.concat([best,worst],ignore_index=True)
    for y in sorted({v for c in COHORTS for v in c}):
        raw=pd.read_parquet(PRIVATE/f'raw_roster_{y}.parquet')
        for name,cases in chosen.items():
            if not len(cases): continue
            cy=cand.loc[cand.Cohort.eq(name),['Year_1','Year_2','Year_3']].iloc[0].astype(int).tolist()
            if y not in cy: continue
            sub=cases[['Frame','Cohort','Panel_ID','Address','Case_Set','Rank','Linkage_Score']].merge(
                raw[raw.Address_Raw.isin(set(cases.Address))],left_on='Address',right_on='Address_Raw',how='inner')
            for _,z in sub.iterrows():
                extremes.append(dict(Frame=z.Frame,Cohort=name,Panel_ID=z.Panel_ID,Address=z.Address,Case_Set=z.Case_Set,Rank=int(z.Rank),Linkage_Score=z.Linkage_Score,Year=y,
                    Relationship=txt(z.get('Relationship_Code')),Sex=txt(z.get('Sex_Code')),Age=pd.to_numeric(z.get('Age_Raw'),errors='coerce'),Member_Number=txt(z.get('Member_Number'))))
    pd.DataFrame(extremes).to_parquet(AUDIT/'panel_link_extreme_cases.parquet',index=False)

if __name__=='__main__': main()
