# راهنمای فایل‌های داده در Google Drive

محدودیت بارگذاری Drive در این اتصال ۱۰۰ MiB برای هر فایل است. بنابراین فایل‌های اصلی بزرگ به قطعات مستقل تقسیم شده‌اند؛ فایل‌های کامل با نام اصلی در محیط محلی پروژه موجودند.

## قطعات بارگذاری‌شده

- `food_item_long_all_1392_1403_part01.parquet` — 4,500,000 ردیف
- `food_item_long_all_1392_1403_part02.parquet` — 4,500,000 ردیف
- `food_item_long_all_1392_1403_part03.parquet` — 4,394,042 ردیف
- `itemwide_all_1392_1403_part01.csv.gz` — 150,000 ردیف داده به‌علاوهٔ سرستون
- `itemwide_all_1392_1403_part02.csv.gz` — 150,000 ردیف داده به‌علاوهٔ سرستون
- `itemwide_all_1392_1403_part03.csv.gz` — 138,577 ردیف داده به‌علاوهٔ سرستون

هر قطعه کمتر از ۱۰۰ MiB است. همهٔ قطعات CSV به‌طور مستقل gzip و دارای سرستون‌اند.

## فایل‌های کامل و بدون تقسیم

`household_year_all_1392_1403.parquet`, `household_year_panelB_1392_1403.parquet`, `itemwide_all_1392_1403.parquet`, `itemwide_panelB_1392_1403.parquet`, و `itemwide_panelB_1392_1403.csv.gz` با نام کامل در Drive قرار دارند.

## بازسازی در Python

```python
import pyarrow.dataset as ds

food_files = [
    "food_item_long_all_1392_1403_part01.parquet",
    "food_item_long_all_1392_1403_part02.parquet",
    "food_item_long_all_1392_1403_part03.parquet",
]
food = ds.dataset(food_files, format="parquet").to_table()
```

برای CSV، فایل‌ها را جداگانه با `pandas.read_csv` بخوانید و ردیف‌ها را با `pandas.concat` به‌ترتیب part01، part02، part03 به هم بچسبانید. سرستون‌های تکراری در هر فایل، سرستون مستقل همان قطعه‌اند و جزو ردیف داده نیستند.

`analysis_drive_upload_manifest.csv` اندازه، تعداد ردیف، SHA-256، نام و پیوند Drive هر فایل را ثبت می‌کند.
