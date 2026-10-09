# ۸. پیگیری پنج تصریح و مشتق مستقیم

Pooled با سن/RF یکسان، B1/B2 بدون میانگین فصل و کشش‌های مستقیم S&Y؛ آخرین بستهٔ تکمیل‌شده.

[گزارش کامل](report.md) · [نتایج](results.json) · [راهنمای همهٔ بسته‌ها](../README.md)

ورودی این مرحله به [بستهٔ قبلی](../specification_suite/README.md) و cacheهای خصوصی همان نمونه/قیمت در `intermediate/pilot_inputs/` وابسته است. دستور تهیهٔ stageهای لازم در گزارش این بسته ثبت شده است.

دستورها از ریشهٔ مخزن اجرا می‌شوند. برای مطالعهٔ نتایج نیازی به اجرای دوباره نیست؛ دستورهای زیر برای بازتولیدند.

```bash
python -m pilot.specification_followup.specification_followup --inputs intermediate/pilot_inputs --model P0_matched
python -m pilot.specification_followup.specification_followup --inputs intermediate/pilot_inputs --model B1_no_season_means
python -m pilot.specification_followup.specification_followup --inputs intermediate/pilot_inputs --model B2_no_season_means
python -m pilot.specification_followup.specification_followup --inputs intermediate/pilot_inputs --direct-old B0 B1 B2
python -m pilot.specification_followup.specification_followup --inputs intermediate/pilot_inputs --assemble
python -m pilot.specification_followup.write_followup_report
```

کد عمومی تخمین در [common](../common/README.md) بازاستفاده می‌شود. کدهای این پوشه ورودی/تصریح و گزارش مخصوص همین بسته را مشخص می‌کنند. اشیای مدل و دادهٔ خانوار در پوشهٔ خصوصی intermediate نگهداری می‌شوند.

برای اجراهای هم‌زمان `--threads 1` بدهید؛ بخش پرحافظهٔ استنباط قفل مشترک دارد. با `--assemble` نتایج cache دوباره تجمیع می‌شوند؛ برای حفظ نسخهٔ تاریخی، قبل از نوشتن خروجی تازه آن را آرشیو کنید.
