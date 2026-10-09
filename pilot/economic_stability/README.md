# ۵. ثبات زمانی و اهمیت اقتصادی

مقایسهٔ قبل/بعد ۱۳۹۷ با استنباط چندمرحله‌ای و آزمایش مدل بدون S&Y/CF؛ چند اجرا یک بسته‌اند.

[گزارش کامل](report.md) · [نتایج](results_frame_stability.json) · [راهنمای همهٔ بسته‌ها](../README.md)

نتایج مدل ساده‌تر بدون S&Y و CF در [results_plain_stability.json](results_plain_stability.json) است.

ورودی این مرحله به [بستهٔ قبلی](../cohort/README.md) و cacheهای خصوصی همان نمونه/قیمت در `intermediate/pilot_inputs/` وابسته است. دستور تهیهٔ stageهای لازم در گزارش این بسته ثبت شده است.

دستورها از ریشهٔ مخزن اجرا می‌شوند. برای مطالعهٔ نتایج نیازی به اجرای دوباره نیست؛ دستورهای زیر برای بازتولیدند.

```bash
python -m pilot.economic_stability.frame_stability --inputs intermediate/pilot_inputs
python -m pilot.economic_stability.plain_stability --inputs intermediate/pilot_inputs
python -m pilot.economic_stability.score_stability --inputs intermediate/pilot_inputs
python -m pilot.economic_stability.write_frame_report
```

کد عمومی تخمین در [common](../common/README.md) بازاستفاده می‌شود. کدهای این پوشه ورودی/تصریح و گزارش مخصوص همین بسته را مشخص می‌کنند. اشیای مدل و دادهٔ خانوار در پوشهٔ خصوصی intermediate نگهداری می‌شوند.
