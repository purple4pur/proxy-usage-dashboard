import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'traffic.csv'
sys.path.insert(0, str(ROOT))

from dashboard import generate_html, process_csv


class DashboardTests(unittest.TestCase):
    def test_csv_contract(self):
        data, quota = process_csv(FIXTURE)
        self.assertEqual(len(data), 45)
        self.assertEqual(quota, 2400.1)
        self.assertEqual(data[0], {'date': '2026-09-15', 'upload': 17.5, 'download': 436.1, 'totalUsed': 453.6, 'usedPercent': 18.9})
        self.assertEqual(set(data[-1]), {'date', 'upload', 'download', 'totalUsed', 'usedPercent'})
        self.assertGreater(data[-1]['totalUsed'], data[0]['totalUsed'])

    def test_fixture_has_quiet_days(self):
        data, _ = process_csv(FIXTURE)
        self.assertEqual(data[11]['totalUsed'], data[10]['totalUsed'])

    def test_input_order_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reversed.csv'
            with FIXTURE.open(newline='') as stream:
                rows   = list(csv.DictReader(stream))
                fields = list(rows[0])
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(reversed(rows))
            data, _ = process_csv(path)
            self.assertEqual(data[0]['date'], rows[-1]['UTC8_Date'])

    def test_single_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'single.csv'
            path.write_text('\n'.join(FIXTURE.read_text().splitlines()[:2]) + '\n')
            data, quota = process_csv(path)
            self.assertEqual(len(data), 1)
            self.assertEqual(quota, 2400.1)

    def test_empty_csv_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'empty.csv'
            path.write_text(FIXTURE.read_text().splitlines()[0] + '\n')
            self.assertEqual(process_csv(path), ([], None))

    def test_missing_column_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing.csv'
            path.write_text('UTC8_Date\n2026-10-01\n')
            with self.assertRaises((KeyError, ValueError)):
                process_csv(path)

    def test_bad_number_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.csv'
            path.write_text(FIXTURE.read_text().replace('17.5,436.1', 'invalid,436.1', 1))
            with self.assertRaises(ValueError):
                process_csv(path)

    def test_render_preserves_dashboard_information(self):
        data, quota = process_csv(FIXTURE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dashboard.html'
            generate_html(path, data, quota, False)
            html = path.read_text()
            for label in ['流量使用统计', '已用流量', '使用率', '每日上传下载', '上传下载比例', '详细数据', '2026-09-15', '2400.1']:
                self.assertIn(label, html)
            self.assertNotIn('{% ', html)
            self.assertNotIn('{{ ', html)

    def test_cli_and_discard_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            for flags in [[], ['--discard-day1']]:
                path   = Path(directory) / 'dashboard.html'
                result = subprocess.run([sys.executable, str(ROOT / 'dashboard.py'), str(FIXTURE), str(path), *flags], cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Successfully generated dashboard page:', result.stdout)
                self.assertTrue(path.is_file())
                self.assertIn('const discardDay1 = ' + ('true' if flags else 'false'), path.read_text())


if __name__ == '__main__':
    unittest.main()
