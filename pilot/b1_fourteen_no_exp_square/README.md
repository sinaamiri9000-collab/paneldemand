# بازتخمین ۱۰ مدل پنلی بدون میانگین مربع لگاریتم مخارج

طبق درخواست ۲۰۲۶-۱۰-۱۲، از هشت پنل cohort و دو پنل تجمیعی، میانگین مربع لگاریتم مخارج حذف شده است. در پنل تاریخی، دو میانگین تعامل دوره با مربع مخارج نیز حذف شده‌اند. میانگین خودِ لگاریتم مخارج باقی است؛ جملهٔ درجه‌دوم QUAIDS، S&Y، CF، قیود، دامی‌ها، نمونه و قیمت‌ها تغییر نکرده‌اند. اصلاح قبلی سه معادلهٔ مشارکت نیز حفظ شده است.

- [گزارش و مقایسهٔ قبل/بعد](report.md)
- [نتایج ۱۴ مدل: چهار مقطع قبلی و ده پنل جدید](results.json)
- [اکسل به‌روز ۱۴ شیت](../b1_fourteen/paneldemand_B1_fourteen_runs.xlsx)
- [نسخهٔ تاریخی اکسل با میانگین مربع](https://github.com/sinaamiri9000-collab/paneldemand/blob/dfc9abd6c84e4326a90c1faf2490826dfc6b1796/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx)

```bash
python -m pilot.b1_fourteen_no_exp_square.run --run-all --workers 2
python -m pilot.b1_fourteen_no_exp_square.publish
python -m unittest pilot.b1_fourteen_no_exp_square.test_checks
```

دو subprocess مستقل با یک BLAS thread استفاده می‌شوند. fitted objects و داده‌ها در `intermediate/pilot_inputs/b1_fourteen_no_exp_square/` حفظ می‌شوند و وارد Git نمی‌شوند. گزارش و JSON اولیهٔ بستهٔ ۱۴ اجرا برای مقایسه حفظ شده‌اند؛ فقط اکسلِ فعال آن بسته با نتایج جدید به‌روز شده است.
