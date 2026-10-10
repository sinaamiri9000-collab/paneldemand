# راهنمای بسته‌های آزمایشی Panel B

تمام فایل‌های موجود مرتب شده‌اند: **۹ بسته، ۹ گزارش جامع، ۱۰ فایل نتایج JSON و یک مرور ادبیات**. نتایج تاریخی حفظ شده‌اند؛ بستهٔ نهم فقط محاسبهٔ کشش با ضرایب قبلی است. هر پوشه شامل کد مخصوص همان بسته، گزارش و نتایج آن است؛ هسته و ابزارهای مشترک در `common/` و آزمون‌های صحت کد در `tests/` قرار دارند.

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

## کد مشترک و بازتولید

- [کد مشترک](common/README.md): ساخت قیمت، تخمین عمومی، جبر QUAIDS و covariance چندمرحله‌ای. کد package اصلی pyquaidsce به نسخهٔ pin‌شده در [requirements.txt](requirements.txt) وابسته است.
- [آزمون‌های کد](tests/README.md): صحت فرمول‌ها، مشتق‌ها و استنباط؛ این پوشه یک بستهٔ تجربی جدید نیست.

```bash
python -m pip install -r pilot/requirements.txt
python -m unittest discover -s pilot/tests -p "test_*.py"
```

داده‌ها، fitted objects و influenceهای خانوار در `intermediate/pilot_inputs/` باقی مانده‌اند و در GitHub منتشر نمی‌شوند. کلاس‌های قدیمی pickle سازگار نگه داشته شده‌اند. هیچ تخمین جدیدی برای این مرتب‌سازی اجرا نشده است.

## مسیرهای قبلی

[layout_manifest.json](layout_manifest.json) مسیر قبلی و جدید هر فایل و SHA256 تمام ۹ JSON تاریخی را ثبت می‌کند. JSONها دقیقاً همان محتوا را دارند؛ برخی رشته‌های فرادادهٔ داخل آن‌ها ممکن است هنوز مسیر تاریخی قبل از انتقال را نشان دهند و از طریق همین جدول قابل بازیابی‌اند. لینک‌ها و دستورهای گزارش‌های Markdown، کدها و راهنمای مخزن به مسیر جدید اصلاح شده‌اند. نسخهٔ چیدمان قبلی در commit `0f4caf5594c71749fabcdcdf1151b87975737883` و تاریخچهٔ Git در دسترس است.
