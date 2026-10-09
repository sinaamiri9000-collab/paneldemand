# ۴. آزمون‌های مقدماتی ثبات

آزمون‌های اکتشافی و conditional ثبات زمانی/cohort؛ همراه مرور ادبیات. محدودیت‌های این مرحله در گزارش حفظ شده‌اند.

[گزارش کامل](report.md) · [نتایج](results.json) · [راهنمای همهٔ بسته‌ها](../README.md)

[مرور ادبیات و محدودیت آزمون‌ها](literature_stability.md)

ورودی این مرحله به [بستهٔ قبلی](../cohort/README.md) و cacheهای خصوصی همان نمونه/قیمت در `intermediate/pilot_inputs/` وابسته است. دستور تهیهٔ stageهای لازم در گزارش این بسته ثبت شده است.

دستورها از ریشهٔ مخزن اجرا می‌شوند. برای مطالعهٔ نتایج نیازی به اجرای دوباره نیست؛ دستورهای زیر برای بازتولیدند.

```bash
python -m pilot.preliminary_stability.stability --inputs intermediate/pilot_inputs
python -m pilot.preliminary_stability.write_stability_report
```

کد عمومی تخمین در [common](../common/README.md) بازاستفاده می‌شود. کدهای این پوشه ورودی/تصریح و گزارش مخصوص همین بسته را مشخص می‌کنند. اشیای مدل و دادهٔ خانوار در پوشهٔ خصوصی intermediate نگهداری می‌شوند.
