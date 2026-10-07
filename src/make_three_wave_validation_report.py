"""Render Persian reports from the direct-Access validation outputs."""
from pathlib import Path
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'audit'

def nfmt(x):
    try:return f'{int(x):,}'
    except:return '—'
def pfmt(x,d=1):
    try:
        if pd.isna(x):return '—'
        return f'{float(x):.{d}f}%'
    except:return '—'
def table(df,cols,headers=None):
    headers=headers or cols
    lines=['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']
    for _,r in df.iterrows():
        vals=[]
        for c in cols:
            v=r.get(c,'')
            vals.append(str(v).replace('|','\\|'))
        lines.append('| '+' | '.join(vals)+' |')
    return '\n'.join(lines)

def tekrari_report():
    cv=pd.read_csv(AUDIT/'tekrari_cross_validation.csv')
    counts=cv[cv.Record_Type.eq('Code_by_area')].copy()
    pred=cv[cv.Record_Type.eq('Address_prediction_by_Tekrari')].copy()
    waves=cv[cv.Record_Type.eq('Tekrari_By_Cohort_Position')].copy()
    cross=pd.read_csv(AUDIT/'tekrari_response_crosstabs.csv')
    lines=['# ممیزی پزشکی‌قانونی متغیر Tekrari','',
      'این ممیزی از جدول‌های خانوار Access خام و پرسشنامه‌های همان سال استفاده می‌کند. هیچ پیوندی میان دو دوره طراحی ساخته نشده است. مقدار خالی جدا از کدهای مشاهده‌شده نگه داشته شده است.','',
      '## دامنه و معنای مستند','',
      'فیلد `Tekrari` در جدول Access خانوار سال‌های ۱۳۹۲ تا ۱۳۹۵ وجود دارد؛ در ۱۳۹۶ تا ۱۴۰۳ اصلاً در شِمای Access نیست. در ۱۳۹۲ همه ردیف‌ها خالی‌اند. در ۱۳۹۳ دو مقدار نقطه و ۲٬۱۱۴ مقدار ۱ دیده می‌شود؛ در ۱۳۹۴ مقدار ۱ برای ۲٬۱۰۷ ردیف و در ۱۳۹۵ برای ۲٬۱۹۶ ردیف دیده می‌شود. پرسشنامه‌های خام، تعریف مستقیم و صریحی برای فیلد `Tekrari` پیدا نمی‌کنند. بنابراین معنای آن را قطعی نمی‌نامم. جملهٔ روی جلد دربارهٔ تکراری نبودن محل اقامت خانوار اصلی به‌تنهایی تعریف این فیلد نیست.','',
      '## فراوانی و محل سکونت','',
      table(counts.assign(Code=counts.Tekrari_Code.fillna('<گمشده>')).rename(columns={'Year':'سال','Code':'کد Tekrari','N':'کل','Urban':'شهری','Rural':'روستایی'})[['سال','کد Tekrari','کل','شهری','روستایی']],['سال','کد Tekrari','کل','شهری','روستایی']),'',
      '## پیش‌بینی تکرار واقعی Address','',
      'تکرار واقعی فقط از حضور همان رشتهٔ خام Address در سال قبل/بعد داخل همان دورهٔ طراحی تعریف شده است. در ابتدا و انتهای دوره، سمت فاقد سال همسایه قابل مشاهده نیست؛ از آن طرف، احتمال شرطی محاسبه نشده است.','',
      table(pred.assign(Code=pred.Tekrari_Code.fillna('<گمشده>'),Prev=pred.P_Previous_Given_Tekrari.map(lambda x:pfmt(100*x)),Next=pred.P_Next_Given_Tekrari.map(lambda x:pfmt(100*x)),Given=pred.P_Tekrari_Given_Repeated_Address.map(lambda x:pfmt(100*x))).rename(columns={'Year':'سال','Code':'کد Tekrari','Prev':'احتمال Address در سال قبل | کد','Next':'احتمال Address در سال بعد | کد','Given':'سهم این کد از Addressهای تکرارشده'})[['سال','کد Tekrari','احتمال Address در سال قبل | کد','احتمال Address در سال بعد | کد','سهم این کد از Addressهای تکرارشده']],['سال','کد Tekrari','P(Address قبل | کد)','P(Address بعد | کد)','P(کد | Address تکرار‌شده)']),'',
      'در ۱۳۹۳ تا ۱۳۹۵، مقدار ۱ با احتمال اندکی بیشتر از کدهای خالی با حضور Address در دو همسایه همراه است، اما ارزش ۱ فقط حدود ۵٫۸ تا ۶٫۱ درصد از تمام ردیف‌های واقعاً تکرارشده را پوشش می‌دهد. بنابراین به‌تنهایی شاخص قابل اتکایی برای انتخاب پنل نیست. مقدار نقطه در ۱۳۹۳ فقط دو مشاهده دارد.','',
      '## سازگاری با موج مشاهده‌شده','',
      'موقعیت موج در این جدول برای هر cohortِ سه‌ساله‌ای محاسبه شده که Address در هر سه سال حضور دارد. کد ۱ در ۱۳۹۳، ۱۳۹۴ و ۱۳۹۵ در موقعیت‌های اول، دوم و سوم cohortها دیده می‌شود؛ بنابراین کد موج را مشخص نمی‌کند. برای سال ۱۳۹۲ همه مقادیر گمشده‌اند و سال‌های بعد فیلد در Access وجود ندارد.','',
      table(waves.assign(Code=waves.Tekrari_Code.fillna('<گمشده>')).rename(columns={'Year':'سال','Cohort':'cohort','Code':'کد Tekrari','Cohort_Position':'موقعیت در cohort','N':'تعداد'})[['سال','cohort','کد Tekrari','موقعیت در cohort','تعداد']],['سال','cohort','کد Tekrari','موقعیت در cohort','تعداد']),'',
      '## رابطه با Takmil و Jaygozin','',
      'توافق‌های شمارشی Tekrari × Takmil و Tekrari × Jaygozin در `tekrari_response_crosstabs.csv` ثبت شده‌اند؛ نرخ‌ها و کدهای خالی در همان فایل باقی مانده‌اند. این جدول‌ها الگوی توصیفی‌اند و به‌تنهایی معنی متغیر را ثابت نمی‌کنند.','',
      '## نتیجه','',
      '`Tekrari` در دادهٔ خام معنای مستندی که بتوان آن را معادل «خانوار پیگیری‌شده» یا «موج پنل» دانست ندارد. کد ۱ در ۱۳۹۳–۱۳۹۵ فقط یک همراهی ضعیف با تکرار Address نشان می‌دهد؛ مقدار آن برای ساخت یا حذف پیوند خانوار به کار نرفته است.']
    (AUDIT/'tekrari_forensic_audit.md').write_text('\n'.join(lines),encoding='utf-8')

def repair_panel_scores_and_extremes():
    """Apply the predeclared balanced score and refresh anonymized examples."""
    path=AUDIT/'panel_candidates_1392_1403.parquet'
    cand=pd.read_parquet(path)
    def flag(row,col):
        v=row.get(col)
        return False if pd.isna(v) else bool(v)
    sex_supported=[];age_supported=[];scores=[]
    for _,r in cand.iterrows():
        sx=[flag(r,'Head_Sex_Consistent_12'),flag(r,'Head_Sex_Consistent_23')]
        ag=[flag(r,'Head_Age_Consistent_12'),flag(r,'Head_Age_Consistent_23')]
        tr=[flag(r,'Plausible_Head_Transition_12'),flag(r,'Plausible_Head_Transition_23')]
        ss=all(a or b for a,b in zip(sx,tr));aa=all(a or b for a,b in zip(ag,tr))
        cont=pd.to_numeric(pd.Series([r.get('Mean_Roster_Continuity')]),errors='coerce').iloc[0]
        sex_supported.append(ss);age_supported.append(aa)
        scores.append(float(np.mean([float(ss),float(aa),float(cont)])) if pd.notna(cont) else np.nan)
    cand['Head_Sex_Path_Supported']=sex_supported;cand['Head_Age_Path_Supported']=age_supported;cand['Linkage_Score']=scores
    cand.to_parquet(path,index=False)
    for (y0,y2),g in cand.groupby(['Year_1','Year_3']):g.to_parquet(AUDIT/f'three_wave_{int(y0)}_{int(y2)}.parquet',index=False)
    rosters={};ext=[];extreme_groups=[]
    pair_diag=pd.read_parquet(ROOT/'intermediate/three_wave_validation/private/three_wave_pairwise_roster_diagnostics.parquet')
    pair_diag['Members_Lost_When_Number_Required']=pair_diag.Matched_Members-pair_diag.Number_Matched
    number_impact=pair_diag.groupby('Panel_ID').Members_Lost_When_Number_Required.sum().gt(0).to_dict()
    for cname,g in cand[cand.Sample_B].groupby('Cohort'):
        best=g.sort_values(['Linkage_Score','Address'],ascending=[False,True],na_position='last').head(100).copy()
        best['Case_Set']='Best';best['Rank']=range(1,len(best)+1)
        worst=g.sort_values(['Linkage_Score','Address'],ascending=[True,True],na_position='first').head(100).copy()
        worst['Case_Set']='Worst';worst['Rank']=range(1,len(worst)+1)
        cases=pd.concat([best,worst],ignore_index=True)
        extreme_groups.append(cases)
        years=[int(best.Year_1.iloc[0]),int(best.Year_2.iloc[0]),int(best.Year_3.iloc[0])] if len(best) else []
        if not years: continue
        for y in years:
            if y not in rosters: rosters[y]=pd.read_parquet(ROOT/f'intermediate/three_wave_validation/private/raw_roster_{y}.parquet')
            raw=rosters[y]; sel=raw[raw.Address_Raw.isin(set(cases.Address))]
            sub=cases[['Frame','Cohort','Panel_ID','Address','Case_Set','Rank','Linkage_Score']].merge(sel,left_on='Address',right_on='Address_Raw',how='inner')
            for z in sub.to_dict('records'):
                ext.append(dict(Frame=z['Frame'],Cohort=z['Cohort'],Panel_ID=z['Panel_ID'],Address=z['Address'],Case_Set=z['Case_Set'],Rank=int(z['Rank']),Linkage_Score=z['Linkage_Score'],Year=y,
                    Relationship=None if pd.isna(z.get('Relationship_Code')) else str(z.get('Relationship_Code')),
                    Sex=None if pd.isna(z.get('Sex_Code')) else str(z.get('Sex_Code')),
                    Age=pd.to_numeric(z.get('Age_Raw'),errors='coerce'),Member_Number=None if pd.isna(z.get('Member_Number')) else str(z.get('Member_Number'))))
    pd.DataFrame(ext).to_parquet(AUDIT/'panel_link_extreme_cases.parquet',index=False)
    selected=pd.concat(extreme_groups,ignore_index=True)
    summary=[]
    for (cname,case_set),g in selected.groupby(['Cohort','Case_Set']):
        flags=[]
        for _,r in g.iterrows():
            transitions=[flag(r,f'Plausible_Head_Transition_{p}') for p in ('12','23')]
            age_out=any((not flag(r,f'Head_Age_Consistent_{p}')) and not transitions[i]
                        for i,p in enumerate(('12','23'))
                        if pd.notna(r.get(f'Head_Age_Consistent_{p}')))
            sex_out=any((not flag(r,f'Head_Sex_Consistent_{p}')) and not transitions[i]
                        for i,p in enumerate(('12','23'))
                        if pd.notna(r.get(f'Head_Sex_Consistent_{p}')))
            respondent=[str(r.get(f'Respondent_Kind_{int(y)}','')) for y in (r.Year_1,r.Year_2,r.Year_3)]
            possible_substitute=any(x in ('Substitute','Ambiguous') for x in respondent)
            continuity=pd.to_numeric(pd.Series([r.get('Roster_Continuity')]),errors='coerce').iloc[0]
            low_roster=bool(pd.notna(continuity) and continuity<.25)
            roster_missing=bool(pd.isna(continuity))
            number_changed=bool(number_impact.get(r.Panel_ID,False))
            transition=any(transitions)
            unexplained=not any([transition,age_out,sex_out,possible_substitute,low_roster,roster_missing,number_changed])
            flags.append(dict(Plausible_Head_Transition=transition,Head_Age_Outside_Rule=age_out,
                Head_Sex_Mismatch_Without_Transition=sex_out,Member_Number_Affects_Matches=number_changed,
                Roster_Continuity_LT25=low_roster,Roster_Not_Measurable=roster_missing,
                Possible_Substitute_or_Ambiguous_Status=possible_substitute,No_Flag_From_Audited_Indicators=unexplained))
        fg=pd.DataFrame(flags)
        row=dict(Cohort=cname,Case_Set=case_set,N=len(g),Median_Linkage_Score=g.Linkage_Score.median(),
            Median_Roster_Continuity=g.Roster_Continuity.median())
        for col in fg.columns: row[f'{col}_Pct']=100*fg[col].mean()
        summary.append(row)
    pd.DataFrame(summary).to_csv(AUDIT/'panel_link_extreme_case_summary.csv',index=False)

def panel_report():
    repair_panel_scores_and_extremes()
    c=pd.read_csv(AUDIT/'three_wave_cohort_counts.csv')
    cand=pd.read_parquet(AUDIT/'panel_candidates_1392_1403.parquet')
    pl=pd.read_csv(AUDIT/'linkage_placebo_summary.csv')
    annual=pd.read_csv(AUDIT/'yearly_sample_summary_1392_1403.csv')
    rec=pd.read_csv(AUDIT/'within_frame_address_recurrence.csv')
    pair=pd.read_csv(AUDIT/'original_substitute_pair_comparison.csv')
    middle=pd.read_csv(AUDIT/'middlewave_nonresponse_summary.csv')
    ov=pd.read_csv(AUDIT/'cohort_overlap_integrity.csv')
    extreme_summary=pd.read_csv(AUDIT/'panel_link_extreme_case_summary.csv')
    diag_all=pd.read_parquet(ROOT/'intermediate/three_wave_validation/private/three_wave_pairwise_roster_diagnostics.parquet')
    rt=[]
    for (r0,r1),g in diag_all.groupby(['Respondent_t','Respondent_t1'],dropna=False):
        rt.append(dict(Respondent_t=r0,Respondent_t1=r1,N=len(g),Head_Sex_Consistent_Pct=100*g.Head_Sex_Consistent.mean(),
            Head_Age_Consistent_Pct=100*g.Head_Age_Consistent.mean(),Plausible_Head_Transition_N=int(g.Plausible_Head_Transition.sum()),
            Median_Roster_Continuity=g.Symmetric_Roster_Match_Rate.median(),Roster_GE50_Pct=100*g.Symmetric_Roster_Match_Rate.ge(.5).mean(),
            Roster_GE75_Pct=100*g.Symmetric_Roster_Match_Rate.ge(.75).mean()))
    response_summary=pd.DataFrame(rt)
    response_summary.to_csv(AUDIT/'response_type_quality_summary.csv',index=False)
    diag=diag_all.merge(cand[['Panel_ID','Sample_B']],on='Panel_ID',how='left')
    diag=diag[diag.Sample_B.fillna(False)].copy()
    diag['Number_Symmetric_Roster_Rate']=diag[['Number_Match_Rate_From_t','Number_Match_Rate_From_t1']].min(axis=1)
    diag['Members_Lost_When_Number_Required']=diag.Matched_Members-diag.Number_Matched
    numrows=[]
    for (coh,ya,yb),g in diag.groupby(['Cohort','Year_t','Year_t1']):
        numrows.append(dict(Cohort=coh,Year_t=ya,Year_t1=yb,N=len(g),
            Median_Without_Number=g.Symmetric_Roster_Match_Rate.median(),Median_With_Number=g.Number_Symmetric_Roster_Rate.median(),
            Pct_Households_Losing_Matches=100*g.Members_Lost_When_Number_Required.gt(0).mean(),
            Mean_Members_Lost_When_Number_Required=g.Members_Lost_When_Number_Required.mean()))
    numcmp=pd.DataFrame(numrows)
    numcmp.to_csv(AUDIT/'member_number_comparison.csv',index=False)
    cols=['Cohort','Candidate_A','Candidate_B','Candidate_C','B_Percent_of_First_Year','B_Percent_of_Theoretical_One_Third','Head_Sex_Pct','Head_Age_Pct','Head_Both_Pct','Head_Transition_Pct','Roster_Median_B','Roster_GE50_B','Roster_GE75_B','Roster_LT25_B','Level_1','Level_2','Level_3']
    headers=['Cohort','A','B','C','B / N₁','B / (N₁/3)','جنس سرپرست ثابت','مسیر سن سازگار','هر دو شرط','تغییر سرپرست توضیح‌پذیر','میانه تداوم اعضا','B ≥۵۰٪','B ≥۷۵٪','B <۲۵٪','L1','L2','L3']
    components=[]
    for cname,g in cand[cand.Sample_B].groupby('Cohort'):
        components.append(dict(Cohort=cname,Head_Sex_Pct=100*g.Head_Sex_Consistent.fillna(False).mean(),
            Head_Age_Pct=100*g.Head_Age_Consistent.fillna(False).mean(),
            Head_Both_Pct=100*(g.Head_Sex_Consistent.fillna(False)&g.Head_Age_Consistent.fillna(False)).mean(),
            Head_Transition_Pct=100*g.Plausible_Head_Transition.mean()))
    ctab=c.merge(pd.DataFrame(components),on='Cohort',how='left')
    for col in ['B_Percent_of_First_Year','B_Percent_of_Theoretical_One_Third','Roster_GE50_B','Roster_GE75_B','Roster_LT25_B']:ctab[col]=ctab[col].map(lambda x:pfmt(x))
    for col in ['Head_Sex_Pct','Head_Age_Pct','Head_Both_Pct','Head_Transition_Pct']:ctab[col]=ctab[col].map(pfmt)
    ctab['Roster_Median_B']=ctab.Roster_Median_B.map(lambda x:pfmt(100*x))
    py=pl[pl.Control.eq('Actual_Address_Same')]
    rnd=pl[pl.Control.eq('Province_Urban_Rural_Shuffle')]
    hard=pl[pl.Control.eq('Same_Cluster_Different_Address')]
    real_ro=float(py.Roster_Continuity_Mean.mean()); random_ro=float(rnd.Roster_Continuity_Mean.mean()); hard_ro=float(hard.Roster_Continuity_Mean.mean())
    real_head=float(py.Head_Path_Mean.mean()); random_head=float(rnd.Head_Path_Mean.mean()); hard_head=float(hard.Head_Path_Mean.mean())
    pvals=pl[pl.Control.ne('Actual_Address_Same')].groupby('Control').Empirical_P_Roster_GE_Actual.mean().to_dict()
    pw=pl.pivot(index=['Year_t','Year_t1'],columns='Control',values=['Roster_Continuity_Mean','Empirical_P_Roster_GE_Actual']).reset_index()
    pw.columns=['_'.join(str(x) for x in col if str(x)!='') if isinstance(col,tuple) else str(col) for col in pw.columns]
    for col in pw.columns:
        if col.startswith('Roster_Continuity_Mean_'): pw[col]=pw[col].map(lambda x:pfmt(100*x))
        if col.startswith('Empirical_P_Roster_GE_Actual_'): pw[col]=pw[col].map(lambda x:f'{float(x):.3f}')
    pw=pw.rename(columns={'Year_t':'از','Year_t1':'به','Roster_Continuity_Mean_Actual_Address_Same':'واقعی','Roster_Continuity_Mean_Province_Urban_Rural_Shuffle':'تصادفی استان/ناحیه','Roster_Continuity_Mean_Same_Cluster_Different_Address':'کنترل خوشه','Empirical_P_Roster_GE_Actual_Province_Urban_Rural_Shuffle':'p استان/ناحیه','Empirical_P_Roster_GE_Actual_Same_Cluster_Different_Address':'p خوشه'})
    placebo_table=table(pw,['از','به','واقعی','تصادفی استان/ناحیه','کنترل خوشه','p استان/ناحیه','p خوشه'],['از','به','Address واقعی','تصادفی استان/ناحیه','خوشه‌یکسان/ردیف‌دیگر','p استانی','p خوشه‌ای'])
    worst=extreme_summary[extreme_summary.Case_Set.eq('Worst')].copy()
    worst['Median_Roster_Continuity']=worst.Median_Roster_Continuity.map(lambda x:pfmt(100*x))
    worst['Median_Linkage_Score']=worst.Median_Linkage_Score.map(lambda x:f'{float(x):.3f}')
    pctcols=['Plausible_Head_Transition_Pct','Head_Age_Outside_Rule_Pct','Head_Sex_Mismatch_Without_Transition_Pct',
        'Member_Number_Affects_Matches_Pct','Roster_Continuity_LT25_Pct','Possible_Substitute_or_Ambiguous_Status_Pct',
        'No_Flag_From_Audited_Indicators_Pct']
    for col in pctcols: worst[col]=worst[col].map(pfmt)
    worst=worst.rename(columns={'Cohort':'cohort','Plausible_Head_Transition_Pct':'تغییر سرپرست قابل توضیح',
        'Head_Age_Outside_Rule_Pct':'سن بیرون از قاعده','Head_Sex_Mismatch_Without_Transition_Pct':'تغییر جنس بدون انتقال',
        'Member_Number_Affects_Matches_Pct':'شماره عضو مانع تطبیق',
        'Roster_Continuity_LT25_Pct':'تداوم اعضا زیر ۲۵٪',
        'Possible_Substitute_or_Ambiguous_Status_Pct':'جایگزین/وضعیت مبهم',
        'No_Flag_From_Audited_Indicators_Pct':'بدون پرچم تشخیصی',
        'Median_Linkage_Score':'میانه امتیاز','Median_Roster_Continuity':'میانه تداوم اعضا'})
    extreme_table=table(worst[['cohort','N','میانه امتیاز','میانه تداوم اعضا','تغییر سرپرست قابل توضیح','سن بیرون از قاعده','تغییر جنس بدون انتقال','شماره عضو مانع تطبیق','تداوم اعضا زیر ۲۵٪','جایگزین/وضعیت مبهم','بدون پرچم تشخیصی']],
        ['cohort','N','میانه امتیاز','میانه تداوم اعضا','تغییر سرپرست قابل توضیح','سن بیرون از قاعده','تغییر جنس بدون انتقال','شماره عضو مانع تطبیق','تداوم اعضا زیر ۲۵٪','جایگزین/وضعیت مبهم','بدون پرچم تشخیصی'])
    bstats=c[['Candidate_B','Level_1','Level_2','Level_3']].sum()
    explained=int(c.Plausible_Head_Transition_N.sum())
    med=float(c.Roster_Median_B.median())
    oo=diag_all[(diag_all.Respondent_t=='Original')&(diag_all.Respondent_t1=='Original')]
    subst=diag_all[(diag_all.Respondent_t=='Substitute')|(diag_all.Respondent_t1=='Substitute')]
    resp_delta=(float(oo.Symmetric_Roster_Match_Rate.mean()-subst.Symmetric_Roster_Match_Rate.mean()) if len(oo) and len(subst) else float('nan'))
    lines=['# گزارش نهایی اعتبارسنجی پنل سه‌موجی، ۱۳۹۲–۱۴۰۳','',
      '## دامنه، کلید و قاعده‌های پیش‌اعلام‌شده','',
      '۱۲ فایل خام Access برای سال‌های ۱۳۹۲ تا ۱۴۰۳ مستقیماً خوانده شد. هر سال جدول خانوار، جدول P1 اعضا و جدول‌های طراحی موجود استخراج شد. در ۱۳۹۴ و ۱۳۹۵ چهار جدول کمکی R/U فقط شامل Address و MahMorajeh بودند؛ همهٔ Addressها و MahMorajeh آن‌ها عیناً با جدول Data همان سال منطبق بود و متغیر طراحی تازه‌ای اضافه نمی‌کردند (`raw_access_auxiliary_design_table_check.csv`). Address به‌صورت رشتهٔ خام حفظ شد؛ کلید فقط `دورهٔ طراحی + Address خام` است. هیچ پیوندی میان ۱۳۹۶ و ۱۳۹۷ ساخته نشده است. دادهٔ پاک‌شدهٔ HBSIR برای ساخت کلید استفاده نشد.','',
      'دورهٔ طراحی اول ۱۳۹۲–۱۳۹۶ و دورهٔ دوم ۱۳۹۷–۱۴۰۳ است. هشت cohort سه‌موجی در جدول پایین جداگانه سنجیده شده‌اند. در تمام سال‌ها Address درون‌سالی یکتا بود و مقدار خالی نداشت.','',
      'پیش از مشاهدهٔ نتایج، سطح ۱ را با تداوم متقارن حداقل ۷۵٪ در هر یک از دو فاصله، مسیر سرپرست پذیرفتنی یا تغییر سرپرست قابل توضیح تعریف کردم. سطح ۲ همان قاعدهٔ جمعیت‌شناختی را با حداقل ۵۰٪ در هر فاصله به کار می‌برد. سطح ۳ همهٔ Addressهای سه‌موجی با وضعیت اصلی/جایگزین قابل طبقه‌بندی را نگه می‌دارد و فیلتر جمعیت‌شناختی ندارد. این‌ها طبقه‌بندی‌های ممیزی‌اند، نه پنل تأییدشده.','',
      '## دسترسی و تکرار Address','',
      table(annual[['Year','Access_Household_Rows','Access_Member_Rows','Address_Unique','Address_Duplicate_Rows','Urban','Rural']],['Year','Access_Household_Rows','Access_Member_Rows','Address_Unique','Address_Duplicate_Rows','Urban','Rural'],['سال','ردیف خانوار Access','ردیف اعضا','Address یکتا','ردیف تکراری','شهری','روستایی']),'',
      table(rec[rec.Record_Type.eq('Years_Present')].rename(columns={'Frame':'دوره طراحی','Value':'حضور در چند سال','Address_Count':'تعداد Address'})[['دوره طراحی','حضور در چند سال','تعداد Address']],['دوره طراحی','حضور در چند سال','تعداد Address']),'',
      f'در دورهٔ اول {nfmt(rec[(rec.Frame=="Frame_1392_1396") & (rec.Record_Type=="Any_gap_then_return")].Address_Count.iloc[0])} Address و در دورهٔ دوم {nfmt(rec[(rec.Frame=="Frame_1397_1403") & (rec.Record_Type=="Any_gap_then_return")].Address_Count.iloc[0])} Address بعد از وقفه بازگشته‌اند. این موارد متوازن نیستند و جدا نگه داشته شده‌اند.','',
      '## اندازهٔ cohortها و سه سطح پیشنهادی','',
      table(ctab,cols,headers),'',
      f'در کل هشت cohort، {nfmt(bstats.Candidate_B)} نامزد B، {nfmt(bstats.Level_1)} در سطح ۱، {nfmt(bstats.Level_2)} در سطح ۲ و {nfmt(bstats.Level_3)} در سطح ۳ قرار گرفتند. شناسه‌های مشترک بین cohortها در `cohort_overlap_integrity.csv` ممیزی شده‌اند؛ برای هر دوره تعداد کلیدهای واقع‌شده در چند cohort {nfmt(ov.Keys_In_Multiple_Cohorts.sum())} بود.','',
      'B تعریف شده است به‌صورت Takmil=1 در هر سه موج؛ مقدار Jaygozin خالی برای این موارد خالی باقی می‌ماند و به «خیر» تبدیل نشده است. C به معنی پاسخ وضعیت اصلی روشن است (Takmil=1)، یا Takmil=2 همراه با کد صریح ۱/۲ برای پاسخ جایگزین؛ ترکیب‌های ناقص/متناقض در C وارد نشده‌اند.','',
      '## سرپرست و ترکیب اعضا','',
      f'در نمونهٔ B، {nfmt(explained)} مشاهدهٔ cohort دارای دست‌کم یک تغییر سرپرست بودند که با تطبیق یک عضو قبلی (همسر یا فرزند) به سرپرست موج بعد قابل توضیح شد. این شمارش مشاهده در سطح cohort است؛ خانواری که در cohortهای متفاوت باشد می‌تواند بیش از یک بار شمرده شود. ناسازگاری به‌تنهایی حذف ایجاد نکرد.','',
      f'میانهٔ تداوم متقارن roster در cohortهای B به‌طور میانه {pfmt(100*med)} بود. برای هر cohort سهم B با تداوم دست‌کم ۵۰٪، ۷۵٪ و کمتر از ۲۵٪ در جدول آمده است. تطبیق اعضا حداکثر تعداد یک‌به‌یک را با جنس، سن مطابق فاصلهٔ سال‌ها و رابطهٔ یکسان/قابل‌توضیح بیشینه می‌کند.','',
      '## نمونه‌های بهترین و ضعیف‌ترین پیوند','',
      'برای هر cohort صد مورد برتر و صد مورد ضعیف‌تر از نمونهٔ B بر اساس امتیاز متوازنِ ازپیش‌تعریف‌شده انتخاب شد. جزئیات هر عضو در سه سال، فقط با رابطه، جنس، سن و شمارهٔ عضو، در `panel_link_extreme_cases.parquet` (Drive) است. جدول زیر ۱۰۰ مورد ضعیف هر cohort را با پرچم‌های تشخیصی خلاصه می‌کند. پرچم‌ها هم‌پوشان‌اند و علت قطعی یا حکم فردی نیستند: «سن بیرون از قاعده» یعنی مسیر سنی خارج از بازهٔ مجاز، بدون انتقال سرپرست قابل‌تشخیص؛ تطبیق زیر ۲۵٪ نشانگر تغییر شدید roster است؛ وضعیت جایگزین/مبهم در B عمدتاً ریسکِ تعارض کد است چون B بر Takmil=1 بنا شده است.','',
      extreme_table,'',
      'قید شمارهٔ عضو از تطبیق جمعیت‌شناختیِ بدون آن جدا سنجیده شد. جدول پایین نشان می‌دهد در هر گذار چه مقدار از matchها با این قید باقی می‌مانند و در چند درصد خانوارها شمارهٔ عضو باعث از دست‌رفتن تطبیق شده است.','',
      table(numcmp.assign(Median_Without_Number=numcmp.Median_Without_Number.map(lambda x:pfmt(100*x)),Median_With_Number=numcmp.Median_With_Number.map(lambda x:pfmt(100*x)),Pct_Households_Losing_Matches=numcmp.Pct_Households_Losing_Matches.map(pfmt)).rename(columns={'Cohort':'cohort','Year_t':'t','Year_t1':'t+1','Median_Without_Number':'بدون شماره عضو','Median_With_Number':'با شماره عضو','Pct_Households_Losing_Matches':'درصد با افت تطبیق'})[['cohort','t','t+1','N','بدون شماره عضو','با شماره عضو','درصد با افت تطبیق']],['cohort','t','t+1','N','بدون شماره عضو','با شماره عضو','درصد با افت تطبیق'],['cohort','t','t+1','N','تداوم roster بدون شماره','تداوم roster با شماره','خانوار دارای افت تطبیق']),'',
      'تفاوت پاسخ اصلی و جایگزین در جدول زیر آمده است. درصدها روی جفت Addressهای تکرارشده در cohortها محاسبه شده‌اند؛ جایگزینی می‌تواند تغییر ترکیب واقعی خانوار باشد و به‌خودی‌خود خطای Address نیست.','',
      f'در تجمیع همهٔ cohortها، میانگین تداوم متقارن برای اصلی→اصلی {pfmt(100*oo.Symmetric_Roster_Match_Rate.mean())} و برای جفت‌هایی که دست‌کم یک سوی آن‌ها جایگزین بود {pfmt(100*subst.Symmetric_Roster_Match_Rate.mean())} بود؛ اختلاف اصلی→اصلی منهای جفت جایگزین {pfmt(100*resp_delta)} واحد درصد است. این مقایسه توصیفی است و با انتخاب نمونهٔ B سازگار است اگر اختلاف مثبت و روشن باشد.','',
      table(response_summary.assign(Head_Sex_Consistent_Pct=response_summary.Head_Sex_Consistent_Pct.map(pfmt),Head_Age_Consistent_Pct=response_summary.Head_Age_Consistent_Pct.map(pfmt),Median_Roster_Continuity=response_summary.Median_Roster_Continuity.map(lambda x:pfmt(100*x)),Roster_GE50_Pct=response_summary.Roster_GE50_Pct.map(pfmt),Roster_GE75_Pct=response_summary.Roster_GE75_Pct.map(pfmt)).rename(columns={'Respondent_t':'نوع t','Respondent_t1':'نوع t+1','Head_Sex_Consistent_Pct':'جنس سرپرست','Head_Age_Consistent_Pct':'سن سرپرست','Plausible_Head_Transition_N':'تغییر توضیح‌پذیر','Median_Roster_Continuity':'تداوم roster','Roster_GE50_Pct':'roster≥۵۰٪','Roster_GE75_Pct':'roster≥۷۵٪'})[['نوع t','نوع t+1','N','جنس سرپرست','سن سرپرست','تغییر توضیح‌پذیر','تداوم roster','roster≥۵۰٪','roster≥۷۵٪']],['نوع t','نوع t+1','N','جنس سرپرست','سن سرپرست','تغییر توضیح‌پذیر','تداوم roster','roster≥۵۰٪','roster≥۷۵٪'],['از','به','N','جنس سرپرست ثابت','سن در مسیر زمان','تغییر توضیح‌پذیر','میانه roster','roster≥۵۰٪','roster≥۷۵٪']),'',
      table(pair.assign(Head_Sex_Consistent_Pct=pair.Head_Sex_Consistent_Pct.map(pfmt),Head_Age_Consistent_Pct=pair.Head_Age_Consistent_Pct.map(pfmt),Roster_GE50_Pct=pair.Roster_GE50_Pct.map(pfmt),Roster_GE75_Pct=pair.Roster_GE75_Pct.map(pfmt),Median_Roster_Continuity=pair.Median_Roster_Continuity.map(lambda x:pfmt(100*x))).rename(columns={'Respondent_t':'نوع t','Respondent_t1':'نوع t+1','Head_Sex_Consistent_Pct':'جنس سرپرست','Head_Age_Consistent_Pct':'سن سرپرست','Plausible_Head_Transition_N':'تغییر توضیح‌پذیر','Median_Roster_Continuity':'میانه تداوم','Roster_GE50_Pct':'roster≥۵۰٪','Roster_GE75_Pct':'roster≥۷۵٪'})[['نوع t','نوع t+1','N','جنس سرپرست','سن سرپرست','تغییر توضیح‌پذیر','میانه تداوم','roster≥۵۰٪','roster≥۷۵٪']],['نوع t','نوع t+1','N','جنس سرپرست','سن سرپرست','تغییر توضیح‌پذیر','میانه تداوم','roster≥۵۰٪','roster≥۷۵٪'],['از','به','N','جنس سرپرست ثابت','سن در مسیر زمان','تغییر توضیح‌پذیر','میانه roster','roster≥۵۰٪','roster≥۷۵٪']),'',
      '## عدم پاسخ موج میانی','',
      f'برای هر cohort، Addressهای حاضر در موج اول و سوم ولی غایب در موج میانی جدا شدند؛ تعداد کل این پیوندهای بازگشتی {nfmt(len(middle))} است. مشخصات پاسخ و سازگاری موج اول–سوم در `middlewave_absence_returns.parquet` (Drive) و خلاصه در `middlewave_nonresponse_summary.csv` ثبت شده است. این موارد در نمونهٔ متوازن A/B/C وارد نشده‌اند.','',
      table(middle.assign(Median_Roster_Continuity=middle.Median_Roster_Continuity.map(lambda x:pfmt(100*x)),Head_Sex_Consistent_Pct=middle.Head_Sex_Consistent_Pct.map(pfmt),Head_Age_Consistent_Pct=middle.Head_Age_Consistent_Pct.map(pfmt)).rename(columns={'Cohort':'cohort','Respondent_Kind_1':'نوع t','Respondent_Kind_3':'نوع t+2','Median_Roster_Continuity':'تداوم roster','Head_Sex_Consistent_Pct':'جنس سرپرست','Head_Age_Consistent_Pct':'سن سرپرست'})[['cohort','نوع t','نوع t+2','N','تداوم roster','جنس سرپرست','سن سرپرست']],['cohort','نوع t','نوع t+2','N','تداوم roster','جنس سرپرست','سن سرپرست'],['cohort','نوع پاسخ t','نوع پاسخ t+2','N','تداوم roster','جنس سرپرست ثابت','سن سازگار']),'',
      '## آزمون ساختگی، ۲۰۰ تکرار','',
      f'در هر یک از ۱۰ انتقال سالانهٔ درون‌دوره‌ای، ۲۰۰ بار مقایسهٔ هم‌اندازه انجام شد. جابه‌جایی اول درون استان و شهری/روستایی از روی کدهای موجود در Address خام انجام شد؛ کنترل سخت، خانوار دیگری از همان خوشه با ردیف خانوار متفاوت را گرفت و در نبود مورد، جایگزین نزدیک در همان استان/ناحیه به کار برد. میانگین تداوم roster برای Address واقعی {pfmt(100*real_ro)}، در جابه‌جایی استانی/ناحیه‌ای {pfmt(100*random_ro)} و در کنترل سخت {pfmt(100*hard_ro)} بود. مسیر سرپرست پذیرفتنی به‌ترتیب {pfmt(real_head)}، {pfmt(random_head)} و {pfmt(hard_head)} بود.','',
      f'میانگین احتمال تجربی اینکه کنترل تصادفی به تداوم roster برابر یا بالاتر از Address واقعی برسد {pfmt(100*float(pvals.get("Province_Urban_Rural_Shuffle",float("nan"))))} برای جابه‌جایی استانی/ناحیه‌ای و {pfmt(100*float(pvals.get("Same_Cluster_Different_Address",float("nan"))))} برای کنترل خوشه‌ای بود. این احتمال تجربی معیار فاصله از placebo است، نه احتمال پسین اینکه Address همان خانوار را دنبال کند.','',
      placebo_table,'',
      '![مقایسهٔ تداوم در آزمون ساختگی](linkage_placebo_roster.svg)','',
      '## نتیجه و حدود اعتبار','',
      'اختلاف Address واقعی با دو کنترل placebo، به‌همراه پیوستگی roster و پایداری سرپرست، مبنای ارزیابی هر cohort است؛ یک شاخص منفرد نتیجه‌گیری نمی‌کند. اگر Address واقعی به‌وضوح از هر دو کنترل بالاتر باشد، این شاهد قوی برای دنبال‌کردن خانوار درون آن دورهٔ طراحی است. با این حال، تکرار یک نشانی نمونه‌ای می‌تواند در بعضی موارد جایگاه/نشانی طراحی را حفظ کند، به‌ویژه هنگام عدم پاسخ یا جایگزینی؛ کدها و ترکیب اعضا برای سنجش این ریسک همراه Address گزارش شده‌اند. برای این داده‌ها احتمال عددی اینکه «Address فقط جایگاه نمونه باشد» قابل شناسایی نیست و از اختلاف placebo به‌تنهایی استخراج نمی‌شود.','',
      'استفاده از سطح ۱ یا ۲ برای تحلیل پنلی از نظر داده‌ای فقط برای cohortهایی قابل دفاع است که هم از placebo فاصلهٔ روشن دارند، هم تداوم roster و مسیر سرپرست قابل‌قبول دارند و هم جایگزینی در آن‌ها جدا کنترل می‌شود. این گزارش هیچ‌یک از سطح‌ها را خودکار انتخاب نمی‌کند. سطح ۳ برای بررسی حساسیت جایگزینی مناسب‌تر است؛ به‌تنهایی شواهد پیوند خانوار را تأمین نمی‌کند.','',
      'پروفایل سطح‌های ۱/۲/۳ شامل شهری/روستایی، کد استان استخراج‌شده از Address خام، اندازهٔ خانوار، سن و جنس سرپرست و کد خام تحصیلات `DYCOL08` در `sample_level_profiles.csv` است. مخارج غذایی محاسبه نشد، چون در خروجی‌های آماده به‌صورت جمع سالانهٔ خانوار موجود نبود و ساخت آن پردازش تازهٔ ریزدادهٔ خوراکی می‌خواست. هیچ مدل تقاضا، گروه کالایی یا قیمت گروهی ساخته نشد.','',
      'فایل‌های خانوار، نمونه‌های بهترین/بدترین و تشخیص‌های ریزداده‌ای فقط به Drive منتقل می‌شوند. GitHub فقط کد، گزارش و جدول‌های تجمیعی را نگه می‌دارد.']
    (AUDIT/'final_three_wave_panel_validation.md').write_text('\n'.join(lines),encoding='utf-8')

def main():
    tekrari_report()
    panel_report()

if __name__=='__main__':main()
