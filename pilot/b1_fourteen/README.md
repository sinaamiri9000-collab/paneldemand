# بستهٔ ۱۴ مدل B1 توسعه‌یافته

**نسخهٔ فعال اکسل — ۲۰۲۶-۱۰-۱۲:** ده شیت پنلی با بازتخمین بدون میانگین CF و بدون میانگین مربع لگاریتم مخارج به‌روز شده‌اند؛ چهار شیت مقطعی تغییر نکرده‌اند. [گزارش و نتایج فعلی](../b1_fourteen_no_mean_cf/README.md) در بستهٔ جدید هستند. گزارش، JSON و توضیحات زیر نسخهٔ تاریخی با هر دو میانگین را ثبت می‌کنند. [اکسل تاریخی اولیه](https://github.com/sinaamiri9000-collab/paneldemand/blob/dfc9abd6c84e4326a90c1faf2490826dfc6b1796/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) و [نسخهٔ قبل با میانگین CF](https://github.com/sinaamiri9000-collab/paneldemand/blob/be4e5f48417670c5fab24f40567e58c4c941e309/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) در تاریخچه در دسترس‌اند.

این بسته شامل دو مدل مقطع تجمیعی All، دو مقطع تجمیعی B، هشت پنل سه‌سالهٔ مستقل، و دو پنل تجمیعی B است. سه جفت تجمیعی با/بدون تفاوت ضرایب تاریخی تخمین زده می‌شوند. دوره‌ها ۱۳۹۲–۱۳۹۶، ۱۳۹۷–۱۳۹۸ و ۱۳۹۹–۱۴۰۳ هستند.

مبنای طراحی، B1 بدون میانگین فصل در [بستهٔ ۸](../specification_followup/README.md) است؛ این بسته نمونه‌ها و ساختار ضرایب را گسترش می‌دهد:

| شناسه‌ها | نمونه و تفاوت |
| --- | --- |
| `CS_All_common` / `CS_All_history` | All به‌صورت مقطع تجمیعی؛ بدون میانگین خانوار؛ شیب مشترک / متفاوت بین سه دورهٔ تاریخی |
| `CS_B_common` / `CS_B_history` | همان دو تصریح مقطعی روی نمونهٔ B |
| `Panel_1392`، `1393`، `1394`، `1397`، `1398`، `1399`، `1400`، `1401` | هشت پنل مستقل؛ هر cohort سه سال پیاپی از سال نام‌گذاری‌شده |
| `Panel_B_common` / `Panel_B_history` | همهٔ هشت cohort با کنترل سطح cohort؛ شیب مشترک / متفاوت بین سه دورهٔ تاریخی |

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
