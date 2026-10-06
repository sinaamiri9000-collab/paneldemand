"""Build Persian reports and safe aggregate schemas; never publish schema examples."""
from audit_raw_panel_identifiers import ROOT, WORK, OUT, YEARS
from build_panel_key import frame
from pathlib import Path
from collections import Counter
import pandas as pd
import json,hashlib

def write(name,text): (OUT/name).write_text(text,encoding='utf-8')
def md(df):
    cols=list(df.columns)
    return '| '+' | '.join(cols)+' |\n| '+' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(str(x) for x in r)+' |' for r in df.itertuples(index=False,name=None))

def main():
    meaning={'Address':'آدرس/کلید رکورد نمونه؛ شناسه دائمی شخص یا خانواده اثبات نشده','MahMorajeh':'ماه مراجعه','Fasl':'فصل مراجعه','weight':'وزن نمونه','NoeKhn':'نوع خانوار','Takmil':'پرسشنامه برای خانوار اصلی تکمیل شده؟','Jaygozin':'پرسشنامه برای خانوار جایگزین تکمیل شده؟','TakmilDescA':'کد جدول وضعیت عدم تکمیل خانوار اصلی؛ تفسیر دقیق کد نیازمند تطبیق راهنما','TakmilDescB':'علت عدم تکمیل خانوار اصلی؛ جدول وضعیت مکان','TakmilDescC':'توضیح متنی علت عدم تکمیل؛ ممکن است اطلاعات هویتی داشته باشد','JaygozinDescA':'کد جدول وضعیت عدم تکمیل خانوار جایگزین؛ تفسیر دقیق کد نیازمند تطبیق راهنما','JaygozinDescB':'علت عدم تکمیل خانوار جایگزین؛ جدول وضعیت مکان','JaygozinDescC':'توضیح متنی عدم تکمیل جایگزین؛ ممکن است اطلاعات هویتی داشته باشد','BlkAbdJaygozin':'شماره بلوک یا کد آبادی جایگزین','RadifJaygozin':'ردیف خانوار جایگزین در واحد نمونه اولیه/خوشه','ShoghlSarparast':'شغل/وضع فعالیت سرپرست، متن آزاد','Bakhsh':'بخش','ShrDeh':'شهر/دهستان','Hozeh':'حوزه','BlkAbd':'بلوک/آبادی','AbdName':'نام آبادی','Tekrari':'عنوان تکراری؛ تعریف دقیق و دلالت طولی از اسناد موجود احراز نشد'}
    schemas=[];docs=[];rawcounts=[];parts=[]
    for y in YEARS:
        p=OUT/f'raw_household_schema_{y}.csv';s=pd.read_csv(p)
        s['Meaning']=s.Column_Name.map(meaning).fillna('معنی رسمی بازیابی نشد؛ فیلد اجرایی/کنترلی، بدون فرض هویت پنلی')
        s['Meaning_Evidence']=s.Column_Name.map(lambda c:'پرسشنامه همان سال، صفحه ۱ و ۲؛ راهنمای خام موجود، با تطبیق عنوان' if c in meaning and c!='Tekrari' else 'نامشخص؛ وارد کلید نمی‌شود')
        s.to_csv(p,index=False);schemas.append(s.drop(columns='Example_Values'))
        rawcounts.append(dict(Year=y,Tables=len(pd.read_csv(OUT/f'raw_access_tables_{y}.csv')),Household_Fields=s.Column_Name.nunique()))
        h=pd.read_parquet(WORK/f'raw_household_{y}.parquet');a=h.Raw_Address.dropna()
        for component,sl,ev in [('Urban_Rural',(0,1),'پرسشنامه صفحه۱ و HBSIR id_information'),('Province',(1,3),'پرسشنامه صفحه۱ و HBSIR id_information'),('County',(3,5),'از۱۳۹۲: دو رقم شهرستان درون استان؛ قبل آن از Address به‌تنهایی قابل استخراج نیست'),('PSU_or_Cluster',(3,7) if y<1392 else (5,9),'۱۳۹۰–۱۳۹۶ واحد نمونه اولیه؛ از۱۳۹۷ خوشه، از چینش پرسشنامه استنباط می‌شود'),('Household_Row',(7,10) if y<1392 else (9,11),'چینش پرسشنامه و طول خام؛ نگاشت رسمی ردیف به گروه چرخش در دسترس نیست')]:
            if component=='County' and y<1392:continue
            z=a.str[sl[0]:sl[1]];parts.append(dict(Year=y,Component=component,Start_0based=sl[0],End_Exclusive=sl[1],Unique_Count=z.nunique(),Evidence=ev,Verified_Against_Independent_Raw_Column=False))
        for p in sorted((WORK/str(y)).rglob('*.pdf')):
            docs.append(dict(Year=y,File=str(p.relative_to(WORK)),SHA256=hashlib.sha256(p.read_bytes()).hexdigest(),Bytes=p.stat().st_size,Role='questionnaire' if 'question' in p.name.lower() or 'پرسشنامه' in p.name else 'raw_guide'))
    pd.concat(schemas).to_csv(OUT/'raw_household_schema_summary.csv',index=False)
    pd.DataFrame(parts).to_csv(OUT/'address_component_interpretation.csv',index=False)
    pd.DataFrame(docs).to_csv(OUT/'panel_forensic_document_manifest.csv',index=False)
    pd.DataFrame(rawcounts).to_csv(OUT/'raw_access_pilot_summary.csv',index=False)
    original=pd.read_csv(ROOT/'metadata/raw_sources.csv')
    archives=json.loads((WORK/'local_source_archives.json').read_text())
    # Existing Drive source manifest is the provenance of these local archive copies.
    drive=pd.read_csv(ROOT/'metadata/drive_file_manifest.csv')
    for r in archives:
        match=drive[drive.iloc[:,0].eq(r['Archive'])]
        assert len(match)==1
        sha_col=next(c for c in drive if 'sha' in c.lower());assert match.iloc[0][sha_col]==r['SHA256']
        r['Matches_Previous_Drive_Manifest']=True
    pd.DataFrame(archives).to_csv(OUT/'panel_forensic_source_archive_check.csv',index=False)
    # Full-period label reuse diagnostic, without certifying or extending a panel.
    history=pd.read_parquet(OUT/'panel_household_history.parquet');length=Counter();over=[]
    for r in history.itertuples():
        ys=list(map(int,r.Years_Present.split(';')));co=Counter(frame(y) for y in ys);length.update(co.values())
        if len(ys)>3:over.append(dict(ID=r.ID,Design_Periods=';'.join(co),Max_Years_Within_Period=max(co.values()),Observed_Years=len(ys),Years_Present=r.Years_Present))
    over=pd.DataFrame(over);over.to_parquet(OUT/'id_over_three_frame_decomposition.parquet',index=False)
    pd.DataFrame([dict(Method='Frame_Address',Observed_Years=k,Keys=v,Scope='existing_14year_label_diagnostic_not_certified_panel') for k,v in sorted(length.items())]).to_csv(OUT/'panel_frame_scoped_length_diagnostic.csv',index=False)
    triple=pd.read_parquet(OUT/'three_wave_panels.parquet');cohorts=[]
    for y in range(1390,1402):
        cohorts.append(dict(Cohort=f'{y}-{y+2}',Crosses_Frame_Boundary=frame(y)!=frame(y+2),Existing_Address_Candidate_Count=int(triple.start_year.eq(y).sum()),Validated_Family_Count=None,Status='boundary_no_continuous_key' if frame(y)!=frame(y+2) else 'not_certified; missing_full_three_wave_raw_pilot_coverage'))
    pd.DataFrame(cohorts).to_csv(OUT/'panel_three_wave_cohort_status.csv',index=False)
    iddoc='''# ساخت ID در HBSIR

نسخه بررسی‌شده HBSIR 0.6.6، commit `e5b3e5d5146ccf76af3e3068c0fc12fa7b4b678f`؛ BSSIR 0.6.8.

- فایل `src/hbsir/metadata/tables.yaml`: نگاشت `global_address` نام جدید `ID` و نوع `UInt64` را تعیین می‌کند. ستون `ADDRESS` در `household_information` و `members_properties` به همین نگاشت ارجاع می‌دهد. انتخاب خانوار از الگوی `*Data*` است.
- تبدیل در BSSIR، فایل `bssir/data_cleaner.py`، توابع `_apply_metadata_to_table`، `_apply_metadata_to_column` و `_apply_type_to_column` انجام می‌شود. نام جدید از `new_name` گرفته می‌شود؛ سپس `_general_cleaning` و `astype('UInt64', errors='raise')` اجرا می‌شوند.
- `_general_cleaning` فاصله و برخی نشانه‌های اضافی را پاک می‌کند، `.0` انتهایی را حذف و مقدار خالی را null می‌کند. بنابراین عبارت «کاملاً بدون تغییر» در سطح نوع/رشته دقیق نیست؛ در سطح عدد برای هر هشت سال برابری کامل مشاهده شد. صفر ابتدایی در تبدیل عددی قابل حفظ نیست، اما در Address غیرخالی این هشت سال هیچ صفر ابتدایی مشاهده نشد؛ نسخه خام متنی جدا حفظ شده است.
- فایل `src/hbsir/metadata/schema.yaml` برای خانوار `add_year` و `dropna: ID` دارد؛ قطع یا بازشماره‌گذاری ID ندارد. ۱۳۹۰ یک ردیف خام با Address خالی دارد و طبق همین قاعده در استاندارد نیست: ۴۰٬۰۱۱ در خام، ۴۰٬۰۱۰ در خروجی. هیچ ID غیرخالی گم نشده است.
- قواعد ساخت ID در هشت سال تغییر ندارند؛ تغییر طول کد از داده خام می‌آید. `id_information.yaml` از۱۳۸۷ طول۱۰ و از۱۳۹۲ طول۱۱ و موقعیت استان/شهری‌روستایی را ثبت می‌کند؛ شهرستان پیش از۱۳۹۲ از جدول خارجی و پس از آن از موقعیت۱ تا۵ استخراج می‌شود. این فایل معرف دائمی بودن خانوار نیست.
- `src/hbsir/schema_functions/standard_tables.py::adjust_month` ماه۱ را۱۳ کرده و سپس۱ کم می‌کند؛ قاعده سالنامه آمارگیری اردیبهشت تا فروردین را برای نمایش ماه اعمال می‌کند. ممیزی حاضر ماه خام را نگه می‌دارد.

شواهد عددی: `raw_panel_id_integrity.csv` و `address_structure_by_year.csv`. پنج متغیر خام اعضا (Address، ردیف، رابطه، جنس، سن) در هشت سال به‌صورت چندمجموعهٔ کامل با نسخه استاندارد برابرند؛ مقایسه در `validate_panel_links.py::raw_members` اجرا شده است.

منبع کد HBSIR: https://github.com/Iran-Open-Data/HBSIR/tree/e5b3e5d5146ccf76af3e3068c0fc12fa7b4b678f/src/hbsir/metadata
'''
    write('hbsir_id_construction.md',iddoc)
    frame_report='''# تغییر چارچوب و قالب شناسه

## شواهد مستقیم اولیه

پرسشنامه‌های رسمی داخل آرشیو همان هشت سال، صفحه۱ و۲، بررسی شدند. پرسشنامه۱۳۹۱ واحد نمونه‌گیری اولیه در نمونه پایه، گروه چرخش، طبقه، ردیف فهرست‌برداری و ردیف در واحد اولیه را دارد. پرسشنامه۱۳۹۲ شهرستان را به چینش کد ترکیبی اضافه می‌کند و شماره خوشه/طبقه را جدا روی فرم چاپی دارد. در۱۳۹۷ چینش چاپی از «واحد نمونه اولیه» به «شماره خوشه» تغییر عنوان می‌دهد. این خانه‌های فرم الزاماً ستون مستقل در Access منتشرشده نیستند.

طول Address در۱۳۹۰–۱۳۹۱ دقیقاً۱۰ و از۱۳۹۲ در سال‌های آزمایشی دقیقاً۱۱ است؛ نوع آن Text است. برداشت چینش: پیش از۱۳۹۲ شهری/روستایی۱ + استان۲ + واحد اولیه۴ + ردیف۳؛ از۱۳۹۲ شهری/روستایی۱ + استان۲ + شهرستان۲ + واحد اولیه/خوشه۴ + ردیف۲. ماه مراجعه جدا از Address ذخیره می‌شود. طول و موقعیت استان/شهرستان با metadata HBSIR سازگار است؛ برای بقیه اجزا ستون مستقل یا جدول نگاشت رسمی موجود نیست و برداشت از فرم، تضمین تعریف یا پایداری طولی آن اجزا نیست.

در۱۳۹۲–۱۳۹۵ پنج ستون مکانی Bakhsh/ShrDeh/Hozeh/BlkAbd/AbdName نیز در Data منتشر شده‌اند؛ در۱۳۹۶ به بعد در Data موجود نیستند. از۱۳۹۶ وزن و فصل اضافه می‌شود. ردیف جایگزین و بلوک/آبادی جایگزین در همه سال‌های آزمایشی وجود دارند. هیچ جدول یا ستون مستقل دارای عنوان گروه چرخش/طبقه/خوشه برای ساخت نگاشت طولی دقیق پیدا نشد؛ تمامی ستون‌ها در `raw_access_all_columns.csv` فهرست شده‌اند.

## شواهد روش‌شناختی ثانویه و حد اطمینان

[راهنمای عملی HEIS، فصل۱](https://m-hoseini.github.io/HEIS/introduction.html) دوره‌های۱۳۸۹–۱۳۹۱،۱۳۹۲–۱۳۹۶ و۱۳۹۷ به بعد را جدا معرفی می‌کند. [مستندات HBSIR](https://iran-open-data.github.io/HBSIR/data/) نیز جدول الگوی چرخش را در همین سه دوره ارائه می‌دهد. جدول انگلیسی یک اشتباه چاپی B1/B1 و صفحه فارسی فرمول‌های اشتباه دارد؛ از این رونویسی‌ها برای تعیین گروه واقعی هر ردیف استفاده نشده است.

این دو منبع سند اصلی امضاشده طراحی مرکز آمار نیستند. نسخه رسمی کامل طراحی/جدول تطبیق چارچوب‌های قبل و بعد در آرشیوهای آزمایشی یافت نشد. تلاش دریافت گزارش از `amar.22n.ir/ftp/amar/hb/hb-rostayi-95.pdf` به پاسخ غیرPDF۲۱۶بایتی انجامید. شرح IHSN تولیدکننده مرکز آمار را معرفی و نمونه‌گیری سه‌مرحله‌ای را شرح می‌دهد اما تغییر دو مرز را اثبات نمی‌کند: https://catalog.ihsn.org/catalog/10337/study-description . پس دوره‌های پایه با شواهد ثانویه و قرائن مستقیم بسیار سازگارند، ولی حکم مطلق «هیچ خانواده واقعی دو بار انتخاب نمی‌شود» از این منابع نتیجه نمی‌شود.

## حکم عملی

دو مرز فاقد کلید مشترک قابل اثبات‌اند و نباید به‌عنوان ادامهٔ همان پنل پیوند داده شوند. تغییر طول۱۳۹۲ علت مکانیکی صفر بودن Address کامل است؛۱۳۹۷ طول ثابت است اما مجموعه کدهای نمونه/ردیف‌ها از نو شروع می‌شود. حذف رقم، برش کد یا تطبیق جمعیت‌شناختی برای عبور از مرز توجیه طراحی ندارد. عبور فیزیکی اتفاقی همان خانواده بین دو نمونه ممکن است، اما از انتشار عمومی قابل اثبات نیست.
'''
    write('sampling_frame_change_report.md',frame_report)
    for a,b in [(1391,1392),(1396,1397)]:
        h1=pd.read_parquet(WORK/f'raw_household_{a}.parquet').Raw_Address.dropna();h2=pd.read_parquet(WORK/f'raw_household_{b}.parquet').Raw_Address.dropna()
        content=f'''# ممیزی مرز {a}→{b}

- همپوشانی ID استاندارد و Address خام، هر دو: **{len(set(h1)&set(h2))}**؛ منشأ صفر شدن تبدیل HBSIR نیست.
- طول متن Address: {sorted(h1.str.len().unique().tolist())}→{sorted(h2.str.len().unique().tolist())}؛ تمام مقدارهای غیرخالی متن رقمی‌اند.
- تغییر قالب: {'۱۰ به۱۱ رقم؛ اضافه شدن شهرستان و تغییر اندازه ردیف در چینش فرم.' if a==1391 else 'طول۱۱ ثابت؛ عنوان واحد اولیه در فرم به خوشه تغییر می‌کند و دامنه کدهای نمونه/ردیف از نو شروع می‌شود.'}
- گروه چرخش روی پرسشنامه هست اما ستون مستقلی برای آن منتشر نشده است. بلوک و ردیف جایگزین شناسه جایگزین درون همان نمونه‌اند و نگاشت بین چارچوب‌ها نیستند.
- منابع روش‌شناختی دوره چرخش تازه را در {b} نشان می‌دهند؛ همراه با نبود کلید مشترک، هیچ مبنای معتبر برای ساخت پیوند طولی بین این دو نمونه نداریم.
- ادعای مطلق ممنوعیت انتخاب دوباره یک خانواده به سند رسمی کامل نیاز دارد؛ این سند به دست نیامد. نتیجه ممیزی: اتصال بین دو سوی مرز **نامشخص و غیرقابل تأیید**، نه تطبیق حدسی.

برای منشأ شواهد و محدودیت‌ها `sampling_frame_change_report.md` را ببینید.
'''
        write(f'boundary_{a}_{b}_report.md',content)
    validation=pd.read_csv(OUT/'panel_link_demographic_validation.csv');overlap=pd.read_csv(OUT/'panel_key_candidate_overlap.csv')
    v=validation[(validation.Method=='Respondent_Location')&(validation.Links>0)].copy()
    table=v[['Year_t','Year_next','Links','Head_Age_Consistent_Rate','Head_Sex_Consistent_Rate','Head_Both_Consistent_Rate','Head_Age_Time_Plausible_Rate']].copy()
    for c in table.columns:
        if c.endswith('Rate'):table[c]=table[c].map(lambda z:f'{100*z:.2f}%')
    summ=json.loads((OUT/'id_over_three_years_summary.json').read_text())
    status={'Direct_Raw_Pilot_Completed':True,'Pilot_Years':YEARS,'Candidate_Methods':5,'Pilot_Key_Certified':False,'Full_Raw_Expansion_Performed':False,'Crosswalk_Created':False,'Validated_Three_Wave_File_Created':False,'Validated_Family_Count':None,'Reason':'Population identity and rotation assignments remain unproven; demographic conflicts substantial. Conditional outputs withheld per request.', '353_Labels_Appear_In_Two_Frames':bool(len(over)==353 and over.Design_Periods.eq('1392;1397').all()),'Max_Observed_Years_Per_Frame':int(over.Max_Years_Within_Period.max()),'Existing_Three_Wave_Candidates':len(triple),'Prior_Outputs_Overwritten':False}
    (OUT/'panel_forensic_completion_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
    report=f'''# ممیزی مستقیم شناسه پنلی طرح هزینه و درآمد خانوار

تاریخ: ۷ اکتبر۲۰۲۶؛ ادامه پروژه paneldemand. نتیجه: **اصلاح کلید با دوره طراحی ضروری است، اما هویت طولی خانواده هنوز برای پذیرش خودکار پنل اثبات نشده است.**

## دامنه و شواهد اجرا

هشت سال۱۳۹۰،۱۳۹۱،۱۳۹۲،۱۳۹۳،۱۳۹۵،۱۳۹۶،۱۳۹۷،۱۳۹۸ واقعاً از Access خوانده شدند: مجموع {sum(r['Tables'] for r in rawcounts)} جدول، همه نام‌ها/نوع ستون‌ها و شمار رکوردها استخراج شد. خواندن با MDBTools1.0.1، ابزارهای mdb-tables/schema/count/export انجام شد؛ SQLColumns در ODBC فایل‌های قدیمی خطا داد و مسیر بومی MDBTools موفق شد. آرشیوهای محلی همان نسخه‌های مرحله پیشین Drive هستند و SHA-256 هر هشت با فهرست قبلی Drive برابر است؛ دوباره از آینه دانلود نشدند. هش پایگاه قبل و بعد برابر بود؛ فایل خام تغییر نکرد.

{md(pd.DataFrame(rawcounts))}

در تمام سال‌ها مجموعه Address غیرخالی پس از تبدیل عددی دقیقاً با ID استاندارد برابر است. در۱۳۹۰ یک ردیف Address خالی هست و استاندارد طبق `dropna: ID` آن را ندارد. پنج ستون پایه اعضا نیز از خام به‌صورت چندمجموعه کامل با استاندارد تطبیق داده شدند؛ تمام هشت مقایسه موفق بود.

## ۱ و۲. ID چیست و آیا دائمی است؟

ID همان Address خام پس از پاکسازی عمومی قالب و تبدیل UInt64 است، نه شناسه جدید استخراج‌شده از متغیرهای جمعیت‌شناختی. قواعد تبدیل در سال‌ها ثابت‌اند؛ جزئیات تابع/فایل در `hbsir_id_construction.md` است. Address کلید واحد/جایگاه نمونه است و تکرارش به‌تنهایی هویت دائمی خانواده پاسخ‌دهنده را اثبات نمی‌کند، به‌ویژه با جایگزینی و تغییر چارچوب. نسخه متنی خام برای جلوگیری از حذف صفر حفظ شده؛ در Addressهای این هشت سال صفر ابتدایی مشاهده نشد، اما در بلوک و ردیف جایگزین وجود دارد و حفظ شد.

## ۳. علت مرزهای صفر

۱۳۹۱→۱۳۹۲: Address از۱۰ به۱۱ رقم تغییر می‌کند و مجموعه‌های رشته کامل هم اشتراک ندارند. ۱۳۹۶→۱۳۹۷: طول۱۱ ثابت است؛ شماره‌های واحد نمونه/ردیف و دوره طراحی تغییر می‌کنند. در هر دو مرز Address خام و ID استاندارد صفرند؛ باگ تبدیل HBSIR نیست. منابع روش‌شناختی سه دوره۱۳۸۹–۱۳۹۱،۱۳۹۲–۱۳۹۶،۱۳۹۷ به بعد را معرفی می‌کنند. پرسشنامه‌های رسمی و فهرست خام قرائن مستقیم این تغییر را نشان می‌دهند، اما نسخه رسمی کامل نگاشت چارچوب‌ها یافت نشد. حکم عملی: از مرزها پیوند ساخته نشود؛ حکم مطلق درباره امکان انتخاب اتفاقی همان خانواده اثبات نشده است.

## ۴. متغیرهای بیشتر در خام

نام هیچ ستون خانوار حذف نشد. Takmil/Jaygozin، دلایل عدم تکمیل، بلوک/آبادی و ردیف جایگزین در خام موجودند. پنج ستون مکانی در۱۳۹۲–۱۳۹۵ و برخی ستون‌های اجرایی/متنی دیگر نیز وجود دارند. گروه چرخش، طبقه و خوشه روی فرم چاپی هستند اما ستون مستقل یا جدول تطبیق طولی آنها در نسخه عمومی پیدا نشد. جدول خانوار در۱۳۹۶ به بعد۱۵ ستون خام دارد. فیلد Tekrari در سال‌های قدیمی هست، اما معنی دقیق آن و نقش پنلی‌اش احراز نشد و در کلید استفاده نشده است.

`raw_household_schema_<YEAR>.csv` تمام ستون‌ها، نوع، مقادیر غیرگمشده، یکتایی، مثال و معنی/منبع بازیابی‌شده را در Drive دارد. مثال‌ها ممکن است شناسه/متن هویتی باشند؛ GitHub فقط `raw_household_schema_summary.csv` بدون مثال دارد. برداشت اجزای Address در `address_component_interpretation.csv` همراه با سطح شواهد ثبت شده؛ نگاشت دلخواه ردیف به گروه چرخش ساخته نشد.

## ۵. کلیدهای نامزد و بهترین پیشنهاد فعلی

پنج روش پیش از نگاه به جمعیت‌شناسی تعریف شدند:

1. HBSIR_ID.
2. Raw_Address متن کامل بدون برش/تغییر.
3. Frame_Address = دوره طراحی + Address.
4. Original_Only: همان کلید، فقط Takmil=1 و Jaygozin≠1؛ مقدار نامشخص اصلی حذف حدسی نمی‌شود و کلید نمی‌گیرد.
5. Respondent_Location: برای اصلی دوره+Address+original؛ برای جایگزین Takmil=2 و Jaygozin=1، دوره+Address+substitute+بلوک/آبادی جایگزین+ردیف جایگزین، فقط وقتی دو جزء موجود و رقمی‌اند. وضعیت ناقص کلید نمی‌گیرد. هیچ مؤلفه جمعیت‌شناختی در ساخت پیوند استفاده نشده است.

هر پنج روش در هر سال آزمایشی یکتا هستند؛ پوشش و موارد فاقد کلید جدا گزارش شده است. این پنج روش پنج منشأ مستقل نیستند؛ اول و دوم روی داده حاضر یک پیوند می‌دهند، سوم فقط دامنه شناسه را درست می‌کند، چهارم/پنجم امکان تعویض پاسخ‌دهنده در یک جایگاه را کنترل می‌کنند. پیشنهاد محافظه‌کارانه برای بررسی آینده **دوره طراحی+Address با کنترل صریح اصلی/جایگزین** است. این هنوز شناسه دائمی خانواده یا کلید پنل تأییدشده نیست؛ شماره خوشه به‌تنهایی و ترکیب شهرستان/بلوک/ردیفِ فاقد شاهد کافی انتخاب نشد.

## ۶ و۷. همپوشانی و اعتبار جمعیت‌شناختی

N_t،N_next،N_common،دو نرخ و Jaccard برای فاصله۱ و۲ در `panel_key_candidate_overlap.csv` ثبت شده‌اند. مخرج نرخ همپوشانی تعداد کلیدهای یکتای واجد شرایط همان روش در همان سال است. برای Address خام نرخ‌های سالانه غیرصفر از۴۶٫۴۹٪ تا۶۹٫۴۷٪ است؛ حذف جایگزین/اطلاعات ناقص مخرج را عوض می‌کند، بنابراین افزایش یک نرخ دلیل برتری کلید نیست. شاخص‌های نظری۲/۳ و۱/۳ صرفاً راهنما هستند.

سازگاری سرپرست برای کلید مکان پاسخ‌دهنده، با مخرج پیوندهای دارای سن/جنس معلوم:

{md(table)}

برای کلید ID ساده، سازگاری هم‌زمان سن و جنس سالانه فقط۶۳٫۱۴٪ تا۶۹٫۸۲٪ است. کنترل وضعیت اصلی/جایگزین آن را به۷۷٫۷۹٪ تا۸۲٫۴۷٪ بهبود می‌دهد؛ پیوند دوساله۱۳۹۳→۱۳۹۵ برابر۷۲٫۶۶٪ است. این مقدار برای اعلام صحت همه پیوندها کافی نیست. پیوندهای دارای سن/جنس ناسازگار حذف نشده‌اند؛ ممکن است تغییر سرپرست، خطای گزارش سن، تغییر ردیف یا عدم تطبیق واقعی باشد. «تغییر قطعی سرپرست» بدون شناسه دائمی فرد قابل شمارش نیست؛ ستون Possible_Head_Change فقط هشدار است.

قاعده سنی درخواست‌شده دقیقاً رعایت شد: فاصله۱، تغییر۰ یا۱؛ فاصله۲، تغییر۱ یا۲. بررسی ماه خام، دامنه زمانی±۱ماه را جدا اعمال می‌کند؛ سن خارج قاعده اصلی با زمان ممکن، همچنان جدا پرچم دارد و جای قاعده اصلی را نمی‌گیرد. این کنترل با ماه و نه تاریخ دقیق است و خطای ماه/سن را رفع نمی‌کند.

برای اعضا فقط شماره عضو+رابطه در خانوارِ ازقبل پیوندخورده آزموده شد؛ شماره عضو هویت دائمی نیست. تغییر تعداد اعضا دلیل رد نیست. هشدار ترکیب شدید به‌صورت حداقل۲ زوج موقت و کمتر از۵۰٪ سازگاری سن و جنس تعریف شد؛ این آستانه توصیفی و قابل تغییر است، نه معیار رسمی یا اثبات مهاجرت/فوت. نرخ این هشدار برای کلید مکان پاسخ‌دهنده در پیوندهای سالانه قابل ارزیابی حدود۱۵٫۸۸٪ تا۲۰٫۵۸٪ و دوساله۲۴٫۸۴٪ است؛ جابه‌جایی شماره اعضا می‌تواند آن را ایجاد کند.

امتیاز توصیفی۰–۱۰۰ در سطح پیوند:۴۰امتیاز سن+۲۰جنس+۴۰میانگین سازگاری زوج‌های موقت اعضا؛ اگر اطلاعات لازم کامل نیست امتیاز null است. این احتمال صحت نیست و برای ایجاد پیوند استفاده نشده. چون شرط اثبات طراحی طولی برقرار نیست، هیچ برچسب A/B به‌معنای پیوند نهایی معتبر داده نشده؛ Panel_Link_Confidence=D به معنی عدم پذیرش فعلی خودکار است، نه اثبات کاذب بودن تک‌تک پیوندها. طبقه Demographic_Quality سازگاری مشاهده‌شده را جدا نشان می‌دهد.

## نمونه و بازبینی جزئی

نمونه ثابت با seed20261007:۵۰۰پیوند سالانه دوره۱۳۸۹،۵۰۰سالانه و۵۰۰دوساله دوره۱۳۹۲،۵۰۰سالانه دوره۱۳۹۷؛ مجموع۲۰۰۰پیوند در `panel_link_validation_sample.parquet`. دوره۱۳۸۹ و۱۳۹۷ در پایلوت فاصله دوساله داخل همان چارچوب ندارند و برایشان نمونه دوساله اختراع نشد. ۲۴پیوند از این نمونه با ردیف‌های خام دوباره بررسی مکانیکی شدند و نتیجه در `panel_link_partial_source_review.parquet` است؛ این بازبینی جزئی انسانی یا داوری هویت نیست. همه داده‌های سطح خانوار فقط Drive هستند.

## ۸. توضیح۳۵۳ شناسه بیش ازسه‌ساله

تمام۳۵۳ شناسه در **هر دو دوره۱۳۹۲ و۱۳۹۷** دیده شده‌اند؛ هیچ‌کدام از مرز۱۳۹۱/۱۳۹۲ عبور نکرده‌اند. در هر دوره جدا حداکثر۳سال دارند:۲۶۰شناسه حداکثر۳سال و۹۳شناسه حداکثر۲سال. پس مشکل بیش‌ازسه‌سال ناشی از استفاده دوباره از برچسب عددی در دو چارچوب است، نه مشاهده اثبات‌شده یک خانواده در۴تا۶موج یک پنل. در کل داده موجود، وقتی دوره طراحی وارد کلید شود، توزیع حضور۱،۲،۳سال به‌ترتیب۱۵۱٬۷۸۴،۱۰۴٬۸۳۰،۶۰٬۷۱۶کلید می‌شود و حضور بیشتر از۳ صفر است.

در۳۵۳ گذر بین دوره‌ها، جنس سرپرست در۳۵۲مورد معلوم است و فقط۷۷٫۸۴٪ سازگار؛۱۶۵مورد از۳۵۲سن معلوم کاهش سن دارند. این قرینه قوی علیه فرض «همان سرپرست/همان خانواده» برای کل مجموعه است؛ حتی سازگاری چند مورد اثبات هویت نیست. گذرها متوالی از۱۳۹۶به۱۳۹۷ نیستند؛ ID در مرز مجاور صفر و استفاده مجدد در سال‌های غیرمجاور رخ می‌دهد. در کل حضورهای این شناسه‌ها بیشترین دنباله متوالی۳سال است. `id_over_three_years.parquet` جزئیات کلیدهای بیش‌از۳سالِ هر روش در پایلوت و تشخیص۳۵۳ID در دوره کامل را با Scope جدا دارد؛ `id_over_three_frame_decomposition.parquet` تفکیک هر ID به دوره را حفظ می‌کند.

## ۹. چند پنل سه‌موجی قابل اعتماد داریم؟

در خروجی قدیمی۶۰٬۷۱۶نامزد سه سال متوالی وجود دارد؛ با شناسه دوره+Address نیز۶۰٬۷۱۶کلید سه‌ساله مشاهده می‌شود. **این عدد تعداد خانواده تأییدشده نیست.** پایلوت انتخاب‌شده هیچ سه سال متوالی درون یک دوره طراحی را به‌طور کامل پوشش نمی‌دهد. جدول `panel_three_wave_cohort_status.csv` شمار نامزد قدیمی هر cohort و مرزها را گزارش می‌کند و Validated_Family_Count را null می‌گذارد. تعداد واقعی قابل اعتماد در این مرحله **نامشخص** است؛ صفر اعلام نمی‌شود.

## ۱۰. تصمیم و معیار پایان

ممیزی آزمایشی، خواندن خام، تشریح قالب، آزمون پنج روش، بررسی سن/جنس/اعضا، بازبینی نمونه و توضیح۳۵۳برچسب انجام شده است. روش طولی خودکار با شواهد کافی تأیید نشد؛ بنا بر شرط صریح درخواست، به۱۴سال گسترش داده نشد و `panel_key_crosswalk.parquet` و `validated_three_wave_panels.parquet` ساخته نشدند. استفاده از تاریخچه۱۴ساله صرفاً تشخیص استفاده مجدد ID و شمار نامزد قدیمی است، نه گسترش روشِ تأییدنشده. خروجی‌های قبلی حفظ شدند.

برای ورود مطمئن به مدل‌سازی پنلی هنوز نیاز است: سند اصلی دوره/گروه چرخش و تعریف ثبات Address و جایگزین، سپس یک cohort کامل در هر دوره با داوری موارد ناسازگار و قواعد پذیرش ازپیش‌تعیین‌شده. ساخت کلید جدید صرفاً با حذف ارقام، انتخاب ترکیب برای افزایش همپوشانی یا پیوند بر پایه شباهت سن/جنس مجاز نیست و انجام نشد. هیچ مدل تقاضا، گروه کالایی یا نمونه نهایی برآورد ساخته نشده است.

## بازتولید و نگهداری

۱. `src/audit_raw_panel_identifiers.py` استخراج تو‌در‌تو و خواندن مستقیم MDBTools؛ برای نصب محلی کتابخانه‌ها LD_LIBRARY_PATH مطابق محیط مرحله قبل تنظیم شود.۲. `src/build_panel_key.py` کلیدها و همپوشانی.۳. `src/validate_panel_links.py` سنجش پیوند و تشخیص۳۵۳.۴. `src/make_panel_forensic_report.py` گزارش‌ها و خلاصه امن. گزارش و کد/آمار تجمیعی GitHub؛ فایل‌های پارکت، ستون‌های مثالی هویتی و ردیف‌های خام فقط Drive. اسناد اولیه همراه آرشیوها و نسخه مستقل مستندات ممیزی در documentation نگهداری می‌شوند. فایل `panel_forensic_completion_status.json` عمداً شروط انجام‌نشده را false و شمار تأییدشده را null ثبت می‌کند.
'''
    write('panel_identifier_forensic_audit.md',report)
    print(json.dumps(status,ensure_ascii=False))

if __name__=='__main__':main()
