# آخرین تحلیل فیزیکی پیشنهادی

این مرحله تنها کار علمی مهم باقی‌مانده پیش از نگارش مقاله است.

هدف بررسی مستقیم رابطه زیر در میدان کامل است:

\[
q'(s,\theta,t)\simeq
-a(t)\,\frac{\partial\overline q}{\partial s}.
\]

این رابطه برای density، Mach، translational temperature و pressure آزمون
می‌شود. شکل زاویه‌ای displacement از مود فیزیکی Kn=0.01 گرفته می‌شود.

## چه چیزهایی اجرا می‌شود؟

- common200 برای Kn=0.01، 0.025 و 0.05؛
- همان half-jump registration و physical wall clipping؛
- matched-filter displacement amplitude برای هر moment؛
- مقایسه مستقیم amplitude میدان با marker displacement؛
- moving-block bootstrap؛
- circular-time-shift null test؛
- shifted-template spatial null؛
- cross-variable consensus؛
- کانتورهای رنگی actual / reconstructed / residual.

## چه چیزهایی اجرا نمی‌شود؟

- POD، DMD یا SPOD جدید؛
- power/exclusion جدید؛
- DSMC جدید؛
- Mach sweep.

## نصب

پوشه کامل `JFM2_DISPLACEMENT_TEMPLATE_VALIDATION` را داخل ریشه
`JFM2_ALL_KN_UNIFIED_ANALYSIS` کپی کنید.

ساختار:

```text
JFM2_ALL_KN_UNIFIED_ANALYSIS
├── config
├── scripts
└── JFM2_DISPLACEMENT_TEMPLATE_VALIDATION
    ├── RUN_DISPLACEMENT_TEMPLATE_VALIDATION.ps1
    ├── ZIP_RESULTS.ps1
    └── scripts
```

## اجرا

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\JFM2_DISPLACEMENT_TEMPLATE_VALIDATION\RUN_DISPLACEMENT_TEMPLATE_VALIDATION.ps1 `
  -Bootstrap 500
```

این مرحله raw DS2FF را برای سه case می‌خواند و ممکن است چند ساعت طول بکشد.
هر case یک cache فشرده می‌سازد؛ بنابراین اجرای مجدد سریع‌تر است.

## زیپ نتایج

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\JFM2_DISPLACEMENT_TEMPLATE_VALIDATION\ZIP_RESULTS.ps1
```

## معیار موفقیت

برای Kn=0.01 و 0.025 انتظار داریم:

- correlation مثبت و bootstrap-stable میان marker و full-field amplitudes؛
- سازگاری density، Mach، Ttr و pressure؛
- positive spatial template correlation؛
- true template بهتر از xi-shifted null templates؛
- multi-moment PC1 هم‌بسته با marker؛
- density reconstruction دارای ساختار جابه‌جایی و residual بدون front سراسری.

Kn=0.05 به‌عنوان diagnostic/negative-sensitivity case اجرا می‌شود.
