# راهنمای بسته‌های آزمایشی Panel B

فایل‌ها در **۱۵ بستهٔ آزمایشی** نگهداری می‌شوند. نتایج تاریخی حفظ شده‌اند؛ بستهٔ نهم فقط محاسبهٔ کشش با ضرایب قبلی است و بستهٔ دهم ۱۴ اجرای اولیهٔ مقطع/پنل و تاریخی است. بستهٔ سیزدهم میانگین مربع مخارج و بستهٔ پانزدهم، علاوه بر آن، میانگین CF را از ده پنل حذف کرده‌اند. هر پوشه کد و نتایج همان بسته را دارد؛ گزارش بسته‌های ۱۱، ۱۲ و ۱۴، طبق درخواست صاحب پروژه، در چت ارائه شده است. هسته و ابزارهای مشترک در `common/` و آزمون‌های صحت کد در `tests/` قرار دارند.

نسخهٔ [اکسل کامل مارشالی ۱۲×۱۲](fixed_parameter_elasticities/paneldemand_B1_B2_marshallian_12x12_1392_1403.xlsx) نیز در بستهٔ نهم قرار دارد.

برای نسخهٔ فعلی ۱۴ مدل، [بستهٔ پانزدهم](b1_fourteen_no_mean_cf/README.md)، [گزارش حذف میانگین CF](b1_fourteen_no_mean_cf/report.md) و [اکسل به‌روز ۱۴ شیت](b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) را ببینید. بسته‌های دهم و سیزدهم، گزارش و نتایج نسخه‌های قبلی را حفظ می‌کنند.

دو حساسیت [بستهٔ ۱۴](cohort1401_no_exp_square_followup/README.md) فقط cohort ۱۴۰۱ را بررسی کردند؛ بستهٔ ۱۵ حذف میانگین CF مدل A آن بسته را به همهٔ ده پنل گسترش می‌دهد. برای کشش‌های سالانه و cohort با ضرایب ثابت از [بستهٔ ۹](fixed_parameter_elasticities/README.md) و برای مقایسهٔ B1 و B2 آن مرحله از [بستهٔ ۸](specification_followup/README.md) شروع کنید.

**تفاوت نام B1 در مراحل مختلف:** B1 بسته‌های ۷–۹ میانگین CF دارد، اما میانگین مخارج ندارد؛ B2 همان مدل با میانگین لگاریتم مخارج است. «B1 توسعه‌یافته» در بستهٔ ۱۰، با تأیید صاحب پروژه، میانگین لگاریتم مخارج و میانگین مربع آن را هم دارد. بستهٔ ۱۳ فقط میانگین مربع را حذف می‌کند؛ بستهٔ ۱۵ میانگین CF را نیز حذف می‌کند و CF جاری را نگه می‌دارد. بنابراین نام B1 به‌تنهایی مشخصات مدل را تعیین نمی‌کند.

## مبنا و تغییر هر بسته

«مبنا» مدل یا ورودی مرجع است؛ ترتیب شماره‌ها به معنی انباشته‌شدن همهٔ تغییرات نیست. هر README جزئیات اجراهای داخل آن بسته، کد و دستور بازتولید را معرفی می‌کند. خروجی‌های تاریخی برای مقایسه حفظ شده‌اند و الزاماً تصریح نهایی مقاله نیستند.

| بسته | مبنا | تغییر یا محاسبه | خروجی |
| --- | --- | --- | --- |
| [۱. پایلوت اولیه](initial/README.md) | دادهٔ پاک‌سازی‌شده و mapping | ساخت قیمت از All؛ مقایسهٔ Pooled/Mundlak روی همان Panel B با S&Y و CF | [گزارش](initial/report.md) · [JSON](initial/results.json) |
| [۲. بدون سال و فصل](no_year_season/README.md) | Mundlak بستهٔ ۱ | حذف سال/فصل؛ حفظ wave؛ فقط بازتخمین Mundlak | [گزارش](no_year_season/report.md) · [JSON](no_year_season/results.json) |
| [۳. cohort به جای wave](cohort/README.md) | بستهٔ ۲ | حذف wave؛ افزودن دامی cohort؛ همچنان بدون سال/فصل | [گزارش](cohort/report.md) · [JSON](cohort/results.json) |
| [۴. ثبات مقدماتی](preliminary_stability/README.md) | بستهٔ ۳ | آزمون‌های اکتشافی ثبات زمانی/cohort با ثابت‌گرفتن مراحل تولید CF و مشارکت؛ محدودیت‌ها در گزارش | [گزارش](preliminary_stability/report.md) · [JSON](preliminary_stability/results.json) |
| [۵. ثبات و اهمیت اقتصادی](economic_stability/README.md) | بستهٔ ۳ | قبل/بعد ۱۳۹۷ با استنباط چندمرحله‌ای؛ جداگانه مدل بدون S&Y/CF | [گزارش](economic_stability/report.md) · [JSON اصلی](economic_stability/results_frame_stability.json) · [JSON ساده‌تر](economic_stability/results_plain_stability.json) |
| [۶. ثبات بلوک‌ها](cohort_annual_stability/README.md) | مدل بستهٔ ۳ و ابزارهای بستهٔ ۵ | آزمون جداگانهٔ β، λ، Γ بین cohortها؛ سپس سال‌ها با کنترل تغییر سطح سال | [گزارش](cohort_annual_stability/report.md) · [JSON](cohort_annual_stability/results.json) |
| [۷. پنج تصریح](specification_suite/README.md) | نمونه/قیمت بستهٔ ۳؛ طراحی B0 جدید | B0، B1، B2، B3، P0؛ بررسی میانگین CF، میانگین مخارج و میانگین‌های جمعیت‌شناختی؛ کنترل سال/فصل | [گزارش](specification_suite/report.md) · [JSON](specification_suite/results.json) |
| [۸. پیگیری پنج تصریح](specification_followup/README.md) | B0/B1/B2 بستهٔ ۷ | Pooled با سن و مرحلهٔ اول یکسان با B0؛ B1/B2 بدون میانگین فصل؛ مشتق مستقیم S&Y | [گزارش](specification_followup/report.md) · [JSON](specification_followup/results.json) |
| [۹. کشش با ضرایب ثابت](fixed_parameter_elasticities/README.md) | B1/B2 بدون میانگین فصل در بستهٔ ۸ | بدون بازتخمین؛ ۲۱ نقطهٔ مرجع کل/سال/cohort و خلاصهٔ کشش‌های مشاهده‌ای | [گزارش](fixed_parameter_elasticities/report.md) · [JSON](fixed_parameter_elasticities/results.json) |
| [۱۰. چهارده اجرای اولیه](b1_fourteen/README.md) | توسعهٔ B1 بدون میانگین فصل بستهٔ ۸ | چهار مقطع، هشت cohort، دو پنل تجمیعی؛ مشترک/تاریخی؛ افزودن میانگین مخارج و میانگین مربع آن به پنل‌ها | [گزارش تاریخی](b1_fourteen/report.md) · [JSON اولیه](b1_fourteen/results.json) |
| [۱۱. اصلاح مشارکت](marital_participation_sensitivity/README.md) | سه پنل بستهٔ ۱۰ | حذف مجرد/میانگین مجرد از Probit نان ۱۳۹۸ و ۱۴۰۱، سبزیجات ۱۳۹۹؛ بازتخمین تقاضا | [JSON](marital_participation_sensitivity/results.json)؛ گزارش در چت |
| [۱۲. حساسیت مغزها ۱۴۰۱](cohort1401_nuts_sensitivity/README.md) | Panel_1401 اصلاح‌شدهٔ بستهٔ ۱۱ | ۱۱ تصریح مستقل، روش‌ها/نقاط محاسبهٔ کشش و یک شروع عددی دیگر؛ QUAIDS/S&Y ثابت | [JSON](cohort1401_nuts_sensitivity/results.json)؛ گزارش در چت |
| [۱۳. ده پنل بدون میانگین مربع](b1_fourteen_no_exp_square/README.md) | پنل‌های بستهٔ ۱۰ با اصلاح‌های بستهٔ ۱۱ | حذف میانگین مربع مخارج و تعامل‌های تاریخی آن؛ بازتخمین ده پنل؛ چهار مقطع قبلی ثابت | [گزارش](b1_fourteen_no_exp_square/report.md) · [JSON قبل با میانگین CF](b1_fourteen_no_exp_square/results.json) |
| [۱۴. دو پیگیری ۱۴۰۱](cohort1401_no_exp_square_followup/README.md) | Panel_1401 بستهٔ ۱۳ | جداگانه حذف میانگین CF یا وزن‌دارکردن همهٔ مراحل؛ بدون میانگین مربع؛ اکسل فعلی ثابت | [JSON](cohort1401_no_exp_square_followup/results.json)؛ گزارش در چت |
| [۱۵. ده پنل بدون میانگین CF](b1_fourteen_no_mean_cf/README.md) | ده پنل بستهٔ ۱۳؛ تغییر مثل مدل A بستهٔ ۱۴ | حذف میانگین CF از مشارکت/تقاضا؛ حفظ CF جاری و نبود میانگین مربع مخارج؛ چهار مقطع ثابت | [گزارش](b1_fourteen_no_mean_cf/report.md) · [JSON فعلی ۱۴ مدل](b1_fourteen_no_mean_cf/results.json) |

**محل اکسل فعلی:** [فایل ۱۴شیتی](b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) برای حفظ مسیر دانلود در پوشهٔ ۱۰ مانده است، اما با JSON بستهٔ **۱۵** تطبیق دارد. JSON و گزارش داخل پوشه‌های ۱۰ و ۱۳ همچنان تاریخی‌اند. [اکسل قبل با میانگین CF](https://github.com/sinaamiri9000-collab/paneldemand/blob/be4e5f48417670c5fab24f40567e58c4c941e309/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) و [اکسل اولیه](https://github.com/sinaamiri9000-collab/paneldemand/blob/dfc9abd6c84e4326a90c1faf2490826dfc6b1796/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) در تاریخچهٔ Git در دسترس‌اند.

در بستهٔ ۱۲، خطای شمارش ستون‌ها در شاخص قدرت ابزارهای درآمدِ مرحلهٔ اول بستهٔ ۱۰ اصلاح شده است. آمار ذخیره‌شدهٔ قدیمیِ `excluded_current_income_*` را برای استنباط استفاده نکنید؛ ضرایب مرحلهٔ اول، CF و برازش‌های تاریخی تغییر نکرده‌اند. شاخص بازحساب‌شده برای cohort ۱۴۰۱ در نتایج بستهٔ ۱۲ موجود است و کد تولید شاخص برای اجراهای بعدی اصلاح شده است.

## کد مشترک و بازتولید

- [کد مشترک](common/README.md): ساخت قیمت، تخمین عمومی، جبر QUAIDS و covariance چندمرحله‌ای. کد package اصلی pyquaidsce به نسخهٔ pin‌شده در [requirements.txt](requirements.txt) وابسته است.
- [آزمون‌های کد](tests/README.md): صحت فرمول‌ها، مشتق‌ها و استنباط؛ این پوشه یک بستهٔ تجربی جدید نیست.

```bash
python -m pip install -r pilot/requirements.txt
python -m unittest discover -s pilot/tests -p "test_*.py"
python -m unittest pilot.cohort1401_nuts_sensitivity.test_checks
```

داده‌ها، fitted objects و influenceهای خانوار در `intermediate/pilot_inputs/` باقی مانده‌اند و در GitHub منتشر نمی‌شوند. کلاس‌های قدیمی pickle سازگار نگه داشته شده‌اند.

## مسیرهای قبلی

[layout_manifest.json](layout_manifest.json) مسیر قبلی و جدید هر فایل و SHA256 تمام ۹ JSON تاریخی را ثبت می‌کند. JSONها دقیقاً همان محتوا را دارند؛ برخی رشته‌های فرادادهٔ داخل آن‌ها ممکن است هنوز مسیر تاریخی قبل از انتقال را نشان دهند و از طریق همین جدول قابل بازیابی‌اند. لینک‌ها و دستورهای گزارش‌های Markdown، کدها و راهنمای مخزن به مسیر جدید اصلاح شده‌اند. نسخهٔ چیدمان قبلی در commit `0f4caf5594c71749fabcdcdf1151b87975737883` و تاریخچهٔ Git در دسترس است.
