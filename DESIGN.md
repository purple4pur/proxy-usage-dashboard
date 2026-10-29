# Dashboard design contract

The dashboard turns CSV snapshots into a standalone, responsive HTML report.
The page keeps Chinese labels and uses UTC+8 dates and GB units.

## Public interfaces

Keep these interfaces compatible:

- `python dashboard.py <csv_file> <output_file> [--discard-day1]`
- `process_csv(csv_file)` returns `(traffic_data, total_gb)`.
- `generate_html(output_file, traffic_data, total_gb, discard_day1)` writes an HTML file.
- Entries use `date`, `upload`, `download`, `totalUsed`, and `usedPercent`.

`process_csv` preserves input order. It uses the first row's total quota.
An empty CSV with all required headers returns `([], None)`.
Dates must use `YYYY-MM-DD`. Numeric inputs must be finite and nonnegative.
Values above the quota remain valid.
Derived values above the numeric range show `超出范围`.
Ratios remain available through normalized arithmetic.

## Information and interaction

Retain total quota, used traffic, recorded percentage, and estimated remaining days.
Retain cumulative usage, percentage history, daily upload/download, and traffic distribution.
Retain every raw record and all five existing table columns.
Add remaining quota, latest increment, date inspection, search, and pagination.

One range control updates all four charts. The default range is 14 calendar days.
The 7, 14, and 30 day ranges end at the latest CSV date.
The percentage Y-axis uses the selected minimum rounded down and maximum rounded up to whole percentages.
Flat whole-number percentages receive padding to keep the chart range positive.
The summary cards always use the latest snapshot.
The table contains all raw records, independent of the chart range.
Show 20 table records per page, newest first. Search matches date text.

Use the last input row for each date in charts. Keep duplicate rows in the table.
Sort chart snapshots by date. Compute increments between adjacent snapshots.
When a counter decreases, use its current value as the increment after a reset.
A sparse interval represents all traffic between its two records.
Calculate the daily average from interval lengths.

The default first daily sample contains its accumulated upload and download.
This preserves the previous dashboard's actual behavior.
`--discard-day1` removes that daily sample, including its contribution to daily averages.
Cumulative charts, summary cards, and raw records retain the first snapshot.
The distribution for the full range always uses the latest accumulated counters.
Shorter ranges use the selected increments.

Estimate remaining days from the percentage change over the latest seven record intervals.
Divide that change by the elapsed calendar days.
Show `未知` when there is insufficient history or no positive growth.
This estimate describes quota consumption, not subscription expiry.

## Visual direction

Use an ivory background, ink text, a dark quota card, terracotta download data,
and teal upload data. Provide separate dark theme tokens.
Use a compact sidebar on wide screens. Stack panels on narrow screens.
Keep the traffic distribution compact on phones.
Use local font stacks and native SVG charts. The generated page needs no network requests.

Controls need visible labels, keyboard access, focus rings, and 44px touch targets.
Provide a date selector as the keyboard alternative to chart pointer inspection.
Use live text summaries and semantic tables for chart values.
The table can scroll horizontally within its own region on small screens.
Store the theme preference when local storage is available.
Storage failure must preserve the dashboard's functionality.

## Verification

Run the generator suite with `uv run python -m unittest discover -s tests -v`.
Run browser checks with `uv run --group browser python tests/browser_check.py`.
The browser suite checks offline use, themes, keyboard controls, responsive layouts,
range selection, pagination, empty data, sparse dates, duplicate dates, and resets.
