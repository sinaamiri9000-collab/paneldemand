# ۸. پیگیری پنج تصریح و مشتق مستقیم

پیگیری [بستهٔ پنج تصریح](../specification_suite/README.md) با سه بازتخمین و محاسبات پس از تخمین:

| اجرا | تغییر نسبت به بستهٔ قبلی |
| --- | --- |
| `P0_matched` | سن و مرحلهٔ اول مخارج/CF عین B0؛ مشارکت و تقاضا بدون سایر میانگین‌های ماندلاک |
| `B1_no_season_means` | B1 بدون سه میانگین دامی فصل در همهٔ مراحل؛ حفظ فصل جاری |
| `B2_no_season_means` | همین تغییر برای B2؛ حفظ میانگین لگاریتم مخارج |

کشش‌های مشتق مستقیم S&Y برای مدل‌های جدید و B0/B1/B2 قبلی نیز محاسبه و با قرارداد قبلی مقایسه شده‌اند. حذف میانگین فصل به معنی حذف دامی فصل جاری نیست.

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
