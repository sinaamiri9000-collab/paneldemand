"""Market prices for the authorized 106-item analysis basket.

No source-data writes. All sample supplies unit values and fixed Young weights.
Majumder (2012), equations (6)-(7), is implemented in levels, never log UVs.
"""
import hashlib
import numpy as np
import pandas as pd

# Verbatim REGION_BY_PROVINCE from D1_C11_FINAL_PSU_BOOTSTRAP_V2/d1_spec.py.
REGION = {1:0,2:0,27:0,23:1,30:1,25:1,26:1,0:1,20:1,13:1,
          3:2,4:2,24:2,19:2,12:3,5:3,16:3,15:3,6:3,14:3,17:3,18:3,
          9:4,28:4,29:4,7:5,10:5,21:5,8:5,11:5,22:5}
PROVINCES = ['Markazi','Gilan','Mazandaran','East_Azerbaijan','West_Azerbaijan',
 'Kermanshah','Khuzestan','Fars','Kerman','Razavi_Khorasan','Isfahan',
 'Sistan_and_Baluchestan','Kurdistan','Hamadan','Chaharmahal_and_Bakhtiari',
 'Lorestan','Ilam','Kohgiluyeh_and_Boyer_Ahmad','Bushehr','Zanjan','Semnan',
 'Yazd','Hormozgan','Tehran','Ardabil','Qom','Qazvin','Golestan',
 'North_Khorasan','South_Khorasan','Alborz']
TIERS = [['county','season_number','urban_rural'],['county','season_number'],
 ['province','season_number','urban_rural'],['province','season_number'],
 ['region','season_number'],['season_number']]

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(2**20),b''): h.update(chunk)
    return h.hexdigest()

def geography(df):
    df=df.copy()
    ad=df.address_raw.astype(str).str.replace(r'\.0$','',regex=True).str.zfill(11)
    assert ad.str.fullmatch(r'\d{11}').all()
    pc=ad.str[1:3].astype(int)
    assert (pc.map(dict(enumerate(PROVINCES)))==df.province).all()
    assert (ad.str[0].map({'1':'Urban','2':'Rural'})==df.urban_rural).all()
    df['county']=ad.str[1:5]  # HBSIR id_information.yaml County code, 1392+
    df['psu']=ad.str[:9]
    df['region']=pc.map(REGION)
    assert df.region.notna().all() and df.season_number.isin([1,2,3,4]).all()
    return df

def construct(all_df,panel,mapping,log=print):
    assert len(all_df)==438577 and len(panel)==139041 and len(mapping)==106
    assert mapping.exp_var.nunique()==106 and mapping.p_var.nunique()==106
    assert 'p_11_4' not in mapping.p_var.to_list()
    assert sorted(mapping.group_id.unique())==list(range(1,13))
    a,b=geography(all_df),geography(panel)
    e=a[mapping.exp_var].to_numpy(float)
    assert np.isfinite(e).all() and (e>=0).all()
    assert np.allclose(e.sum(1),a.exp_system_107-a.exp_11_4,rtol=1e-10,atol=1e-5)
    # Same fixed national weights as prior pipeline, using all 12 years' REAL
    # expenditures. Equal year contribution avoids changing yearly sample size.
    totals=np.zeros(len(mapping))
    for _,sub in a.groupby('year'):
        ww=sub.weight.to_numpy(float);ww=ww/ww.sum()
        totals+=ww@sub[mapping.exp_var].to_numpy(float)/12
    iw=mapping.copy();iw['national_weighted_real_expenditure']=totals
    iw['fixed_weight']=totals/iw.groupby('group_id').national_weighted_real_expenditure.transform('sum')
    assert np.allclose(iw.groupby('group_id').fixed_weight.sum(),1)
    la=np.zeros((len(a),12));lb=np.zeros((len(b),12))
    pa=np.zeros((len(a),len(mapping)),dtype=np.uint8);pb=np.zeros((len(b),len(mapping)),dtype=np.uint8)
    audit=[];failures=[]
    for year,aa in a.groupby('year',sort=True):
        ia=aa.index.to_numpy();bb=b[b.year==year];ib=bb.index.to_numpy()
        # tfexppc, head age, household size + province/urban/season.
        # Children absent in frozen clean file; do not invent a proxy or threshold.
        continuous=np.column_stack([aa.total_food_exp/aa.household_size,
                                    aa.head_age,aa.household_size]).astype(float)
        continuous=continuous/np.nanstd(continuous,axis=0)
        cat=pd.get_dummies(aa[['province','urban_rural','season_number']].astype(str),
                           drop_first=True,dtype=float).to_numpy()
        X=np.column_stack([np.ones(len(aa)),continuous,cat])
        wt=aa.weight.to_numpy(float)
        base=np.isfinite(X).all(1)&np.isfinite(wt)&(wt>0)&(aa.household_size.to_numpy()>0)
        for k,row in enumerate(iw.itertuples(index=False)):
            uv=aa[row.p_var].to_numpy(float)
            vu=np.isfinite(uv)&(uv>0)
            med=pd.Series(np.where(vu,uv,np.nan),index=aa.index).groupby(aa.psu).transform('median').to_numpy()
            ok=vu&base&np.isfinite(med)
            sw=np.sqrt(wt[ok]/np.mean(wt[ok]))
            coef,_,rank,_=np.linalg.lstsq(X[ok]*sw[:,None],(uv[ok]-med[ok])*sw,rcond=1e-11)
            if rank!=X.shape[1]:
                # Sparse items can lack a province. QR retains identified design
                # via minimum-norm LS; absent categories never predict a donor.
                log(f'price regression rank {year}/{row.p_var}: {rank}/{X.shape[1]}')
            adjusted=np.full(len(aa),np.nan)
            adjusted[ok]=med[ok]+(uv[ok]-med[ok]-X[ok]@coef)
            valid=np.isfinite(adjusted)&(adjusted>0)
            donor=aa.loc[valid,['county','province','region','season_number','urban_rural']].copy()
            donor['adjusted']=adjusted[valid]
            price_a=np.full(len(aa),np.nan);price_b=np.full(len(bb),np.nan)
            ta=np.zeros(len(aa),dtype=np.uint8);tb=np.zeros(len(bb),dtype=np.uint8)
            for tier,keys in enumerate(TIERS,1):
                cells=donor.groupby(keys).adjusted.agg(['median','count'])
                cells=cells[cells['count']>=3]
                for target,out,prov in [(aa,price_a,ta),(bb,price_b,tb)]:
                    idx=pd.MultiIndex.from_frame(target[keys]) if len(keys)>1 else pd.Index(target[keys[0]])
                    values=cells['median'].reindex(idx).to_numpy()
                    use=np.isnan(out)&np.isfinite(values)&(values>0)
                    out[use]=values[use];prov[use]=tier
            if np.isnan(price_a).any() or np.isnan(price_b).any():
                failures.append({'year':int(year),'item':row.p_var,
                  'missing_All':int(np.isnan(price_a).sum()),'missing_PanelB':int(np.isnan(price_b).sum())})
            la[ia,row.group_id-1]+=row.fixed_weight*np.log(price_a)
            lb[ib,row.group_id-1]+=row.fixed_weight*np.log(price_b)
            pa[ia,k]=ta;pb[ib,k]=tb
            audit.append({'year':int(year),'item':row.p_var,'group':int(row.group_id),
              'positive_uv':int(vu.sum()),'quality_donors':int(ok.sum()),
              'adjusted_positive':int(valid.sum()),'adjusted_nonpositive':int((ok&~valid).sum()),
              'quality_regression_rank':int(rank),'quality_regression_columns':int(X.shape[1])})
        log(f'Finished {year}: {len(mapping)} items, 6 tiers, All donors',flush=True)
    if failures:
        raise RuntimeError(f'National-season support failure; no invented prices: {failures}')
    # One donor-pool normalization for every recipient sample.
    centers=sum((sub.weight.to_numpy()/sub.weight.sum())@la[sub.index]/12 for _,sub in a.groupby('year'))
    la-=centers;lb-=centers
    assert np.isfinite(la).all() and np.isfinite(lb).all()
    tier_summary={}
    for name,pr in [('All',pa),('PanelB',pb)]:
        tier_summary[name]={
          'overall':{str(t):float(np.mean(pr==t)) for t in range(1,7)},
          'by_group':{str(g):{str(t):float(np.mean(pr[:,iw.group_id.to_numpy()==g]==t))
                             for t in range(1,7)} for g in range(1,13)},
          'by_year':{str(y):{str(t):float(np.mean(pr[(a if name=='All' else b).year.to_numpy()==y]==t))
                            for t in range(1,7)} for y in range(1392,1404)}}
    b[[f'lnp_{g}' for g in range(1,13)]]=lb
    return b, {'item_weights':iw.to_dict('records'),'price_centers':centers.tolist(),
       'quality_regressions':audit,'tiers':tier_summary,'national_failures':failures,
       'method':'fixed national Geometric Young, equal-year All survey-weighted real expenditure weights',
       'normalization':'equal-year All survey-weighted geometric mean = 1',
       'authorized_exclusion':{'code':12211,'exp_var':'exp_11_4','p_var':'p_11_4',
          'reason':'all unit values missing; user explicitly requested soda exclusion'},
       'children_omitted':'not available in frozen clean data'}
