# داده‌های هزینه و درآمد خانوار ایران، ۱۳۹۰ تا ۱۴۰۳

این پروژه آرشیوهای سالانهٔ طرح هزینه و درآمد خانوار را ثبت، با HBSIR استاندارد و از نظر ساختار کالا، شناسه، متغیرهای جمعیت‌شناختی و تبدیل‌ها ممیزی می‌کند. سند جاری نمونه و preprocessing در [PROJECT_BRIEF.md](PROJECT_BRIEF.md) است. کد و نتایج پایلوت تقاضای Panel B در پوشه `pilot/` نگه داشته می‌شوند.

## پایلوت تقاضای Panel B

پوشهٔ `pilot` بر اساس هشت بستهٔ آزمایشی مرتب شده است. از [راهنمای بسته‌ها](pilot/README.md) شروع کنید؛ کد، گزارش و نتایج هر بسته کنار هم هستند و آخرین بسته در `specification_followup/` قرار دارد. کد مشترک و آزمون‌های صحت کد جدا نگهداری می‌شوند.

[گزارش پایلوت](pilot/initial/report.md) روش ساخت قیمت از All donor pool و مقایسه censored QUAIDS روی **همان Panel B**، با و بدون کنترل‌های Mundlak، را توضیح می‌دهد. [نتایج تجمیعی](pilot/initial/results.json) شامل ضرایب، کشش‌ها و diagnostics است. بنا به دستور کاربر، نوشابه فقط از سبد تحلیل این پایلوت حذف شده است: ۱۰۶ قلم و ۱۲ گروه؛ clean منبع و mapping ۱۰۷قلمی تغییر نکرده‌اند. تحصیلات و قید انحنای موضعی استفاده نشده‌اند. این برآورد نقطه‌ای حاشیه‌ای Mundlak/S&Y است؛ specification نهایی مقاله یا full joint RE likelihood نیست. وابستگی‌ها و دستور بازتولید در گزارش آمده‌اند.

[بازتخمین فقط Mundlak/S&Y بدون دامی سال و فصل](pilot/no_year_season/report.md) دامی موج را نگه می‌دارد و از همان نمونه و قیمت‌ها استفاده می‌کند؛ [نتایج کامل](pilot/no_year_season/results.json) جدا از اجرای اولیه نگهداری می‌شوند.

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

بازتخمین Mundlak/S&Y با هفت دامی cohort به جای wave، بدون سال/فصل: [گزارش کامل](pilot/cohort/report.md) و [نتایج](pilot/cohort/results.json). بازتولید: `python pilot/common/run.py --inputs intermediate/pilot_inputs --models CRE --no-year-season --cohort-instead-of-wave --cache-prefix cohort_ --warm-start pilot/no_year_season/results.json --output pilot/cohort/results.json` سپس `python pilot/common/write_sensitivity.py --cohort`.

آزمون‌های conditional و مقدماتی همگنی ضرایب زمانی/cohort: [گزارش محاسبات](pilot/preliminary_stability/report.md)، [نتایج](pilot/preliminary_stability/results.json) و [بررسی ادبیات و محدودیت انتقال روش‌ها](pilot/preliminary_stability/literature_stability.md). این اجراها sensitivity هستند؛ مدل پایهٔ cohort و دادهٔ frozen تغییر نکرده‌اند.

بررسی جدید پایداری **قبل/بعد از ۱۳۹۷** با covariance چندمرحله‌ایِ خوشهٔ خانوار (CF، ۱۲ Probit و IFGNLS)، تفکیک اهمیت آماری/اقتصادی تفاوت کشش‌ها و حساسیت **Mundlak بدون S&Y و CF**: [گزارش جامع و تمام پارامترها/ماتریس‌ها](pilot/economic_stability/report.md)، [نتایج مدل اصلی](pilot/economic_stability/results_frame_stability.json) و [نتایج مدل ساده‌تر](pilot/economic_stability/results_plain_stability.json). bootstrap بزرگ اجرا نشده است؛ قیمت‌ها و نمونهٔ قبلی ثابت‌اند. مدل ساده‌تر آزمون‌های برابری Wald و score/LM مقاوم دو بازه، سه بازه و beta/lambda هشت cohort را دارد؛ نتیجهٔ آن به مدل اصلی تعمیم داده نمی‌شود.

مسیر مشخص جدید روی **مدل اصلی Mundlak/S&Y + CF**: آزمون جداگانهٔ beta،lambda،Gamma بین هشت cohort ورود؛ سپس آزمون مستقل سالانه با کنترل سطح cohort و سال، از مدل مقید با score مقاوم. [گزارش کامل، تمام ضرایب و ماتریس‌ها و فاصلهٔ اطمینان اختلاف کشش‌ها](pilot/cohort_annual_stability/report.md) و [نتایج ماشین‌خوان](pilot/cohort_annual_stability/results.json). استنباط، WLS و ۱۲ Probit و Sigma را در خوشهٔ خانوار لحاظ می‌کند؛ قیمت‌های ساخته‌شده ثابت‌اند. سال فقط در خانوادهٔ آزمون سالانه اضافه می‌شود؛ مدل پایهٔ cohort و خروجی‌های قبلی حفظ شده‌اند. این دو آزمون، علت تفاوت را به طور مشترک بین cohort و زمان شناسایی نمی‌کنند.

پنج تصریح مشترک‌شیب **B0، B1، B2، B3 و P0** طبق مشخصات جدید: [گزارش و همهٔ ضرایب/ماتریس‌های کشش](pilot/specification_suite/report.md)، [نتایج و مقایسه‌های ماشین‌خوان](pilot/specification_suite/results.json). درآمد میانگین فقط در مرحلهٔ اول است؛ B1/B2 میانگین CF را به‌صورت جمعی، B2 میانگین مخارج را در ترجمهٔ alpha و B3 حذف میانگین‌های جنسیت/تأهل را بررسی می‌کنند. سال و cohort به‌صورت مستقل و فصل جاری/میانگین وارد شده‌اند؛ wave حذف است. آزمون‌ها و اختلاف کشش‌ها استنباط چندمرحله‌ایِ خوشهٔ خانوار دارند. این بسته هنوز مدل کامل joint CRE نیست؛ محدودیت مقایسهٔ P0/B0 دربارهٔ سن و تغییر اندک فصل در گزارش روشن شده‌اند. بازتولید: `python pilot/specification_suite/specification_suite.py --inputs intermediate/pilot_inputs` سپس `python pilot/specification_suite/write_specification_report.py`؛ `--models` و `--threads` برای اجراهای هم‌زمان قابل استفاده‌اند و مرحلهٔ پرحافظهٔ استنباط قفل مشترک دارد.

اجراهای تکمیلی ۲۰۲۶–۱۰–۰۹: **P0_matched** با سن و RF/CF عین B0، و **B1/B2 بدون میانگین‌های فصل** در تمام مراحل، با حفظ دامی‌های فصل جاری. [گزارش کامل و تمام ضرایب/ماتریس‌ها](pilot/specification_followup/report.md) و [نتایج ماشین‌خوان](pilot/specification_followup/results.json) علاوه بر روش قبلی، مشتق مستقیم تابع برازش‌شدهٔ S&Y را در نقطهٔ متوسط و در همهٔ مشاهدات گزارش می‌کنند؛ اختلاف کشش دو مدل با covariance چندمرحله‌ایِ خوشهٔ خانوار و لحاظ همبستگی دو برآورد محاسبه شده است. P0_matched فقط در مشارکت/تقاضا Pooled است و مرحلهٔ اول مشترک CRE دارد. برآوردهای قبلی و داده‌ها حفظ شده‌اند؛ آزمون‌های ثبات شیب‌ها به مرحلهٔ بعد موکول شده‌اند. دستور اجراهای موازی و بازتولید در گزارش آمده است.
