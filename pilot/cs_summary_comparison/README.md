# ۱۶. سه روش خلاصه‌سازی کشش مقطعی مشترک و تاریخی

**مبنا:** چهار مدل مقطعی فعال بستهٔ ۱۵، commit `843d9d0`؛ پارامترهای همان اجراها ثابت‌اند. هیچ RF، Probit یا QUAIDS دوباره تخمین زده نشده و اکسل اصلی ۱۴مدلی تغییر نکرده است.

سه مقایسه برای All و B انجام می‌شود:

1. کشش در سه نقطهٔ میانگین واقعی ۱۳۹۲–۱۳۹۶، ۱۳۹۷–۱۳۹۸ و ۱۳۹۹–۱۴۰۳، سپس میانگین با وزن `N_r/N`، یکسان برای common/history همان نمونه.
2. مدل common در میانگین کل؛ مدل history با هر سه رژیم در همان ورودی‌های پایه و سپس همان وزن دوره‌ها. قرارداد CF، همان `common_reference_period` قبلی است: میانگین CF خاص هر مدل ثابت می‌ماند و RF در سناریوی فرضی بازسازی نمی‌شود.
3. کشش تمام خانوار–سال‌ها با دورهٔ واقعی: میانگین، میانه، P1/P99 و اعتبار سهم، برای کل و هر دوره. میانگین مساوی خانوار–سال است، نه میانگین مساوی شناسه‌های خانوار گزارش قبلی. سهم‌های غیرمثبت نامعتبرند؛ کشش‌های افراطی مثبت/منفی با مخرج مثبت حفظ شده‌اند و trim/winsorize نمی‌شوند. اشتراک معتبر دو مدل نیز جدا گزارش شده است.

این تحلیل توصیفی است؛ SE، bootstrap یا آزمون معناداری تازه ندارد. مقایسهٔ مرجع مشترک، سناریوی تابعی و گاهی خارج از حمایت سال/cohort است. اختلاف‌ها اثر مجموع تفاوت RF/Probit/QUAIDS را دارند؛ اثر خالص ضرایب هسته یا تغییر علّی ترجیحات نیستند.

- [گزارش کامل سه مقایسه و همهٔ دوره‌ها](report.md)
- [اکسل ۱۶ شیت، ماتریس‌های کامل ۱۲×۱۲ و تشخیص‌ها](CS_common_history_three_methods.xlsx)
- [JSON کامل و کنترل صحت](results.json)
- [کد بازسازی ورودی‌ها](prepare.py)، [محاسبه](run.py)، [انتشار خروجی](export.py)، [کنترل قراردادها](tests.py)
- [راهنمای همهٔ بسته‌ها](../README.md)

```bash
python -m pip install -r pilot/requirements.txt
python -m pilot.cs_summary_comparison.prepare --inputs intermediate/pilot_inputs
python -m pilot.cs_summary_comparison.run
python -m pilot.cs_summary_comparison.export
python -m unittest pilot.cs_summary_comparison.tests
```

`--work` در prepare/run مسیر خصوصی cache را مشخص می‌کند؛ پیش‌فرض `intermediate/pilot_inputs/cs_summary_comparison` است. دو clean و mapping با هش ثابت کنترل می‌شوند. sample pickleهای این کد باید فایل‌های ساخته‌شده و مورد اعتماد پروژه باشند. داده و آرایه‌های کشش مشاهده‌ای فقط در work خصوصی باقی می‌مانند. خروجی منتشرشده فقط aggregate است.

دستور اجرای واقعی این بررسی، با ورودی‌های دریافت‌شده از Drive و مسیر cache خصوصی موجود، معادل دستورهای بالا با `--inputs /workspace/research/data` و `--work /workspace/research/cs_comparison_private` بود؛ این مسیرهای محیط اجرا جزو قرارداد کد نیستند.
