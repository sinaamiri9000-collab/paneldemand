# بستهٔ ۱۴ مدل B1 توسعه‌یافته

**نسخهٔ فعال اکسل — ۲۰۲۶-۱۰-۱۲:** ده شیت پنلی با بازتخمین بدون میانگین مربع لگاریتم مخارج به‌روز شده‌اند؛ چهار شیت مقطعی تغییر نکرده‌اند. [گزارش و نتایج فعلی](../b1_fourteen_no_exp_square/README.md) در بستهٔ جدید هستند. گزارش، JSON و توضیحات زیر نسخهٔ تاریخی با میانگین مربع را ثبت می‌کنند. [اکسل تاریخی](https://github.com/sinaamiri9000-collab/paneldemand/blob/dfc9abd6c84e4326a90c1faf2490826dfc6b1796/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) نیز در commit قبلی در دسترس است.

این بسته شامل دو مدل مقطع تجمیعی All، دو مقطع تجمیعی B، هشت پنل سه‌سالهٔ مستقل، و دو پنل تجمیعی B است. سه جفت تجمیعی با/بدون تفاوت ضرایب تاریخی تخمین زده می‌شوند. دوره‌ها ۱۳۹۲–۱۳۹۶، ۱۳۹۷–۱۳۹۸ و ۱۳۹۹–۱۴۰۳ هستند.

صاحب پروژه پس از بررسی چت، **افزودن میانگین مخارج و میانگین مربع لگاریتم مخارج** را تأیید کرده است؛ بنابراین نسخهٔ پنلی توسعهٔ B1 است. نسخهٔ تاریخی پنلی میانگین تعامل‌های واقعی دوره×متغیر را نیز دارد. تحصیلات، wave و قید انحنای موضعی وجود ندارند. منابع اصلی در [refrence](../../refrence/README.md) بررسی شده‌اند.

- [گزارش جامع و همهٔ پارامترها و ماتریس‌ها](report.md)
- [نتایج تجمیعی](results.json)
- [اکسل ۱۴ شیت، مشخصات و ماتریس کامل مارشالی و کشش مخارج](paneldemand_B1_fourteen_runs.xlsx)
- [manifest و جریان نمونه](manifest.json)
- [کد اجرا](run.py)، [هستهٔ تاریخی](historical_core.py)، [خروجی گزارش/اکسل](export.py)
- [معادلات و منابع روش](methodology.md)، [پروبیت با رفع separation](probit_adapter.py)، [بازبینی مشارکت‌های ذخیره‌شده](selection_audit.py): فقط separation تأییدشده با Jeffreys طبق Kosmidis–Firth (2021) اصلاح می‌شود؛ بدون حذف مشاهده/متغیر.
- [آزمون‌های بلوکی مشروط](conditional_tests.py): این covariance مراحل CF/Probit را ثابت می‌گیرد؛ برای نتیجهٔ نهایی مقاله کافی نیست.

اکسل با نمایش اولیهٔ ۸۵٪، ستون‌های باریک و بدون ردیف یا ستون ثابت باز می‌شود. ماتریس اول در ابتدای هر شیت است؛ مشخصات کامل زیر جدول‌ها قرار دارد و لینک «مشخصات کامل» در بالای شیت به آن می‌رود.

```bash
python -m pip install -r pilot/requirements.txt
python -m pilot.b1_fourteen.run --prepare
python -m unittest discover -s pilot/tests -p 'test_*.py'
python -m pilot.b1_fourteen.run --run-all --workers 2
python -m pilot.b1_fourteen.selection_audit
python -m pilot.b1_fourteen.run --run-all --workers 2
python -m pilot.b1_fourteen.run --refresh-results
# Optional provisional conditional block diagnostics, after point fits finish:
python -m pilot.b1_fourteen.conditional_tests CS_All_history
python -m pilot.b1_fourteen.conditional_tests CS_B_history
python -m pilot.b1_fourteen.conditional_tests Panel_B_history
python -m pilot.b1_fourteen.export
```

داده و fit/stage objects در `intermediate/pilot_inputs/b1_fourteen/` می‌مانند و منتشر نمی‌شوند. هر اجرا lock، cache و log مستقل دارد و اجرای مجدد از نتایج همگرای ذخیره‌شده ادامه می‌دهد. دو فرایند مستقل با یک thread در هر فرایند استفاده می‌شوند. گزارش‌های قبلی حفظ شده‌اند.
