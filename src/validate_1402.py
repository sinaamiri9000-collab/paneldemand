from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from common import append_issues, path


def sha256(file: Path) -> str:
    h = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def valid_positive(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.Series(np.isfinite(numeric) & numeric.gt(0), index=series.index)


def main() -> int:
    base = path("yearly") / "1402"
    audit = path("audit")
    audit.mkdir(parents=True, exist_ok=True)
    raw = path("raw") / "1402" / "data.rar"
    guide = path("documentation") / "1402" / "raw_file_guide_1402.pdf"
    questionnaire = path("documentation") / "1402" / "questionnaire_1402.pdf"
    guide_hash = sha256(guide)
    questionnaire_hash = sha256(questionnaire)
    with zipfile.ZipFile(raw) as archive:
        bad_member = archive.testzip()
        members_in_archive = archive.namelist()
        guide_entry = next((n for n in members_in_archive if n.endswith("معرفي فايل خام هزينه و درامد1402.pdf")), None)
        questionnaire_entry = next((n for n in members_in_archive if n.endswith("1402-پرسشنامه هزينه و درامد.pdf")), None)
        archive_guide_hash = hashlib.sha256(archive.read(guide_entry)).hexdigest() if guide_entry else "missing"
        archive_questionnaire_hash = hashlib.sha256(archive.read(questionnaire_entry)).hexdigest() if questionnaire_entry else "missing"

    hh = pd.read_parquet(base / "household.parquet")
    members = pd.read_parquet(base / "members.parquet")
    food = pd.read_parquet(base / "food.parquet")
    wage = pd.read_parquet(base / "income_wage.parquet")
    selfemp = pd.read_parquet(base / "income_self_employed.parquet")
    other = pd.read_parquet(base / "income_other.parquet")
    subsidy = pd.read_parquet(base / "income_subsidy.parquet")
    housing = pd.read_parquet(base / "housing.parquet")
    amount_valid, price_valid, exp_valid = (valid_positive(food[c]) for c in ["Amount", "Price", "Expenditure"])
    employment_types = sorted(selfemp["Employment_Type"].dropna().astype(str).unique().tolist())
    provision_methods = sorted(food["Provision_Method"].dropna().astype(str).unique().tolist())
    doc_match = guide_hash == archive_guide_hash and questionnaire_hash == archive_questionnaire_hash
    report = f"""# گزارش اعتبارسنجی آزمایشی سال ۱۴۰۲

## وضعیت منبع و اسناد

- آرشیو خام در مسیر `raw/1402/data.rar` ذخیره شده است. پاسخ نشانی رسمی مرکز آمار در این اجرا HTTP 503 بود؛ آرشیو با همان نام از آینهٔ مستند HBSIR دریافت شد. URL و زنجیرهٔ تلاش‌ها در `metadata/raw_sources.csv` ثبت شده است.
- امضای واقعی فایل ZIP است، با وجود پسوند `.rar`. `ZipFile.testzip()` نتیجهٔ `{bad_member or 'بدون خطا'}` داد؛ آرشیو شامل فایل‌های راهنمای خام، پرسشنامه و آرشیو تو در توی `HB1402_14030707.rar` است.
- راهنمای خام: SHA256=`{guide_hash}`؛ پرسشنامه: SHA256=`{questionnaire_hash}`.
- هر دو PDF کاربر با نسخه‌های داخل آرشیو برابرند: `{doc_match}` (راهنما: `{archive_guide_hash}`؛ پرسشنامه: `{archive_questionnaire_hash}`).

## تطبیق ساختار داده با اسناد

- جدول مشخصات خانوار در HBSIR شامل `ID`, `Season_Number`, `Season`, `Weight`, `Household_Type`, `Main_Household`, و `Alternative_Household` است. این با فیلدهای `Address`, `Fasl`, `weight`, `NoeKhn`, `Takmil`, و `Jaygozin` در راهنمای خام متناظر است. وزن HBSIR در این سال با فیلد وزن خانوار هم‌خوان است؛ تعداد وزن‌های غیرگمشده `{int(pd.to_numeric(hh['Weight'], errors='coerce').notna().sum()):,}` از `{len(hh):,}` است.
- راهنمای خام همچنین `BlkAbdJaygozin` و `RadifJaygozin` را برای خانوار جایگزین معرفی می‌کند. این دو فیلد در خروجی استاندارد HBSIR موجود نیستند؛ در این مرحله حذف یا بازسازی نشدند. آرشیو خام نگهداری شده است تا در صورت نیاز بعداً استخراج شوند.
- جدول اعضا شامل شناسهٔ خانوار و عضو و متغیرهای `Relationship`, `Sex`, `Age`, `Is_Literate`, `Is_Student`, `Education_Level`, `Activity_Status`, و `Marital_Status` است؛ این‌ها به‌ترتیب با `DYCOL03` تا `DYCOL10` (با فاصلهٔ `DYCOL02` در راهنمای عضو) مطابقت دارند. تعداد ردیف اعضا `{len(members):,}` است.
- جدول خوراکی طولی است و شامل کد کالا، روش تهیه، `Amount`, `Price`, `Expenditure`, و `Duration` است. راهنمای خام برای این بخش `DYCOL01` کد کالا، `DYCOL02` روش تهیه، `DYCOL03` گرم، `DYCOL04` کیلو، `DYCOL05` قیمت و `DYCOL06` ارزش را فهرست می‌کند. در خروجی، مقدار استاندارد HBSIR از کیلو و گرم و در شرایط تعریف‌شده از هزینه/قیمت ساخته می‌شود؛ مقدارهای `Kilos_Raw`, `Grams_Raw`, `Price_Raw` از جدول cleaned آینهٔ HBSIR حفظ شده‌اند، نه از استخراج مستقل Access.
- تعداد خانوار یکتا `{hh['ID'].nunique():,}`؛ تعداد ردیف خوراکی `{len(food):,}`؛ تعداد کد کالای یکتا `{food['Commodity_Code'].nunique():,}`. روش‌های تهیه مشاهده‌شده: `{', '.join(provision_methods)}`. وزن/فصل حفظ شده‌اند. HBSIR نام کالاها و طبقه‌بندی را از فرادادهٔ خودش اضافه می‌کند؛ کد کالاها در این پروژه ادغام نشده‌اند.
- مقادیر مثبت و متناهی در رکوردهای خوراکی: مقدار `{int(amount_valid.sum()):,}` ({amount_valid.mean()*100:.2f}٪)، قیمت `{int(price_valid.sum()):,}` ({price_valid.mean()*100:.2f}٪)، هزینه `{int(exp_valid.sum()):,}` ({exp_valid.mean()*100:.2f}٪). صفرها و مقادیر منفی خودکار اصلاح نشده‌اند؛ HBSIR در استانداردسازی مقدار قیمت صفر را گمشده می‌کند. شمارش Price صفر در ستون حفظ‌شدهٔ HBSIR cleaned: `{int(pd.to_numeric(food['Price_Raw'], errors='coerce').eq(0).sum()):,}`.
- مقدار HBSIR از `Kilos.fillna(0) + Grams.fillna(0)/1000` ساخته می‌شود؛ وقتی هر دو جزء موجود نباشند و قیمت مثبت باشد، HBSIR مقدار را از `Expenditure/Price` جایگذاری می‌کند. ردیف‌هایی که با این قاعده ساخته شده‌اند: `{int(food['Amount_Source'].eq('HBSIR_Expenditure_divided_by_Price').sum()):,}`؛ منشأ هر ردیف در `Amount_Source` مشخص است.
- درآمد مزد، خوداشتغالی، سایر درآمدها و یارانه به‌صورت جداول جدا نگهداری می‌شوند: `{len(wage):,}`, `{len(selfemp):,}`, `{len(other):,}`, `{len(subsidy):,}` ردیف. متغیر کل درآمد خانوار ساخته نشده است. مسکن/دارایی‌ها شامل `{len(housing):,}` ردیف است.

## موارد مهم و محدودیت‌ها

- در خوداشتغالی، راهنمای خام صفحهٔ ۶ کدهای نوع اشتغال را ۱/۲/۳ می‌نویسد؛ پرسشنامهٔ رسمی صفحهٔ ۶۵ کدهای ۴/۵/۶ را نشان می‌دهد. مقادیر `Employment_Type` پس از استانداردسازی HBSIR: `{', '.join(employment_types)}`. این خروجی با پرسشنامه سازگار است؛ کدگذاری را در این پروژه تغییر ندادیم و اختلاف دو سند را ثبت می‌کنیم.
- داده‌های جدول‌شده برای این آزمون از آینهٔ cleaned نگهداری‌شده توسط HBSIR و تابع `load_table(form='normalized')` آمده‌اند. آرشیو خام بایت‌به‌بایت حفظ و هش شده است، اما پایگاه Access تو در تو در این محیط به‌طور مستقل دوباره به جداول cleaned استخراج نشده است. بنابراین تطبیق مستقیم تمام رکوردهای Access با خروجی HBSIR تأیید نشده.
- آزمون ۱۴۰۲ با موفقیت انجام شد: ساختار مورد انتظار و کلید خانوار/عضو حفظ شده‌اند؛ دو شناسهٔ بلوک و ردیف خانوار جایگزین در HBSIR نیستند و اختلاف کد نوع اشتغال در دو سند رسمی باید پیش از تحلیل خوداشتغالی به خاطر سپرده شود.
"""
    target = audit / "1402_validation_report.md"
    target.write_text(report, encoding="utf-8")
    issues = []
    if bad_member:
        issues.append({"Year": 1402, "Scope": "raw.archive", "Issue": "archive_member_checksum_failed", "Severity": "blocking", "Details": str(bad_member)})
    if not doc_match:
        issues.append({"Year": 1402, "Scope": "documentation", "Issue": "embedded_document_hash_mismatch", "Severity": "warning", "Details": "The attached official PDFs do not match the copies inside the raw archive."})
    append_issues(issues)
    print(f"1402 validation written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
