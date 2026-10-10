# کشش‌ها در نقاط میانگین سال و cohort با ضرایب ثابت

محاسبهٔ پس از تخمین برای B1_no_season_means و B2_no_season_means: ۲۱ نقطهٔ مرجع برای هر مدل (کل نمونه، ۱۲ سال، ۸ cohort)، به همراه خلاصهٔ کشش‌های مشاهده‌ای همان زیرگروه‌ها. ضرایب و نمونهٔ برازش قبلی تغییر نمی‌کنند؛ هیچ تخمین دوباره‌ای انجام نمی‌شود.

- [گزارش و جدول‌ها/ماتریس‌های کامل](report.md)
- [نتایج با دقت کامل، ورودی‌های مرجع و خلاصه‌های مشاهده‌ای](results.json)
- [کد محاسبه](run.py) و [ساخت گزارش](write_report.py)
- [برازش اصلی مدل‌ها](../specification_followup/README.md)

از ریشهٔ مخزن و با cacheهای خصوصی برازش قبلی:

```bash
python -m pilot.fixed_parameter_elasticities.run --inputs intermediate/pilot_inputs
python -m pilot.fixed_parameter_elasticities.write_report
```

ورودی‌ها: priced_panel_106.parquet و suite_B1_no_season_means / suite_B2_no_season_means با پسوندهای _stage.pkl و _point.pkl در intermediate/pilot_inputs، به همراه نتایج ثبت‌شدهٔ specification_followup. میانگین‌های خانوار از سه موج اصلی و مرکزسازی‌ها از برازش اولیه حفظ می‌شوند. فقط نقطهٔ ارزیابی تغییر می‌کند. این بسته آزمون ناهمگنی ضرایب نیست و فاصلهٔ اطمینان تازه‌ای تولید نمی‌کند.
