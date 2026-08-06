# تحلیل نهایی همه ۹ عدد نودسن

این پکیج چهار کیس جدید را جدا از کیس‌های قدیمی تحلیل نمی‌کند. همه موارد زیر با یک pipeline واحد پردازش می‌شوند:

`0.01, 0.025, 0.05, 0.075, 0.10, 0.15, 0.25, 0.50, 1.00`

## قبل از اجرا

فایل `config/all_kn_campaign_config.json` را باز کنید و مسیر `pattern` و `log_pattern` هر case را با مسیر واقعی raw snapshotها تطبیق دهید.

برای چهار کیس جدید مقدار `dt_star` عمداً خالی است. مرحله QC آن را از لاگ v10 می‌خواند. اگر لاگ قدیمی فقط زمان دارد، QC ابتدا از کیس‌های قدیمی دارای dt_star سرعت دقیق freestream را کالیبره می‌کند و سپس dt_star جدید را محاسبه می‌کند. اگر لاگ‌های reference در دسترس نباشند، مقدار دقیق `u_inf_m_s` را از DS2V input در config وارد کنید.

## مرحله ۱: QC

در PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File RUN_QC_FIRST.ps1
```

QC باید برای هر ۹ case حداقل ۲۰۰ snapshot، header یکسان، مسیر صحیح و dt_star معتبر گزارش کند. فایل اصلی:

`ALL_KN_FINAL_ANALYSIS/qc/preflight_qc.csv`

تا وقتی QC پاس نشده، تحلیل کامل را اجرا نکنید.

## مرحله ۲: تحلیل کامل

```powershell
powershell -ExecutionPolicy Bypass -File RUN_ALL_AFTER_QC.ps1
```

این دستور به ترتیب انجام می‌دهد:

1. corrected physical-domain POD روی ۲۰۰ snapshot مشترک هر case؛
2. temporal coarse-graining روی common200؛
3. correlated-noise inference با bootstrap و controls؛
4. تحلیل full-available برای استفاده از snapshotهای اضافی؛
5. power-versus-amplitude و exclusion limit؛
6. master tables و شکل‌های مقایسه‌ای همه Knها.

## خروجی‌های مهم

- `summary/pod/corrected_pod_summary.csv`
- `correlated_common200/correlated_noise_inference_summary.csv`
- `correlated_full/correlated_noise_inference_summary.csv`
- `power_full/exclusion_limits.csv`
- `summary/master_common200/master_results.csv`
- `summary/master_full/master_results.csv`
- `summary/master_full/Fig_master_physical_correlation_matrices.png`
- `summary/master_full/Fig_master_amplitude_and_exclusion_limit.png`

## منطق مقایسه

- POD اصلی: دقیقاً ۲۰۰ snapshot برای همه کیس‌ها.
- تحلیل آماری اصلی: هم common200 و هم full-available گزارش می‌شود.
- snapshotهای اضافی برای ACF، bootstrap، power و exclusion limit استفاده می‌شوند.
- classification بین «resolved»، «transitional»، «not detected with adequate sensitivity» و «unmeasurable» تمایز می‌گذارد.

## نکات محاسباتی

POD variable-wise برای ۹ case سنگین است. در تست اول می‌توان در config فقط `D` را در `variables` نگه داشت و `run_multivariate=false` کرد. برای نسخه نهایی مقاله تنظیمات پیش‌فرض کامل اجرا شوند.

SPOD به‌صورت پیش‌فرض خاموش است، چون نتیجه اصلی مقاله marker/covariance است. پس از تثبیت transition، SPOD فقط برای چند case منتخب اجرا شود.

## زیپ نتایج

```powershell
powershell -ExecutionPolicy Bypass -File ZIP_RESULTS.ps1
```
