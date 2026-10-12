# راهنمای بسته‌های آزمایشی Panel B

فایل‌ها در **۱۳ بستهٔ آزمایشی** نگهداری می‌شوند. نتایج تاریخی حفظ شده‌اند؛ بستهٔ نهم فقط محاسبهٔ کشش با ضرایب قبلی است و بستهٔ دهم ۱۴ اجرای اولیهٔ مقطع/پنل و تاریخی است. بستهٔ سیزدهم، نسخهٔ تازهٔ ده پنل بدون میانگین مربع مخارج را دارد. هر پوشه کد و نتایج همان بسته را دارد؛ گزارش بسته‌های ۱۱ و ۱۲، طبق درخواست صاحب پروژه، در چت ارائه شده است. هسته و ابزارهای مشترک در `common/` و آزمون‌های صحت کد در `tests/` قرار دارند.

نسخهٔ [اکسل کامل مارشالی ۱۲×۱۲](fixed_parameter_elasticities/paneldemand_B1_B2_marshallian_12x12_1392_1403.xlsx) نیز در بستهٔ نهم قرار دارد.

برای نسخهٔ فعلی ۱۴ مدل، [بستهٔ سیزدهم](b1_fourteen_no_exp_square/README.md)، [گزارش بازتخمین ده پنل](b1_fourteen_no_exp_square/report.md) و [اکسل به‌روز ۱۴ شیت](b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) را ببینید. [بستهٔ دهم](b1_fourteen/README.md) گزارش و نتایج تاریخی اولیه را حفظ می‌کند.

برای کشش‌های سالانه و cohort با ضرایب ثابت از [بستهٔ نهم](fixed_parameter_elasticities/README.md) شروع کنید. برای آخرین مقایسهٔ برازش B1 و B2 از [بستهٔ پیگیری](specification_followup/README.md) شروع کنید. جدول زیر مسیر تاریخی آزمایش‌ها را نشان می‌دهد؛ فایل هر بسته وضعیت همان آزمایش است و الزاماً تصریح نهایی مقاله نیست.

| بسته | موضوع | گزارش | نتایج |
| --- | --- | --- | --- |
| [۱. پایلوت اولیه و ساخت قیمت](initial/README.md) | ساخت قیمت بازار از All و مقایسهٔ Pooled/Mundlak روی همان Panel B با S&Y و CF. | [گزارش](initial/report.md) | [JSON](initial/results.json) |
| [۲. حذف دامی سال و فصل](no_year_season/README.md) | بازتخمین فقط Mundlak/S&Y بدون سال و فصل و با حفظ wave. | [گزارش](no_year_season/report.md) | [JSON](no_year_season/results.json) |
| [۳. جایگزینی wave با cohort](cohort/README.md) | مدل Mundlak/S&Y با دامی cohort، بدون wave و سال/فصل. | [گزارش](cohort/report.md) | [JSON](cohort/results.json) |
| [۴. آزمون‌های مقدماتی ثبات](preliminary_stability/README.md) | آزمون‌های اکتشافی و conditional ثبات زمانی/cohort؛ همراه مرور ادبیات. محدودیت‌های این مرحله در گزارش حفظ شده‌اند. | [گزارش](preliminary_stability/report.md) | [JSON](preliminary_stability/results.json) |
| [۵. ثبات زمانی و اهمیت اقتصادی](economic_stability/README.md) | مقایسهٔ قبل/بعد ۱۳۹۷ با استنباط چندمرحله‌ای و آزمایش مدل بدون S&Y/CF؛ چند اجرا یک بسته‌اند. | [گزارش](economic_stability/report.md) | [JSON](economic_stability/results_frame_stability.json) و [مدل ساده‌تر](economic_stability/results_plain_stability.json) |
| [۶. آزمون بلوک‌ها بین cohort و سال](cohort_annual_stability/README.md) | آزمون جداگانهٔ beta، lambda و Gamma بین cohortها، سپس آزمون مستقل سالانه با کنترل تغییر سطح. | [گزارش](cohort_annual_stability/report.md) | [JSON](cohort_annual_stability/results.json) |
| [۷. بستهٔ پنج تصریح](specification_suite/README.md) | B0، B1، B2، B3 و P0: بررسی میانگین CF، میانگین مخارج و کنترل‌های جمعیت‌شناختی. | [گزارش](specification_suite/report.md) | [JSON](specification_suite/results.json) |
| [۸. پیگیری پنج تصریح و مشتق مستقیم](specification_followup/README.md) | Pooled با سن/RF یکسان، B1/B2 بدون میانگین فصل و کشش‌های مستقیم S&Y؛ بستهٔ پیگیری برازش‌ها. | [گزارش](specification_followup/report.md) | [JSON](specification_followup/results.json) |
| [۹. کشش با ضرایب ثابت در سال/cohort](fixed_parameter_elasticities/README.md) | بدون بازتخمین B1/B2: ۲۱ نقطهٔ مرجع برای هر مدل و خلاصهٔ کشش‌های مشاهده‌ای همان سال/cohort. | [گزارش](fixed_parameter_elasticities/report.md) | [JSON](fixed_parameter_elasticities/results.json) |
| [۱۰. چهارده اجرای B1 توسعه‌یافته](b1_fourteen/README.md) | دو مقطع All، دو مقطع B، هشت پنل cohort و دو پنل تجمیعی؛ ضرایب مشترک/تاریخی و میانگین مخارج و مربع آن طبق تأیید اولیهٔ صاحب پروژه. | [گزارش تاریخی](b1_fourteen/report.md) | [JSON اولیه](b1_fourteen/results.json) و [اکسل اولیه](https://github.com/sinaamiri9000-collab/paneldemand/blob/dfc9abd6c84e4326a90c1faf2490826dfc6b1796/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) |
| [۱۱. اصلاح سه معادلهٔ مشارکت](marital_participation_sensitivity/run.py) | حذف متغیر مجرد و میانگین آن فقط از سه Probit دارای جداسازی؛ سپس بازتخمین کامل سیستم و مقایسه با نتایج قبلی. | در چت | [JSON](marital_participation_sensitivity/results.json) |
| [۱۲. حساسیت مغزها در cohort ۱۴۰۱](cohort1401_nuts_sensitivity/run.py) | روش‌های مختلف محاسبهٔ کشش، ۱۱ تصریح کنترل/CF/وزن، و کنترل یک نقطهٔ شروع دیگر؛ QUAIDS و S&Y ثابت. | در چت | [JSON](cohort1401_nuts_sensitivity/results.json) |
| [۱۳. حذف میانگین مربع مخارج از ده پنل](b1_fourteen_no_exp_square/README.md) | هشت cohort و دو پنل تجمیعی دوباره تخمین زده شدند؛ چهار مقطع قبلی و فرم QUAIDS/S&Y حفظ شده‌اند. | [گزارش](b1_fourteen_no_exp_square/report.md) | [JSON](b1_fourteen_no_exp_square/results.json) و [اکسل ۱۴مدلی](b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) |

در بستهٔ ۱۲، خطای شمارش ستون‌ها در شاخص قدرت ابزارهای درآمدِ مرحلهٔ اول بستهٔ ۱۰ اصلاح شده است. آمار ذخیره‌شدهٔ قدیمیِ `excluded_current_income_*` را برای استنباط استفاده نکنید؛ ضرایب مرحلهٔ اول، CF و برازش‌های تاریخی تغییر نکرده‌اند. شاخص بازحساب‌شده برای cohort ۱۴۰۱ در نتایج بستهٔ ۱۲ موجود است و کد تولید شاخص برای اجراهای بعدی اصلاح شده است.

## کد مشترک و بازتولید

- [کد مشترک](common/README.md): ساخت قیمت، تخمین عمومی، جبر QUAIDS و covariance چندمرحله‌ای. کد package اصلی pyquaidsce به نسخهٔ pin‌شده در [requirements.txt](requirements.txt) وابسته است.
- [آزمون‌های کد](tests/README.md): صحت فرمول‌ها، مشتق‌ها و استنباط؛ این پوشه یک بستهٔ تجربی جدید نیست.

```bash
python -m pip install -r pilot/requirements.txt
python -m unittest discover -s pilot/tests -p "test_*.py"
python -m unittest pilot.cohort1401_nuts_sensitivity.test_checks
```

داده‌ها، fitted objects و influenceهای خانوار در `intermediate/pilot_inputs/` باقی مانده‌اند و در GitHub منتشر نمی‌شوند. کلاس‌های قدیمی pickle سازگار نگه داشته شده‌اند. هیچ تخمین جدیدی برای این مرتب‌سازی اجرا نشده است.

## مسیرهای قبلی

[layout_manifest.json](layout_manifest.json) مسیر قبلی و جدید هر فایل و SHA256 تمام ۹ JSON تاریخی را ثبت می‌کند. JSONها دقیقاً همان محتوا را دارند؛ برخی رشته‌های فرادادهٔ داخل آن‌ها ممکن است هنوز مسیر تاریخی قبل از انتقال را نشان دهند و از طریق همین جدول قابل بازیابی‌اند. لینک‌ها و دستورهای گزارش‌های Markdown، کدها و راهنمای مخزن به مسیر جدید اصلاح شده‌اند. نسخهٔ چیدمان قبلی در commit `0f4caf5594c71749fabcdcdf1151b87975737883` و تاریخچهٔ Git در دسترس است.
