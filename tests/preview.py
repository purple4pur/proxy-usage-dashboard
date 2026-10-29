"""Generate a dashboard from the synthetic fixture for local inspection."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard import generate_html, process_csv

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=ROOT / 'tests' / 'artifacts' / 'dashboard.html')
parser.add_argument('--discard-day1', action='store_true')
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
data, quota = process_csv(ROOT / 'tests' / 'fixtures' / 'traffic.csv')
generate_html(args.output, data, quota, args.discard_day1)
print(args.output.resolve().as_uri())
