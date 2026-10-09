# ۷. بستهٔ پنج تصریح

B0، B1، B2، B3 و P0: بررسی میانگین CF، میانگین مخارج و کنترل‌های جمعیت‌شناختی.

[گزارش کامل](report.md) · [نتایج](results.json) · [راهنمای همهٔ بسته‌ها](../README.md)

ورودی این مرحله به [بستهٔ قبلی](../cohort/README.md) و cacheهای خصوصی همان نمونه/قیمت در `intermediate/pilot_inputs/` وابسته است. دستور تهیهٔ stageهای لازم در گزارش این بسته ثبت شده است.

دستورها از ریشهٔ مخزن اجرا می‌شوند. برای مطالعهٔ نتایج نیازی به اجرای دوباره نیست؛ دستورهای زیر برای بازتولیدند.

```bash
python -m pilot.specification_suite.specification_suite --inputs intermediate/pilot_inputs
python -m pilot.specification_suite.write_specification_report
```

کد عمومی تخمین در [common](../common/README.md) بازاستفاده می‌شود. کدهای این پوشه ورودی/تصریح و گزارش مخصوص همین بسته را مشخص می‌کنند. اشیای مدل و دادهٔ خانوار در پوشهٔ خصوصی intermediate نگهداری می‌شوند.
