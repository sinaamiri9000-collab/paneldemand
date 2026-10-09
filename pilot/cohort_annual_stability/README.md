# ۶. آزمون بلوک‌ها بین cohort و سال

آزمون جداگانهٔ beta، lambda و Gamma بین cohortها، سپس آزمون مستقل سالانه با کنترل تغییر سطح.

[گزارش کامل](report.md) · [نتایج](results.json) · [راهنمای همهٔ بسته‌ها](../README.md)

ورودی این مرحله به [بستهٔ قبلی](../economic_stability/README.md) و cacheهای خصوصی همان نمونه/قیمت در `intermediate/pilot_inputs/` وابسته است. دستور تهیهٔ stageهای لازم در گزارش این بسته ثبت شده است.

دستورها از ریشهٔ مخزن اجرا می‌شوند. برای مطالعهٔ نتایج نیازی به اجرای دوباره نیست؛ دستورهای زیر برای بازتولیدند.

```bash
python -m pilot.cohort_annual_stability.stability_path --inputs intermediate/pilot_inputs
python -m pilot.cohort_annual_stability.write_path_report
```

کد عمومی تخمین در [common](../common/README.md) بازاستفاده می‌شود. کدهای این پوشه ورودی/تصریح و گزارش مخصوص همین بسته را مشخص می‌کنند. اشیای مدل و دادهٔ خانوار در پوشهٔ خصوصی intermediate نگهداری می‌شوند.
