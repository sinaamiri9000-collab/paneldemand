# ۳. جایگزینی wave با cohort

مدل Mundlak/S&Y با دامی cohort، بدون wave و سال/فصل.

[گزارش کامل](report.md) · [نتایج](results.json) · [راهنمای همهٔ بسته‌ها](../README.md)

ورودی این مرحله به [بستهٔ قبلی](../no_year_season/README.md) و cacheهای خصوصی همان نمونه/قیمت در `intermediate/pilot_inputs/` وابسته است. دستور تهیهٔ stageهای لازم در گزارش این بسته ثبت شده است.

دستورها از ریشهٔ مخزن اجرا می‌شوند. برای مطالعهٔ نتایج نیازی به اجرای دوباره نیست؛ دستورهای زیر برای بازتولیدند.

```bash
python -m pilot.cohort.run --inputs intermediate/pilot_inputs
python -m pilot.cohort.write_report
```

کد عمومی تخمین در [common](../common/README.md) بازاستفاده می‌شود. کدهای این پوشه ورودی/تصریح و گزارش مخصوص همین بسته را مشخص می‌کنند. اشیای مدل و دادهٔ خانوار در پوشهٔ خصوصی intermediate نگهداری می‌شوند.
