# 流量使用统计

Generate a standalone dashboard from accumulated proxy traffic snapshots.
The page shows quota, used traffic, recorded percentage, estimated remaining days,
four charts, and searchable raw records. It works offline after generation.

## Generate a dashboard

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```bash
uv python install 3.14
uv sync --locked
uv run python dashboard.py tests/fixtures/traffic.csv dashboard.html
```

Open `dashboard.html` in your browser. Use your own CSV path for real traffic.
The runtime pin and package requirement both target Python 3.14.
With an existing Python 3.14 environment, install Jinja2 and use the original command:

```bash
python dashboard.py <csv_file> <output_file>
```

To exclude the initial accumulated baseline from daily traffic, add `--discard-day1`:

```bash
uv run python dashboard.py tests/fixtures/traffic.csv dashboard.html --discard-day1
```

The default first daily sample contains its accumulated counters.
The flag preserves cumulative charts, summary cards, and raw records.
Estimated remaining days describe quota consumption, not subscription expiry.

## Test the project

Run the Python suite:

```bash
uv run python -m unittest discover -s tests -v
```

Generate a preview with synthetic data:

```bash
uv run python tests/preview.py
```

The script writes `tests/artifacts/dashboard.html` and prints its location.
Use `--output <path>` or `--discard-day1` to change the preview.
The fixture covers 45 days and includes quiet days. It contains no real account data.

Install Chromium and run the optional browser suite:

```bash
uv sync --locked --group browser
uv run --group browser python -m playwright install chromium
uv run --group browser python tests/browser_check.py
```

The suite tests offline operation, keyboard controls, theme preferences, table search,
pagination, responsive widths from 320px to 1920px, and data edge cases.
It saves desktop and mobile screenshots under `tests/artifacts/`.
Chromium must be able to start in your environment.
Theme persistence for `file://` pages depends on the browser.
Serve the page over HTTP for reliable persistence.

Measure performance with the same workload on different interpreters:

```bash
uv run python tests/benchmark.py --rows 10000 --runs 5
```

The script reports median CSV parse time, HTML render time, and output size.
It uses temporary files and removes them after the run.
Performance varies with the interpreter build, filesystem, and machine load.

## CSV reference

The generator reads these fields. Additional columns remain compatible.

| Column | Format or unit |
|---|---|
| `UTC8_Date` | `YYYY-MM-DD` |
| `Accumulated_Upload_GB` | Accumulated upload in GB |
| `Accumulated_Download_GB` | Accumulated download in GB |
| `Total_GB` | Total quota in GB; the first row supplies the dashboard quota |
| `Total_Used_GB` | Recorded cumulative usage in GB |
| `Used_Percent` | Recorded usage percentage |

Numeric fields must be finite and nonnegative. Usage above the quota is valid.
An empty CSV with headers produces an empty dashboard.
Charts use the final input snapshot for each date and sort dates chronologically.
The table retains duplicate records. Date controls use calendar days.
For missing dates, bars show interval totals and averages use elapsed days.
A decrease in an upload or download counter starts a new baseline for that counter.

The sample preserves the original export columns:

| Commit_SHA | Commit_Date | UTC8_Date | Line_Content | Accumulated_Upload_GB | Accumulated_Download_GB | Total_GB | Total_Used_GB | Used_Percent |
|---|---|---|---|---|---|---|---|---|
| bca1259a7ce126ba9e89ed24bcc1c0ff1415bccb | 2025-09-12 14:52:43 +0800 | 2025-09-12 | # upload=17.5GB; download=436.1GB; total=2400.1GB(Used:453.6GB//18.9%); expire=2026-08-08T15:09:03+0800 | 17.5 | 436.1 | 2400.1 | 453.6 | 18.9 |

See [DESIGN.md](DESIGN.md) for the interface and calculation contracts.
