"""Read pilot Access databases without editing them; preserve all raw HH fields.

Run after extracting raw archives under intermediate/panel_forensic/<year>.
Requires MDBTools ODBC (see environment/system_dependencies.md).
Schema examples contain identifiers: publish this CSV to Drive only.
"""
from pathlib import Path
import os, json, hashlib, re, subprocess, io, shutil, zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
YEARS = [1390,1391,1392,1393,1395,1396,1397,1398]
OUT = ROOT/'audit'
WORK = ROOT/'intermediate/panel_forensic'

def extract(year):
    target=WORK/str(year);target.mkdir(parents=True,exist_ok=True)
    unrar=shutil.which('unrar') or str(ROOT/'.local/rar/usr/lib/unrar')
    subprocess.run([unrar,'x','-o-','-idq',str(ROOT/f'raw/{year}/data.rar'),str(target)+'/'],check=True)
    seen=set()
    for _ in range(6):
        todo=[p for p in target.rglob('*') if p.suffix.lower() in ['.rar','.zip'] and p not in seen]
        if not todo:break
        for p in todo:
            seen.add(p);dest=p.parent/(p.stem+'_extracted');dest.mkdir(exist_ok=True)
            if zipfile.is_zipfile(p):
                with zipfile.ZipFile(p) as z:z.extractall(dest)
            else:subprocess.run([unrar,'x','-o-','-idq',str(p),str(dest)+'/'],check=True)

def main():
    OUT.mkdir(exist_ok=True)
    structures=[]; checks=[]; manifests=[]; allcols=[]
    for y in YEARS:
        hh=[]; members=[]; inventory=[]; schema=[]
        dbs=sorted(p for p in (WORK/str(y)).rglob('*') if p.suffix.lower() in ['.mdb','.accdb'])
        if not dbs:
            extract(y)
            dbs=sorted(p for p in (WORK/str(y)).rglob('*') if p.suffix.lower() in ['.mdb','.accdb'])
        if not dbs:raise FileNotFoundError(y)
        for db in dbs:
            before=hashlib.sha256(db.read_bytes()).hexdigest()
            # Old MDB catalog metadata breaks this driver's SQLColumns. Native
            # MDBTools schema/export/count provides a separate direct-reader path.
            def cli(tool,*args):
                binary=shutil.which(tool) or str(ROOT/'.local/mdbtools/usr/bin'/tool)
                return subprocess.check_output([binary,str(db),*args],text=True)
            tables=sorted(cli('mdb-tables','-1').splitlines())
            ddl=cli('mdb-schema')
            definitions={name:[(c,t.strip()) for c,t in re.findall(r'\[([^\]]+)\]\s+([^\n,]+)',body)] for name,body in re.findall(r'CREATE TABLE \[([^\]]+)\]\s*\((.*?)\);',ddl,re.S)}
            def export(table):
                return pd.read_csv(io.StringIO(cli('mdb-export',table)),dtype='string',keep_default_na=False).replace('',pd.NA)
            for table in tables:
                cols=definitions[table]
                n=int(cli('mdb-count',table).strip())
                household= 'DATA' in table.upper() and table.upper().startswith(('R','U'))
                inventory.append(dict(Year=y,Database_File=str(db.relative_to(WORK)),Table_Name=table,Row_Count=n,Column_Count=len(cols),Household_Design_Table=household))
                for c,t in cols:
                    allcols.append(dict(Year=y,Database_File=str(db.relative_to(WORK)),Table_Name=table,Column_Name=c,Data_Type=t))
                if household:
                    frame=export(table)
                    for c,t in cols:
                        s=frame[c]; present=s.notna() & s.astype('string').str.strip().ne('')
                        schema.append(dict(Year=y,Raw_Table=table,Column_Name=c,Data_Type=t,Nonmissing_Count=int(present.sum()),Unique_Count=int(s[present].nunique()),Example_Values=json.dumps(s[present].astype(str).drop_duplicates().head(5).tolist(),ensure_ascii=False)))
                    frame['Raw_Table']=table; hh.append(frame)
                if table.upper().endswith('P1') and table.upper().startswith(('R','U')):
                    f=export(table);f['Raw_Table']=table;members.append(f)
            after=hashlib.sha256(db.read_bytes()).hexdigest()
            assert before==after
            manifests.append(dict(Year=y,Database_File=str(db.relative_to(WORK)),SHA256=before,Unmodified=True,Table_Count=len(tables)))
        pd.DataFrame(inventory).to_csv(OUT/f'raw_access_tables_{y}.csv',index=False)
        pd.DataFrame(schema).to_csv(OUT/f'raw_household_schema_{y}.csv',index=False)
        h=pd.concat(hh,ignore_index=True);m=pd.concat(members,ignore_index=True)
        # Do not strip, pad, or numerically round raw Address. Preserve source text.
        addr=next(c for c in h if c.upper()=='ADDRESS')
        h['Raw_Address']=h[addr].astype('string');h['Year']=y
        for f,name in [(h,'household'),(m,'members')]:
            # Homogeneous string serialization preserves Access scalar values and nulls.
            for c in f:
                if c!='Year': f[c]=f[c].astype('string')
            f.to_parquet(WORK/f'raw_{name}_{y}.parquet',index=False)
        standard=pd.read_parquet(ROOT/f'yearly/{y}/household.parquet')
        numeric=pd.to_numeric(h['Raw_Address'],errors='raise').astype('UInt64')
        checks.append(dict(Year=y,Raw_Households=len(h),Raw_Missing_Address=int(h.Raw_Address.isna().sum()),Standard_Households=len(standard),Raw_Duplicates=int(h['Raw_Address'].dropna().duplicated().sum()),ID_Set_Equal=set(numeric.dropna())==set(standard.ID),Raw_Numeric_To_ID_OneToOne=numeric.nunique()==h.Raw_Address.nunique()))
        for table,g in h.groupby('Raw_Table'):
            s=g.Raw_Address
            dtype=next(r['Data_Type'] for r in schema if r['Raw_Table']==table and r['Column_Name'].upper()=='ADDRESS')
            structures.append(dict(Year=y,Raw_Table=table,Address_Data_Type=dtype,Rows=len(g),Nonmissing=int(s.notna().sum()),Unique=int(s.nunique()),Length_Distribution=json.dumps({str(k):int(v) for k,v in s.str.len().value_counts().sort_index().items()}),Prefix3_Distribution=json.dumps({str(k):int(v) for k,v in s.str[:3].value_counts().sort_index().items()}),Leading_Zero_Count=int(s.str.startswith('0').sum()),Only_Digits=bool(s.str.fullmatch('[0-9]+').all()),HBSIR_Numeric_ID_Set_Equal=checks[-1]['ID_Set_Equal']))
        print(y,'tables',len(inventory),'HH',len(h),'fields',len(schema),'ID_equal',checks[-1]['ID_Set_Equal'],flush=True)
    pd.DataFrame(structures).to_csv(OUT/'address_structure_by_year.csv',index=False)
    pd.DataFrame(checks).to_csv(OUT/'raw_panel_id_integrity.csv',index=False)
    pd.DataFrame(allcols).to_csv(OUT/'raw_access_all_columns.csv',index=False)
    pd.DataFrame(manifests).to_csv(OUT/'raw_access_database_manifest.csv',index=False)

if __name__=='__main__': main()
