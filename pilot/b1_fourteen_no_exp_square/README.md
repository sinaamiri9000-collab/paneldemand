# بازتخمین ۱۰ مدل پنلی بدون میانگین مربع لگاریتم مخارج

**وضعیت:** این پوشه نسخهٔ قبل، با میانگین CF، را حفظ می‌کند. [بستهٔ ۱۵](../b1_fourteen_no_mean_cf/README.md) و اکسل فعال، نسخهٔ جدید بدون میانگین CF هستند. [اکسل متناظر این بسته](https://github.com/sinaamiri9000-collab/paneldemand/blob/be4e5f48417670c5fab24f40567e58c4c941e309/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx) در تاریخچه نگهداری می‌شود.

**مبنا:** ده پنل [بستهٔ ۱۰](../b1_fourteen/README.md)، با حفظ [اصلاح مشارکت سه مدل در بستهٔ ۱۱](../marital_participation_sensitivity/README.md). همان شناسه‌های `Panel_<cohort>` و `Panel_B_common` / `Panel_B_history` استفاده می‌شوند؛ چهار مدل `CS_*` از نتایج بستهٔ ۱۰ بازاستفاده شده‌اند.

طبق درخواست ۲۰۲۶-۱۰-۱۲، از هشت پنل cohort و دو پنل تجمیعی، میانگین مربع لگاریتم مخارج حذف شده است. در پنل تاریخی، دو میانگین تعامل دوره با مربع مخارج نیز حذف شده‌اند. میانگین خودِ لگاریتم مخارج باقی است؛ جملهٔ درجه‌دوم QUAIDS، S&Y، CF، قیود، دامی‌ها، نمونه و قیمت‌ها تغییر نکرده‌اند. اصلاح قبلی سه معادلهٔ مشارکت نیز حفظ شده است.

- [گزارش و مقایسهٔ قبل/بعد](report.md)
- [نتایج ۱۴ مدل: چهار مقطع قبلی و ده پنل جدید](results.json)
- [اکسل متناظر این نسخه با میانگین CF](https://github.com/sinaamiri9000-collab/paneldemand/blob/be4e5f48417670c5fab24f40567e58c4c941e309/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx)
- [نسخهٔ تاریخی اکسل با میانگین مربع](https://github.com/sinaamiri9000-collab/paneldemand/blob/dfc9abd6c84e4326a90c1faf2490826dfc6b1796/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx)

```bash
python -m pilot.b1_fourteen_no_exp_square.run --run-all --workers 2
python -m pilot.b1_fourteen_no_exp_square.publish
python -m unittest pilot.b1_fourteen_no_exp_square.test_checks
```

دو subprocess مستقل با یک BLAS thread استفاده می‌شوند. fitted objects و داده‌ها در `intermediate/pilot_inputs/b1_fourteen_no_exp_square/` حفظ می‌شوند و وارد Git نمی‌شوند. گزارش و JSON اولیهٔ بستهٔ ۱۴ اجرا برای مقایسه حفظ شده‌اند؛ فقط اکسلِ فعال آن بسته با نتایج جدید به‌روز شده است.
