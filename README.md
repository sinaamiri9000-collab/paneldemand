# داده‌های هزینه و درآمد خانوار ایران، ۱۳۹۰ تا ۱۴۰۳

این پروژه آرشیوهای سالانهٔ طرح هزینه و درآمد خانوار را ثبت، با HBSIR استاندارد و از نظر ساختار کالا، شناسه، متغیرهای جمعیت‌شناختی و تبدیل‌ها ممیزی می‌کند. سند جاری نمونه و preprocessing در [PROJECT_BRIEF.md](PROJECT_BRIEF.md) است. کد و نتایج پایلوت تقاضای Panel B در پوشه `pilot/` نگه داشته می‌شوند.

## پایلوت تقاضای Panel B

[گزارش پایلوت](pilot/report.md) روش ساخت قیمت از All donor pool و مقایسه censored QUAIDS روی **همان Panel B**، با و بدون کنترل‌های Mundlak، را توضیح می‌دهد. [نتایج تجمیعی](pilot/results.json) شامل ضرایب، کشش‌ها و diagnostics است. بنا به دستور کاربر، نوشابه فقط از سبد تحلیل این پایلوت حذف شده است: ۱۰۶ قلم و ۱۲ گروه؛ clean منبع و mapping ۱۰۷قلمی تغییر نکرده‌اند. تحصیلات و قید انحنای موضعی استفاده نشده‌اند. این برآورد نقطه‌ای حاشیه‌ای Mundlak/S&Y است؛ specification نهایی مقاله یا full joint RE likelihood نیست. وابستگی‌ها و دستور بازتولید در گزارش آمده‌اند.

[بازتخمین فقط Mundlak/S&Y بدون دامی سال و فصل](pilot/report_no_year_season.md) دامی موج را نگه می‌دارد و از همان نمونه و قیمت‌ها استفاده می‌کند؛ [نتایج کامل](pilot/results_no_year_season.json) جدا از اجرای اولیه نگهداری می‌شوند.

## فایل داده‌ها

آرشیوهای خام، هشت جدول استاندارد هر سال، جداول ترکیبی و خروجی‌های سطح خانوار در پوشهٔ خصوصی Google Drive [paneldemand](https://drive.google.com/drive/folders/1Q2wH3_8qIgadwC5-eEeOlTSjNa3SyP6N) نگهداری می‌شوند. فایل‌های خام و داده‌های خانوار در این مخزن قرار ندارند. برای هر فایل خام، منبع، اندازه و SHA-256 در `metadata/raw_sources.csv` ثبت شده است. آرشیو ۱۴۰۲ و جدول خوراکی ترکیبی به‌دلیل سقف انتقال Drive هرکدام در دو بخش ذخیره شده‌اند؛ راهنمای اتصال دوباره و هش فایل کامل در پوشه‌های مربوط و `metadata/drive_file_manifest.csv` ثبت شده است.

مهم‌ترین فایل‌های قابل مرور در همین مخزن:

- `audit/final_audit_report.md`: گزارش فارسی نهایی و موارد باز.
- `audit/1402_validation_report.md`: بررسی اسناد و تطبیق مستقیم آرشیو Access سال ۱۴۰۲ با خروجی HBSIR.
- `audit/yearly_sample_summary.csv`: شمار خانوار، عضو، خوراکی، پوشش متغیرها و وزن به تفکیک سال.
- `audit/commodity_year_audit.csv.gz`: ممیزی تجمیعی سال × کد خوراکی؛ نسخهٔ کامل Parquet نیز در Drive است.
- `audit/panel_overlap_by_year.csv` و `audit/panel_length_distribution.csv`: همپوشانی و طول حضور شناسه‌ها.
- `audit/independent_review/drive_destination_check.json`: تطبیق نام و اندازهٔ فایل‌های مقصد Drive با مانیفست و چند آزمون هش مستقیم.
- `audit/demographic_variable_audit.csv`, `audit/hbsir_transformations.csv`, `audit/issues_log.csv`.

## اجرای کد

نسخهٔ HBSIR و وابستگی‌های Python در `metadata/hbsir_version.json` و `environment/requirements.lock.txt` قفل شده‌اند. برای ساخت یک محیط Python:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

استخراج آرشیوهای قدیمی Access به ابزارهای سیستمی معرفی‌شده در `environment/system_dependencies.md` نیاز دارد. مسیرهای پوشه از `config.yaml` خوانده می‌شوند؛ کد به مسیر مطلق یک رایانه وابسته نیست. هر اسکریپت در `src/` یک مرحلهٔ مشخص را اجرا می‌کند؛ ترتیب و محدودیت‌های منبع در گزارش و فراداده آمده است. اجرای گزارش نهایی:

```bash
python src/make_report.py
```

برای بازتولید جداول، آرشیوهای محلی را در `raw/<سال>/data.rar` و فایل‌های منبع HBSIR را در مسیرهای مقرر قرار دهید، سپس اسکریپت‌های دانلود/استانداردسازی/ممیزی را اجرا کنید. نشانی رسمی مرکز آمار در زمان این اجرا HTTP 503 می‌داد؛ آینهٔ ثبت‌شده در `metadata/raw_sources.csv` استفاده شده است.

## هشدارهای اصلی

تطبیق مستقیم هشت جدول سال ۱۴۰۲ با Access کامل است. ممیزی مستقل برای سال ۱۴۰۰ یک ناهماهنگی ۲٬۹۸۰ شناسه‌ای میان جدول مسکن و خانوار پیدا کرد. تکرار برخی شناسه‌ها بیش از سه سال هم به‌تنهایی هویت ثابت خانوار را ثابت نمی‌کند. جزئیات و تصمیم‌های باز در گزارش نهایی ثبت شده‌اند. این یافته‌ها باید پیش از ادعای پنل بودن داده‌ها یا برآورد مدل بررسی شوند.

## ساختار مخزن

`src/` شامل کد؛ `metadata/` شامل منشأ، واژه‌نامه و نسخه‌ها؛ `audit/` شامل آمار و گزارش‌های تجمیعی؛ `environment/` شامل محیط اجرا است. فایل خام و دادهٔ سطح خانوار فقط در Drive خصوصی نگهداری می‌شوند.

بازتخمین Mundlak/S&Y با هفت دامی cohort به جای wave، بدون سال/فصل: [گزارش کامل](pilot/report_cohort.md) و [نتایج](pilot/results_cohort.json). بازتولید: `python pilot/run.py --inputs intermediate/pilot_inputs --models CRE --no-year-season --cohort-instead-of-wave --cache-prefix cohort_ --warm-start pilot/results_no_year_season.json --output pilot/results_cohort.json` سپس `python pilot/write_sensitivity.py --cohort`.

آزمون‌های conditional و مقدماتی همگنی ضرایب زمانی/cohort: [گزارش محاسبات](pilot/report_stability.md)، [نتایج](pilot/results_stability.json) و [بررسی ادبیات و محدودیت انتقال روش‌ها](pilot/literature_stability.md). این اجراها sensitivity هستند؛ مدل پایهٔ cohort و دادهٔ frozen تغییر نکرده‌اند.

بررسی جدید پایداری **قبل/بعد از ۱۳۹۷** با covariance چندمرحله‌ایِ خوشهٔ خانوار (CF، ۱۲ Probit و IFGNLS)، تفکیک اهمیت آماری/اقتصادی تفاوت کشش‌ها و حساسیت **Mundlak بدون S&Y و CF**: [گزارش جامع و تمام پارامترها/ماتریس‌ها](pilot/report_economic_stability.md)، [نتایج مدل اصلی](pilot/results_frame_stability.json) و [نتایج مدل ساده‌تر](pilot/results_plain_stability.json). bootstrap بزرگ اجرا نشده است؛ قیمت‌ها و نمونهٔ قبلی ثابت‌اند. مدل ساده‌تر آزمون‌های برابری Wald و score/LM مقاوم دو بازه، سه بازه و beta/lambda هشت cohort را دارد؛ نتیجهٔ آن به مدل اصلی تعمیم داده نمی‌شود.
