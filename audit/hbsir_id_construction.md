# ساخت ID در HBSIR

نسخه بررسی‌شده HBSIR 0.6.6، commit `e5b3e5d5146ccf76af3e3068c0fc12fa7b4b678f`؛ BSSIR 0.6.8.

- فایل `src/hbsir/metadata/tables.yaml`: نگاشت `global_address` نام جدید `ID` و نوع `UInt64` را تعیین می‌کند. ستون `ADDRESS` در `household_information` و `members_properties` به همین نگاشت ارجاع می‌دهد. انتخاب خانوار از الگوی `*Data*` است.
- تبدیل در BSSIR، فایل `bssir/data_cleaner.py`، توابع `_apply_metadata_to_table`، `_apply_metadata_to_column` و `_apply_type_to_column` انجام می‌شود. نام جدید از `new_name` گرفته می‌شود؛ سپس `_general_cleaning` و `astype('UInt64', errors='raise')` اجرا می‌شوند.
- `_general_cleaning` فاصله و برخی نشانه‌های اضافی را پاک می‌کند، `.0` انتهایی را حذف و مقدار خالی را null می‌کند. بنابراین عبارت «کاملاً بدون تغییر» در سطح نوع/رشته دقیق نیست؛ در سطح عدد برای هر هشت سال برابری کامل مشاهده شد. صفر ابتدایی در تبدیل عددی قابل حفظ نیست، اما در Address غیرخالی این هشت سال هیچ صفر ابتدایی مشاهده نشد؛ نسخه خام متنی جدا حفظ شده است.
- فایل `src/hbsir/metadata/schema.yaml` برای خانوار `add_year` و `dropna: ID` دارد؛ قطع یا بازشماره‌گذاری ID ندارد. ۱۳۹۰ یک ردیف خام با Address خالی دارد و طبق همین قاعده در استاندارد نیست: ۴۰٬۰۱۱ در خام، ۴۰٬۰۱۰ در خروجی. هیچ ID غیرخالی گم نشده است.
- قواعد ساخت ID در هشت سال تغییر ندارند؛ تغییر طول کد از داده خام می‌آید. `id_information.yaml` از۱۳۸۷ طول۱۰ و از۱۳۹۲ طول۱۱ و موقعیت استان/شهری‌روستایی را ثبت می‌کند؛ شهرستان پیش از۱۳۹۲ از جدول خارجی و پس از آن از موقعیت۱ تا۵ استخراج می‌شود. این فایل معرف دائمی بودن خانوار نیست.
- `src/hbsir/schema_functions/standard_tables.py::adjust_month` ماه۱ را۱۳ کرده و سپس۱ کم می‌کند؛ قاعده سالنامه آمارگیری اردیبهشت تا فروردین را برای نمایش ماه اعمال می‌کند. ممیزی حاضر ماه خام را نگه می‌دارد.

شواهد عددی: `raw_panel_id_integrity.csv` و `address_structure_by_year.csv`. پنج متغیر خام اعضا (Address، ردیف، رابطه، جنس، سن) در هشت سال به‌صورت چندمجموعهٔ کامل با نسخه استاندارد برابرند؛ مقایسه در `validate_panel_links.py::raw_members` اجرا شده است.

منبع کد HBSIR: https://github.com/Iran-Open-Data/HBSIR/tree/e5b3e5d5146ccf76af3e3068c0fc12fa7b4b678f/src/hbsir/metadata
