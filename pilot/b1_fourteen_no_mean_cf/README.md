# ۱۵. ده پنل بدون میانگین CF

**مبنا:** مجموعهٔ ۱۴ مدل [بستهٔ ۱۳](../b1_fourteen_no_exp_square/README.md)، بدون میانگین مربع لگاریتم مخارج. فقط `mean_cf_residual` از مشارکت و تقاضا حذف شده است، مانند مدل A در [بستهٔ ۱۴](../cohort1401_no_exp_square_followup/README.md).

هشت `Panel_<cohort>` و دو `Panel_B_common` / `Panel_B_history` دوباره تخمین زده می‌شوند. چهار `CS_*` میانگین CF ندارند و تغییر نمی‌کنند. CF جاری، میانگین لگاریتم مخارج، سایر کنترل‌ها، اصلاح سه مشارکت، نمونه، قیمت، QUAIDS و S&Y حفظ شده‌اند. RF از قبل وزن‌دار و ثابت است؛ Probit و IFGNLS مثل مدل A بدون وزن‌اند.

- [گزارش و مقایسهٔ قبل/بعد](report.md)
- [نتایج فعلی ۱۴ مدل و تمام ضرایب](results.json)
- [اکسل فعلی ۱۴شیتی با ماتریس‌های کامل مارشالی و کشش مخارج](../b1_fourteen/paneldemand_B1_fourteen_runs.xlsx)
- [اکسل قبل از حذف میانگین CF](https://github.com/sinaamiri9000-collab/paneldemand/blob/be4e5f48417670c5fab24f40567e58c4c941e309/pilot/b1_fourteen/paneldemand_B1_fourteen_runs.xlsx)
- [راهنمای همهٔ بسته‌ها](../README.md)

```bash
python -m pilot.b1_fourteen_no_mean_cf.run --run-all --workers 2
python -m pilot.b1_fourteen_no_mean_cf.publish
python -m unittest pilot.b1_fourteen_no_mean_cf.test_checks
```

اشیای مدل و logها در `intermediate/pilot_inputs/b1_fourteen_no_mean_cf/` خصوصی هستند. اکسل در مسیر قبلی حفظ شده؛ گزارش و JSON این پوشه مرجع فعلی‌اند و بستهٔ ۱۳ نسخهٔ قبل با میانگین CF را نگه می‌دارد.
