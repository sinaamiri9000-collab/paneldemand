"""Read original household/member/design tables from Access, 1392--1403.

The source archive is never modified. Raw extracts are private working files;
do not add the private extraction directory to Git.
"""
from pathlib import Path
import hashlib, subprocess, shutil, zipfile, re, io, json
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
YEARS=range(1392,1404)
WORK=ROOT/'intermediate/three_wave_validation'
PRIVATE=WORK/'private'
MIRROR=ROOT/'intermediate/panel_forensic'

def binary(name):return shutil.which(name) or str(ROOT/'.local/mdbtools/usr/bin'/name)
def unrar_bin():return shutil.which('unrar') or str(ROOT/'.local/rar/usr/lib/unrar')
def unpack(year):
    out=WORK/'extracted'/str(year);out.mkdir(parents=True,exist_ok=True)
    archive=ROOT/f'raw/{year}/data.rar'
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:z.extractall(out)
    else:subprocess.run([unrar_bin(),'x','-o-','-idq',str(archive),str(out)+'/'],check=True)
    seen=set()
    for _ in range(6):
        nested=[p for p in out.rglob('*') if p.suffix.lower() in ('.rar','.zip') and p not in seen]
        if not nested:break
        for p in nested:
            seen.add(p);dest=p.parent/(p.stem+'_extracted');dest.mkdir(exist_ok=True)
            if zipfile.is_zipfile(p):
                with zipfile.ZipFile(p) as z:z.extractall(dest)
            else:subprocess.run([unrar_bin(),'x','-o-','-idq',str(p),str(dest)+'/'],check=True)
    return out

def locate(year):
    places=[MIRROR/str(year),WORK/'extracted'/str(year),ROOT/'intermediate/extracted'/str(year)]
    for base in places:
        if base.exists():
            f=sorted(p for p in base.rglob('*') if p.suffix.lower() in ('.mdb','.accdb'))
            if f:return f
    base=unpack(year);f=sorted(p for p in base.rglob('*') if p.suffix.lower() in ('.mdb','.accdb'))
    if not f:raise FileNotFoundError(f'No Access database found in year {year}')
    return f

def cmd(tool,db,*args):return subprocess.check_output([binary(tool),str(db),*args],text=True)
def parse_schema(text):
    out={}
    for table,body in re.findall(r'CREATE TABLE \[([^\]]+)\]\s*\((.*?)\);',text,re.S):
        out[table]=[(c,t.strip()) for c,t in re.findall(r'\[([^\]]+)\]\s+([^\n,]+)',body)]
    return out
def export(db,table):
    return pd.read_csv(io.StringIO(cmd('mdb-export',db,table)),dtype='string',keep_default_na=False).replace('',pd.NA)
def hashfile(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()

def export_auxiliary_design_tables():
    """Export non-Data Rxx/Uxx household tables and compare their fields to Data.

    In the 1392--1403 inventories, only 1394--1395 contain these extra
    household-keyed tables; this pass verifies whether they add design fields
    absent from the household Data tables.
    """
    rows=[];extracts=[]
    for year in YEARS:
        suffix=str(year)[-2:]
        for db in locate(year):
            names=sorted(cmd('mdb-tables',db,'-1').splitlines())
            for table in names:
                if not re.fullmatch(r'[RU]'+suffix,table,re.I):continue
                side=export(db,table);side['Raw_Table']=table;side['Year']=year
                extracts.append(side)
                main_name=table+'Data'
                main=export(db,main_name)
                key=next(c for c in side.columns if c.lower()=='address')
                main_key=next(c for c in main.columns if c.lower()=='address')
                fields=[c for c in side.columns if c.lower()!=key.lower() and c in main.columns]
                joined=side.merge(main,left_on=key,right_on=main_key,how='outer',suffixes=('_Side','_Data'),indicator=True)
                exact_fields=[]
                for field in fields:
                    a=joined[f'{field}_Side'].astype('string').fillna('<NULL>')
                    b=joined[f'{field}_Data'].astype('string').fillna('<NULL>')
                    exact_fields.append(bool((joined._merge.eq('both') & a.eq(b)).all()))
                rows.append(dict(Year=year,Table=table,Rows=len(side),Columns=len(side.columns)-2,
                    Address_Unique=side[key].nunique(),Address_Duplicate_Rows=int(side[key].duplicated().sum()),
                    Main_Data_Table=main_name,Matched_Addresses=int(joined._merge.eq('both').sum()),
                    Address_Only_Side=int(joined._merge.eq('left_only').sum()),Address_Only_Data=int(joined._merge.eq('right_only').sum()),
                    Compared_Fields=';'.join(fields),All_Compared_Fields_Exact=all(exact_fields)))
    if extracts:
        pd.concat(extracts,ignore_index=True).to_parquet(PRIVATE/'raw_auxiliary_design_tables_1392_1403.parquet',index=False)
    pd.DataFrame(rows).to_csv(ROOT/'audit/raw_access_auxiliary_design_table_check.csv',index=False)
    return pd.DataFrame(rows)

def main():
    PRIVATE.mkdir(parents=True,exist_ok=True); inventories=[]; schemas=[]; sources=[]
    for year in YEARS:
        hh=[];members=[];dbpaths=locate(year)
        for db in dbpaths:
            before=hashfile(db); tables=sorted(cmd('mdb-tables',db,'-1').splitlines()); schema=parse_schema(cmd('mdb-schema',db))
            for table in tables:
                cols=schema[table]; n=int(cmd('mdb-count',db,table).strip())
                inventories.append(dict(Year=year,Database=str(db.relative_to(ROOT)),Table=table,Rows=n,Columns=len(cols)))
                for c,t in cols:schemas.append(dict(Year=year,Table=table,Column=c,Data_Type=t))
                tu=table.upper()
                if tu.startswith(('R','U')) and 'DATA' in tu:
                    d=export(db,table);d['Raw_Table']=table;hh.append(d)
                if tu.startswith(('R','U')) and tu.endswith('P1'):
                    d=export(db,table);d['Raw_Table']=table;members.append(d)
            after=hashfile(db);assert before==after
            sources.append(dict(Year=year,Database=str(db.relative_to(ROOT)),SHA256=before,Unmodified=True,Table_Count=len(tables)))
        if not hh or not members:raise AssertionError(f'Household/member table absent in {year}')
        h=pd.concat(hh,ignore_index=True);m=pd.concat(members,ignore_index=True)
        addr=next(c for c in h if c.upper()=='ADDRESS');h['Address_Raw']=h[addr].astype('string');h['Year']=year
        # Keep every raw Data column (including all design/status fields); remove
        # descriptive free-text and unrelated member data from this roster extract.
        keep=['Address','ADDRESS','address','Address_Raw','Year','Raw_Table','Takmil','Jaygozin','TakmilDescA','TakmilDescB','TakmilDescC','JaygozinDescA','JaygozinDescB','JaygozinDescC','BlkAbdJaygozin','RadifJaygozin','Fasl','MahMorajeh','Weight','weight','NoeKhn','Tekrari','Bakhsh','ShrDeh','Hozeh','BlkAbd','AbdName']
        h=h[[c for c in h if c in set(keep) or c.upper()=='ADDRESS']].copy()
        colmap={}
        for target,alternatives in [('Member_Number',['DYCOL01','Dycol01','COL01']),('Relationship_Code',['DYCOL03','Dycol03','COL03']),('Sex_Code',['DYCOL04','Dycol04','COL04']),('Age_Raw',['DYCOL05','Dycol05','COL05']),('Literacy_Raw',['DYCOL06','Dycol06','COL06']),('Education_Raw',['DYCOL08','Dycol08','COL08'])]:
            source=next((c for c in alternatives if c in m.columns),None)
            if source is None:raise KeyError((year,target,m.columns.tolist()))
            colmap[source]=target
        raw_addr=next(c for c in m if c.upper()=='ADDRESS')
        m=m[[raw_addr,*colmap]].rename(columns={raw_addr:'Address_Raw',**colmap});m['Year']=year
        h.to_parquet(PRIVATE/f'raw_household_{year}.parquet',index=False)
        m.to_parquet(PRIVATE/f'raw_roster_{year}.parquet',index=False)
        bytable=[]
        for tab,g in h.groupby('Raw_Table',dropna=False):
            a=g.Address_Raw.dropna();bytable.append(dict(Raw_Table=tab,Rows=len(g),Address_Unique=a.nunique(),Address_Duplicate_Rows=int(a.duplicated().sum()),Blank_Address=int(g.Address_Raw.isna().sum())))
        aa=h.Address_Raw.dropna()
        sources[-1].update(Household_Rows=len(h),Member_Rows=len(m),Address_Unique=int(aa.nunique()),Address_Duplicate_Rows=int(aa.duplicated().sum()),Blank_Address=int(h.Address_Raw.isna().sum()),Access_Read_Success=True)
        print(year,'Access',len(tables),'tables; household rows',len(h),'members',len(m),'design fields',len(h.columns),flush=True)
    pd.DataFrame(inventories).to_csv(WORK/'raw_access_tables_1392_1403.csv',index=False)
    pd.DataFrame(schemas).to_csv(WORK/'raw_access_schema_1392_1403.csv',index=False)
    pd.DataFrame(sources).to_csv(WORK/'raw_access_manifest_1392_1403.csv',index=False)
    pd.DataFrame(sources).to_csv(ROOT/'audit/raw_access_direct_manifest_1392_1403.csv',index=False)
    export_auxiliary_design_tables()

if __name__=='__main__':main()
