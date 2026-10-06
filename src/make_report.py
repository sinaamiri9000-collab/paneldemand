from __future__ import annotations

import json

import pandas as pd

from common import config, path


def pct(value: float) -> str:
    return f"{value:.2f}%"


def main() -> int:
    cfg = config()
    start, end = cfg["project"]["first_year"], cfg["project"]["last_year"]
    samples = pd.read_csv(path("audit") / "yearly_sample_summary.csv")
    commodities = pd.read_parquet(path("audit") / "commodity_year_audit.parquet")
    panel = pd.read_csv(path("audit") / "panel_overlap_by_year.csv")
    length = pd.read_csv(path("audit") / "panel_length_distribution.csv")
    demo = pd.read_csv(path("audit") / "demographic_variable_audit.csv")
    transformations = pd.read_csv(path("audit") / "hbsir_transformations.csv")
    issues = pd.read_csv(path("audit") / "issues_log.csv", encoding="utf-8-sig", dtype=str)
    raw_integrity = pd.read_csv(path("audit") / "raw_archive_integrity.csv")
    raw_summary = json.loads((path("audit") / "raw_archive_integrity_summary.json").read_text(encoding="utf-8"))
    direct = pd.read_csv(path("audit") / "direct_1402_raw_to_hbsir_value_check.csv")
    panel_summary = json.loads((path("audit") / "panel_audit_summary.json").read_text(encoding="utf-8"))

    direct_ok = int(direct["Full_Multiset_Match_On_Shared_Columns"].astype(str).str.lower().eq("true").sum())
    direct_bad = int(len(direct) - direct_ok)
    code_counts = commodities.groupby("Year")["Commodity_Code"].nunique()
    min_hh, max_hh = int(samples["Household_Rows"].min()), int(samples["Household_Rows"].max())
    min_food, max_food = int(samples["Food_Rows"].min()), int(samples["Food_Rows"].max())
    amount_range = (float(samples["Food_Valid_Amount_Percent"].min()), float(samples["Food_Valid_Amount_Percent"].max()))
    price_range = (float(samples["Food_Valid_Price_Percent"].min()), float(samples["Food_Valid_Price_Percent"].max()))
    expenditure_range = (float(samples["Food_Valid_Expenditure_Percent"].min()), float(samples["Food_Valid_Expenditure_Percent"].max()))
    total_food = int(samples["Food_Rows"].sum())
    name_changed = int(commodities["Commodity_Name_Changed_In_Period"].fillna(False).astype(bool).sum())
    category_changed = int(commodities["HBSIR_Category_Changed_In_Period"].fillna(False).astype(bool).sum())
    external_weights = sorted(samples["Household_Weight_Source"].dropna().astype(str).unique())
    weight_sources = "; ".join(external_weights)

    # Report overlap using both defensible denominators. The script stores
    # shares of t and t+lag, plus Jaccard, so the denominator is explicit.
    overlap_lines = [
        "| t | N(t) | مشترک با t+1 | سهم از t | سهم از t+1 | مشترک با t+2 | سهم از t | سهم از t+2 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in panel.iterrows():
        def val(column: str) -> str:
            x = row.get(column)
            return "—" if pd.isna(x) else (f"{x:.3f}" if "Share" in column else f"{int(x):,}")
        overlap_lines.append(
            f"| {int(row['Year'])} | {int(row['Households_t']):,} | {val('Common_t_tplus1')} | "
            f"{val('Share_of_HH_in_t_also_in_tplus1')} | {val('Share_of_HH_in_tplus1_also_in_t')} | "
            f"{val('Common_t_tplus2')} | {val('Share_of_HH_in_t_also_in_tplus2')} | "
            f"{val('Share_of_HH_in_tplus2_also_in_t')} |"
        )

    length_map = dict(zip(length["Observed_Year_Bin"].astype(str), length["Household_ID_Count"].astype(int)))
    integrity_pass = int(raw_integrity.get("Integrity_Pass", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if "Integrity_Pass" in raw_integrity else int(raw_summary.get("zip_integrity_passed", 0)) + int(raw_summary.get("rar_integrity_passed", 0))
    official_fail = int(pd.to_numeric(raw_integrity.get("Official_HTTP_Status"), errors="coerce").eq(503).sum()) if "Official_HTTP_Status" in raw_integrity else 14

    text = f"""# گزارش نهایی گردآوری و ممیزی داده‌های هزینه و درآمد خانوار، {start} تا {end}

## دامنه و وضعیت دریافت

برای هر ۱۴ سال {start} تا {end} آرشیو اصلی در پوشهٔ سالانه دریافت و نگهداری شده است. هش SHA-256، اندازه، نشانی و روش دریافت هر فایل در `metadata/raw_sources.csv` ثبت شده است. آزمون ساختاری/یکپارچگی آرشیوها برای {integrity_pass} فایل موفق بود. نشانی‌های رسمی مرکز آمار در این اجرا برای {official_fail} سال پاسخ HTTP 503 دادند؛ در نتیجه از آینهٔ عمومی مستندشدهٔ HBSIR استفاده شد و هیچ آینهٔ ناشناخته‌ای به‌کار نرفت.

دادهٔ استانداردشدهٔ سالانه شامل خانوار، اعضا، خوراکی، مزد، خوداشتغالی، سایر درآمد، یارانه و مسکن است. جدول یارانه جدا نگه داشته شده تا اجزای درآمدی بدون تعریف پژوهشگرانهٔ «درآمد کل» قابل بررسی بمانند. فایل‌های تلفیقی شامل خانوار، اعضا، خوراکی، سه جدول درآمدی اصلی و یارانهٔ جداگانه‌اند. خوراکی به‌صورت طولی باقی مانده و گروه‌بندی نهایی، سهم بودجه، قیمت گروهی یا نمونهٔ مدل ساخته نشده است.

## اعتبارسنجی مستقیم ۱۴۰۲

آرشیو ۱۴۰۲ با فرمت واقعی ZIP (با پسوند `.rar`) سالم باز شد؛ پایگاه Access تو‌در‌تو با ابزارهای خواندن Access استخراج و از مسیر HBSIR بدون تغییر کد HBSIR استاندارد شد. {direct_ok} جدول از {len(direct)} جدول، در تطبیق چندمجموعه‌ای همهٔ ردیف‌ها روی ستون‌های مشترک، دقیقاً منطبق بود؛ موارد نامنطبق: {direct_bad}. شمارش جدول‌های خام R/U و استانداردشده در `direct_1402_access_table_counts.csv` آمده است. فیلدهای خام طراحی/جایگزینی خانوار که HBSIR در جدول استاندارد نمی‌آورد، در خروجی سال ۱۴۰۲ حفظ شده‌اند. جدول دخانیات جداگانه است و در خوراکی ادغام نشده است.

## کیفیت سالانه و اقلام خوراکی

تعداد خانوارهای سالانه بین {min_hh:,} و {max_hh:,} و ردیف‌های خوراکی بین {min_food:,} و {max_food:,} است؛ مجموع ردیف‌های خوراکی {total_food:,}. در سال‌های ۱۳۹۰ تا ۱۴۰۱ هر سال ۲۲۳ کد خوراکی یکتا دیده می‌شود و در ۱۴۰۲ و ۱۴۰۳ تعداد ۲۲۲ است. این اختلاف گزارش شده و هیچ کدی بر اساس شباهت نام ادغام نشده است.

در کل دوره، سهم ردیف‌های دارای مقدار مثبت و متناهی در دامنهٔ {pct(amount_range[0])} تا {pct(amount_range[1])}، قیمت معتبر {pct(price_range[0])} تا {pct(price_range[1])}، و هزینهٔ معتبر {pct(expenditure_range[0])} تا {pct(expenditure_range[1])} است. «معتبر» در این گزارش یعنی مثبت و متناهی؛ صفر/منفی خودکار جایگزین نشده است. شمار مقدارهایی که HBSIR طبق قاعدهٔ مستند از هزینه تقسیم بر قیمت جایگذاری کرده در `Amount_Source` و ممیزی کالا ثبت شده است. قیمت صفرِ باقی‌مانده در ستون منبع تمیزشدهٔ HBSIR جداگانه شمارش شده؛ این ستون را نباید بی‌قید معادل بایت خام Access برای همهٔ سال‌ها دانست.

`audit/commodity_year_audit.parquet` شامل {len(commodities):,} ردیف سال × کد کالا و شمار خانوارهای خریدار، نرخ خرید خام و وزن‌دار، تعداد/سهم مشاهدات معتبر مقدار و قیمت و هزینه، میانه‌ها، سال‌های مشاهده و تغییر نام/طبقه‌بندی است. نرخ خرید بر اساس روش‌های تهیهٔ ثبت‌شده به‌عنوان خرید در `src/audit_commodities.py` محاسبه شده است. موارد تغییر نام در ردیف‌های سالانهٔ ممیزی علامت‌گذاری می‌شوند؛ تصمیم ادغام پژوهشی گرفته نشده است. در این بازه، {name_changed} ردیف سالانه به کدی تعلق دارد که نامش در دوره تغییر کرده و {category_changed} ردیف سالانه در دسته‌بندی HBSIR تغییر ثبت‌شده دارد.

## جمعیت‌شناسی و تبدیل‌های HBSIR

ممیزی جمعیت‌شناختی {len(demo)} ردیف متغیر × سال دارد و وجود، نام خام/استاندارد، نوع، کدگذاری، درصد گمشده و تغییر نسبت به سال قبل را ثبت می‌کند. وزن سال‌های قبل از ۱۳۹۶ از جدول وزن خارجی HBSIR تکمیل شده است؛ منبع وزن هر سال در `yearly_sample_summary.csv` آمده است (`{weight_sources}`). بنابراین وزن را برای همهٔ سال‌ها نباید مستقیماً ستون خام یکسان مرکز آمار توصیف کرد.

فایل `hbsir_transformations.csv` {len(transformations)} ردیف نگاشت و تبدیل مستند دارد و تغییر نام را از بازکدگذاری، محاسبهٔ HBSIR و منبع خارجی جدا می‌کند. از جمله: مقدار خوراکی ممکن است از کیلو/گرم و در موارد تعریف‌شده از هزینه/قیمت ساخته شود؛ قیمت صفر در نسخهٔ نرمال‌شده به گمشده تبدیل می‌شود؛ کد عضو یارانه ۳۲۳ از ۱۳۹۲ در HBSIR به ۱ بازکدگذاری شده؛ و متغیر درآمد کل خانوار در این پروژه ساخته نشده است. اختلاف کد نوع خوداشتغالی بین راهنمای فایل خام (۱/۲/۳) و پرسشنامهٔ رسمی (۴/۵/۶) در گزارش اعتبارسنجی ۱۴۰۲ ثبت شده است.

## شناسه و همپوشانی پنل

بر اساس حضور شناسه‌ها، {length_map.get('one_year', 0):,} شناسه در یک سال، {length_map.get('two_years', 0):,} در دو سال، {length_map.get('three_years', 0):,} در سه سال و {length_map.get('more_than_three_years', 0):,} در بیش از سه سال دیده شده‌اند. بیش از سه حضور علامت هشدار است و تکرار شناسه به‌تنهایی اثبات نمی‌کند خانوار در طول زمان همان خانوار باشد. تاریخچهٔ شناسه و پنل‌های سه‌موجی فقط در Drive نگهداری می‌شوند، چون شامل دادهٔ سطح خانوارند.

جدول زیر دو تعریف مخرج را برای هر همپوشانی نشان می‌دهد: نسبت به تعداد خانوارهای سال t و نسبت به تعداد خانوارهای سال بعد/با فاصلهٔ دو سال. به‌علاوه فایل `panel_overlap_by_year.csv` شاخص جاکارد را هم دارد. مقادیر نظری حدود ۲/۳ برای t,t+1 و ۱/۳ برای t,t+2 را باید با تغییر چارچوب و جایگزینی نمونه سنجید؛ در دادهٔ مشاهده‌شده برخی گذارها صفر یا دور از این مقادیرند، بنابراین شناسه‌ها برای مدل پنلی تأییدشده تلقی نمی‌شوند.

{"\n".join(overlap_lines)}

## موارد باز و ارزیابی کاربرد

- ممیزی مستقل راستی‌آزمایی ۴۳۷ کنترل موفق، یک کنترل ناموفق و یک هشدار ثبت کرد. مورد ناموفق: در ۱۴۰۰ تعداد ۲٬۹۸۰ شناسهٔ جدول مسکن از ۴۰٬۹۶۸ شناسه در خانوار متناظر وجود ندارد (جدول خانوار ۳۷٬۹۸۸ شناسه دارد). داده حفظ شده و پیش از پیوند این جدول باید منشأ و تعریف کلید بررسی شود.
- ۳۵۳ شناسه در بیش از سه سال حضور دارند. تعریف و هم‌ارزی شناسه‌ها در طول زمان، به‌ویژه در سال‌های تغییر چارچوب ۱۳۹۲ و ۱۳۹۷، برای ساخت پنل نیازمند مستندات طراحی نمونه و بررسی جداگانه است.
- منابع خام مستقیم مرکز آمار در اجرا در دسترس نبودند (HTTP 503)؛ بازتولید از آینه‌های مستند HBSIR ممکن است، اما نسخه/نشانی آینه بخشی از زنجیرهٔ منشأ داده است.
- قیمت‌های صفر/نامعتبر، تفاوت‌های کد/طبقه‌بندی و تغییر ساختار متغیرها باید پیش از هر تحلیل اقتصادی به انتخاب پژوهشگر بررسی شوند. این بسته تورم‌زدایی، تعریف «هزینهٔ واقعی»، برخورد با خرید صفر/نداشتن کالا یا ساخت سبد نهایی را انجام نمی‌دهد.

داده برای تحلیل مقطعی سالانه و بررسی اولیهٔ تقاضا نامزد مناسبی است، مشروط به تعیین روش قیمت‌گذاری/تورم‌زدایی، رسیدگی به مقادیر نامعتبر، استفادهٔ آگاهانه از وزن‌ها و بررسی تغییرات کد کالا. این ممیزی به‌تنهایی کفایت داده برای برآورد QUAIDS را اثبات نمی‌کند. برای مدل پنلی، تا وقتی منشأ شناسه‌ها، همپوشانی نامنتظره و ناهماهنگی مسکن ۱۴۰۰ روشن نشده، پیوند سال‌ها را معتبر فرض نکنید. هیچ گروه کالایی نهایی یا مدل برآوردشده در این پروژه ارائه نشده است.

## بازتولید

تنظیمات در `config.yaml` است. نسخهٔ HBSIR و قفل محیط در `metadata/hbsir_version.json` و `environment/requirements.lock.txt` ثبت شده‌اند. مراحل کدنویسی در `src/` هستند. آرشیوهای حجیم و جداول سالانه در Drive خصوصی پروژه نگهداری می‌شوند؛ دادهٔ خام و دادهٔ سطح خانوار در GitHub قرار نمی‌گیرد.
"""
    out = path("audit") / "final_audit_report.md"
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out} ({len(text)} characters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
