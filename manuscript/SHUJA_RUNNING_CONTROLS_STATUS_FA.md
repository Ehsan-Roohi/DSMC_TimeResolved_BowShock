# راهنمای شجاع در زمان اجرای کنترل‌ها

چهار ران باید بدون تغییر پس از شروع تکمیل شوند:

| case | seed | particle level | start mode |
|---|---:|---:|---|
| N1-A | 104729 | baseline | true new run, IRUN=3 |
| N1-B | 130363 | baseline | true new run, IRUN=3 |
| N2-A | 104729 | 2x particles | true new run, IRUN=3 |
| N2-B | 130363 | 2x particles | true new run, IRUN=3 |

برای continuation همان case، فقط restart همان case با `IRUN=1` و فایل `RNG_STATE.DAT` خودش استفاده شود. restart یک seed هرگز برای seed دیگر کپی نشود.

هندسه، Kn=0.01، Mach=10، مدل مولکولی، mesh/adaptation، timestep، تعداد sample در هر output، cadence و burn-in باید در چهار case یکسان بمانند. تنها تفاوت‌های مجاز seed و particle loading هستند.

در پایان هر case این اقلام ارسال شوند:

- تمام snapshotهای DS2FF؛
- `MODAL_OUTPUT_LOG.csv`؛
- `DS2VD.DAT` و inputهای کامل؛
- seed ورودی و `RNG_STATE.DAT`؛
- فایل‌های restart نهایی؛
- stdout/stderr و اطلاعات compiler/executable؛
- تعداد واقعی particles، FNUM، timestep، output cadence و تعداد snapshot.

حداقل 400 snapshot قابل تحلیل است؛ هدف 600 snapshot برای هر case است. هیچ نتیجه‌ای با عبارت «قبول شد» وارد مقاله نمی‌شود تا چهار case با pipeline ثابت تحلیل و جدول `CONTROL_RESULTS_INPUT_TEMPLATE.csv` پر شود.
