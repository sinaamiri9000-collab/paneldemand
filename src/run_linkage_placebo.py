"""200-run geographic random and hard same-cluster placebo for raw Address links."""
from pathlib import Path
import csv
import numpy as np
import pandas as pd
from validate_three_wave_panels import load_years, frame
from validate_roster_continuity import pair_result, roster_map

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'audit'
RUNS=200
SAMPLE_PER_RUN=100
SEED=20261006

def summarize(items, transition, run, kind, fallbacks=0):
    if not items:return dict(Year_t=transition[0],Year_t1=transition[1],Run=run,Control=kind,N=0,Hard_Placebo_Fallbacks=fallbacks)
    df=pd.DataFrame(items)
    headpath=[bool((r['Head_Sex_Consistent'] and r['Head_Age_Consistent']) or r['Plausible_Head_Transition']) for r in items]
    return dict(Year_t=transition[0],Year_t1=transition[1],Run=run,Control=kind,N=len(items),
        Head_Sex_Consistent_Pct=100*df.Head_Sex_Consistent.mean(),Head_Age_Consistent_Pct=100*df.Head_Age_Consistent.mean(),
        Plausible_Head_Transition_Pct=100*df.Plausible_Head_Transition.mean(),Head_Path_Acceptable_Pct=100*np.mean(headpath),
        Roster_Continuity_Mean=df.Symmetric_Roster_Match_Rate.mean(),Roster_Continuity_Median=df.Symmetric_Roster_Match_Rate.median(),
        Roster_GE50_Pct=100*df.Symmetric_Roster_Match_Rate.ge(.5).mean(),Roster_GE75_Pct=100*df.Symmetric_Roster_Match_Rate.ge(.75).mean(),
        Roster_LT25_Pct=100*df.Symmetric_Roster_Match_Rate.lt(.25).mean(),Hard_Placebo_Fallbacks=fallbacks)

def shuffled_targets(sampled, base, pool_by_region, rng):
    groups={}
    for a in sampled:
        row=base.loc[a];key=(str(row.Province_Code),str(row.Urban_Rural))
        groups.setdefault(key,[]).append(str(a))
    out={}
    for key,src in groups.items():
        pool=pool_by_region.get(key,[])
        if not pool: continue
        replace=len(pool)<len(src)
        dest=np.asarray(rng.choice(pool,size=len(src),replace=replace),dtype=object)
        # A randomized within-stratum permutation should not retain a true raw
        # Address match. Rotate collisions within the same stratum.
        for _ in range(len(dest)):
            if not any(str(dest[i])==src[i] for i in range(len(src))): break
            dest=np.roll(dest,1)
        for a,b in zip(src,dest):
            if str(a)!=str(b): out[a]=str(b)
    return out

def main():
    records=load_years()
    rng=np.random.default_rng(SEED)
    result=[]
    transitions=[(y,y+1) for y in range(1392,1396)]+[(y,y+1) for y in range(1397,1403)]
    for y0,y1 in transitions:
        t0,t1=records[y0],records[y1]
        common=sorted(set(t0.index)&set(t1.index))
        maps={y0:roster_map(y0),y1:roster_map(y1)}
        target=list(t1.index)
        region_pool={}
        cluster_pool={}
        for a,row in t1.iterrows():
            reg=(str(row.Province_Code),str(row.Urban_Rural))
            region_pool.setdefault(reg,[]).append(str(a))
            cluster_pool.setdefault(str(row.Cluster_Code),[]).append(str(a))
        actual_cache={}
        if not common: continue
        sample_n=min(SAMPLE_PER_RUN,len(common))
        for run in range(1,RUNS+1):
            sampled=rng.choice(common,size=sample_n,replace=False).tolist()
            for a in sampled:
                if a not in actual_cache: actual_cache[a]=pair_result(maps[y0].get(a),maps[y1].get(a),1)
            actual=[actual_cache[a] for a in sampled]
            result.append(summarize(actual,(y0,y1),run,'Actual_Address_Same'))
            region=[]
            dests=shuffled_targets(sampled,t0,region_pool,rng)
            for a,b in dests.items():
                region.append(pair_result(maps[y0].get(str(a)),maps[y1].get(str(b)),1))
            result.append(summarize(region,(y0,y1),run,'Province_Urban_Rural_Shuffle'))
            hard=[];fallback=0
            for a in sampled:
                row=t0.loc[a];cluster=str(row.Cluster_Code)
                choices=[b for b in cluster_pool.get(cluster,[]) if b!=str(a)]
                if not choices:
                    fallback+=1
                    pool=region_pool.get((str(row.Province_Code),str(row.Urban_Rural)),[])
                    choices=[b for b in pool if b!=str(a)]
                if choices:
                    b=str(rng.choice(choices));hard.append(pair_result(maps[y0].get(str(a)),maps[y1].get(b),1))
            result.append(summarize(hard,(y0,y1),run,'Same_Cluster_Different_Address',fallback))
        print(f'{y0}-{y1}: {len(common)} real recurring Address; {RUNS} randomized runs',flush=True)
    df=pd.DataFrame(result)
    df.to_csv(AUDIT/'linkage_placebo_test.csv',index=False)
    rows=[]
    for (y0,y1,kind),g in df.groupby(['Year_t','Year_t1','Control']):
        rows.append(dict(Year_t=y0,Year_t1=y1,Control=kind,Simulation_Runs=int(g.Run.nunique()),
            N_Median=float(g.N.median()),Head_Path_Mean=float(g.Head_Path_Acceptable_Pct.mean()),
            Roster_Continuity_Mean=float(g.Roster_Continuity_Mean.mean()),Roster_GE50_Mean=float(g.Roster_GE50_Pct.mean()),
            Roster_GE75_Mean=float(g.Roster_GE75_Pct.mean()),Roster_LT25_Mean=float(g.Roster_LT25_Pct.mean()),
            Hard_Fallback_Median=float(g.Hard_Placebo_Fallbacks.median())))
    summary=pd.DataFrame(rows)
    # Empirical tail probabilities compare randomization runs against the mean
    # same-Address result for the same year transition.
    for (y0,y1),g in df.groupby(['Year_t','Year_t1']):
        real=g[g.Control.eq('Actual_Address_Same')]
        if real.empty:continue
        ro=float(real.Roster_Continuity_Mean.mean()); hp=float(real.Head_Path_Acceptable_Pct.mean())
        for kind in ('Province_Urban_Rural_Shuffle','Same_Cluster_Different_Address'):
            ix=(summary.Year_t==y0)&(summary.Year_t1==y1)&(summary.Control==kind)
            placebo=g[g.Control.eq(kind)]
            summary.loc[ix,'Actual_Roster_Mean']=ro
            summary.loc[ix,'Actual_Head_Path_Pct']=hp
            summary.loc[ix,'Empirical_P_Roster_GE_Actual']=(1+(placebo.Roster_Continuity_Mean>=ro).sum())/(1+len(placebo))
            summary.loc[ix,'Empirical_P_Head_GE_Actual']=(1+(placebo.Head_Path_Acceptable_Pct>=hp).sum())/(1+len(placebo))
    summary.to_csv(AUDIT/'linkage_placebo_summary.csv',index=False)
    # Dependency-free SVG line charts keep all ten design-valid transitions visible.
    srows=list(csv.DictReader((AUDIT/'linkage_placebo_summary.csv').open(encoding='utf-8')))
    controls=[('Actual_Address_Same','#176b4d','Address یکسان'),('Province_Urban_Rural_Shuffle','#c5533d','جابه‌جایی استان/ناحیه'),('Same_Cluster_Different_Address','#496caa','خوشه یکسان، ردیف دیگر')]
    transitions=sorted({(int(r['Year_t']),int(r['Year_t1'])) for r in srows})
    for metric,title,filename,scale in [('Roster_Continuity_Mean','میانگین نرخ تطبیق متقارن اعضا','linkage_placebo_roster.svg',1.0),('Head_Path_Mean','درصد مسیر سرپرست پذیرفتنی','linkage_placebo_head.svg',100.0)]:
        width,height=1000,520;left,right,top,bottom=90,40,70,115;pw=width-left-right;ph=height-top-bottom
        svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',f'<text x="{width/2}" y="34" text-anchor="middle" font-size="20" font-family="sans-serif">{title} ـ ۲۰۰ تکرار برای هر انتقال</text>']
        for tick in range(6):
            value=tick/5*scale;y=top+ph-tick/5*ph
            svg.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#ddd"/>')
            svg.append(f'<text x="{left-12}" y="{y+5:.1f}" text-anchor="end" font-size="12" font-family="sans-serif">{value:.0f}%</text>' if scale==100 else f'<text x="{left-12}" y="{y+5:.1f}" text-anchor="end" font-size="12" font-family="sans-serif">{value:.1f}</text>')
        for i,(a,b) in enumerate(transitions):
            x=left+(i/(max(1,len(transitions)-1)))*pw
            svg.append(f'<text x="{x:.1f}" y="{top+ph+25}" text-anchor="middle" font-size="11" font-family="sans-serif">{a}–{b}</text>')
        for j,(control,color,label) in enumerate(controls):
            points=[]
            for i,(a,b) in enumerate(transitions):
                row=next((r for r in srows if int(r['Year_t'])==a and int(r['Year_t1'])==b and r['Control']==control),None)
                if not row or not row.get(metric):continue
                value=float(row[metric])
                x=left+(i/(max(1,len(transitions)-1)))*pw;y=top+ph-(value/scale)*ph
                points.append((x,y))
            if points:
                svg.append('<polyline fill="none" stroke="'+color+'" stroke-width="3" points="'+' '.join(f'{x:.1f},{y:.1f}' for x,y in points)+'"/>')
                for x,y in points:svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
            lx=left+5+j*300
            svg.append(f'<line x1="{lx}" y1="{height-28}" x2="{lx+25}" y2="{height-28}" stroke="{color}" stroke-width="3"/><text x="{lx+32}" y="{height-23}" font-size="13" font-family="sans-serif">{label}</text>')
        svg.append('</svg>')
        (AUDIT/filename).write_text('\n'.join(svg),encoding='utf-8')

if __name__=='__main__':main()
