"""Measure CSV parsing and HTML generation with the selected interpreter."""
import argparse
import csv
import platform
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard import generate_html, process_csv

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rows', type=int, default=10000)
parser.add_argument('--runs', type=int, default=5)
args = parser.parse_args()
if args.rows < 1 or args.runs < 1:
    parser.error('--rows and --runs must be positive')

with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'traffic.csv'
    output = Path(directory) / 'dashboard.html'
    with (ROOT / 'tests' / 'fixtures' / 'traffic.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows   = list(reader)
    with source.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows[index % len(rows)] for index in range(args.rows))

    parse_times  = []
    render_times = []
    for _ in range(args.runs):
        started     = perf_counter()
        data, quota = process_csv(source)
        parsed      = perf_counter()
        generate_html(output, data, quota, False)
        rendered    = perf_counter()
        parse_times.append(parsed - started)
        render_times.append(rendered - parsed)
    print(f'Python {platform.python_version()}, {args.rows} rows, {args.runs} runs')
    print(f'parse median: {statistics.median(parse_times) * 1000:.2f} ms')
    print(f'render median: {statistics.median(render_times) * 1000:.2f} ms')
    print(f'output: {output.stat().st_size} bytes')
