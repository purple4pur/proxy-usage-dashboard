"""Run real browser checks. Install the browser group and Chromium first."""
import re
import sys
import threading
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from math import ceil, floor
import tempfile
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard import generate_html, process_csv


class BrowserChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.quota = process_csv(ROOT / 'tests' / 'fixtures' / 'traffic.csv')
        cls.directory      = tempfile.TemporaryDirectory()
        cls.playwright     = sync_playwright().start()
        cls.browser        = cls.playwright.chromium.launch(timeout=30000)
        cls.artifacts      = ROOT / 'tests' / 'artifacts'
        cls.artifacts.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.directory.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000}, color_scheme='light')
        self.context.set_offline(True)
        self.page     = self.context.new_page()
        self.errors   = []
        self.requests = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('request', lambda request: self.requests.append(request.url))

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])
        self.assertFalse(any(url.startswith(('http:', 'https:')) and not url.startswith('http://127.0.0.1:') for url in self.requests), self.requests)

    def load(self,
             data=None,
             quota=None,
             discard=False):
        output = Path(self.directory.name) / 'dashboard.html'
        generate_html(output, self.data if data is None else data, self.quota if quota is None else quota, discard)
        self.page.goto(output.as_uri())
        self.page.locator('#daily-chart').wait_for()

    def test_default_information_and_offline_charts(self):
        self.load()
        self.assertEqual(self.page.locator('#total-used').inner_text(), '1,049.6')
        self.assertEqual(self.page.locator('#usage-percent').inner_text(), '43.7')
        self.assertEqual(self.page.locator('#remaining-gb').inner_text(), '1,350.5')
        self.assertEqual(self.page.locator('#remaining-days').inner_text(), '120')
        self.assertEqual(self.page.locator('#inspect-date option').count(), 14)
        self.assertTrue(self.page.locator('#daily-chart .download').first.is_visible())
        self.assertTrue(self.page.locator('#daily-chart .upload').first.is_visible())
        self.assertEqual(self.page.locator('svg[role="img"]').count(), 4)
        self.assertEqual(self.page.locator('#daily-average').inner_text(), '12.7 GB')

    def test_all_range_buttons_update_every_chart(self):
        self.load()
        for value, count in [('7', 7), ('30', 30), ('all', 45), ('14', 14)]:
            self.page.locator('[data-range="' + value + '"]').click()
            self.assertEqual(self.page.locator('#inspect-date option').count(), count)
            for chart, series, field in [('total-chart', 'line-used', 'totalUsed'), ('percent-chart', 'line-percent', 'usedPercent')]:
                svg    = self.page.locator('#' + chart)
                path   = svg.locator('.' + series).get_attribute('d')
                points = [(float(x), float(y)) for x, y in re.findall(r'[ML]([\d.e+\-]+),([\d.e+\-]+)', path)]
                ticks  = svg.locator('text[text-anchor="end"]').all_text_contents()
                grid   = svg.locator('.grid-line').evaluate_all("nodes => nodes.map(node => Number(node.getAttribute('y1')))")
                self.assertEqual(len(points), count)
                minimum = float(ticks[0].replace(',', ''))
                maximum = float(ticks[-1].replace(',', ''))
                if chart == 'percent-chart':
                    self.assertEqual(minimum, floor(min(row[field] for row in self.data[-count:])))
                    self.assertEqual(maximum, ceil(max(row[field] for row in self.data[-count:])))
                else:
                    self.assertEqual(minimum, 0)
                for (_, plotted_y), row in zip(points, self.data[-count:]):
                    expected_y = grid[0] + (row[field] - minimum) / (maximum - minimum) * (grid[-1] - grid[0])
                    self.assertAlmostEqual(plotted_y, expected_y, places=5)
            previous = self.data[-count - 1] if count < len(self.data) else {'upload': 0, 'download': 0}
            upload   = Decimal(str(self.data[-1]['upload'])) - Decimal(str(previous['upload']))
            download = Decimal(str(self.data[-1]['download'])) - Decimal(str(previous['download']))
            total    = upload + download
            self.assertEqual(self.page.locator('#ratio-total').inner_text(), f'{total:,.1f}')
            self.assertEqual(self.page.locator('#download-ratio').inner_text(), f'{download:,.1f} GB · {(download / total * 100).quantize(Decimal('.1'), rounding=ROUND_HALF_UP)}%')
            self.assertEqual(self.page.locator('#upload-ratio').inner_text(), f'{upload:,.1f} GB · {(upload / total * 100).quantize(Decimal('.1'), rounding=ROUND_HALF_UP)}%')
            self.assertEqual(self.page.locator('.range-btn[aria-pressed="true"]').count(), 1)
            self.assertEqual(self.page.locator('.range-btn[aria-pressed="true"]').get_attribute('data-range'), value)
            self.assertIn('2026-10-29', self.page.locator('#total-summary').inner_text())
            self.assertIn('43.7%', self.page.locator('#percent-summary').inner_text())
        self.page.locator('[data-range="all"]').click()
        self.assertEqual(self.page.locator('#ratio-total').inner_text(), '1,049.6')

    def test_percent_axis_handles_flat_and_extreme_ranges(self):
        row   = self.data[-1]
        cases = [([0], (0, 1)), ([50], (49, 51)), ([50, 50], (49, 51)), ([43.7, 43.7], (43, 44)), ([1e308], None), ([sys.float_info.max], None), ([1e308, sys.float_info.max], None)]
        for values, bounds in cases:
            with self.subTest(values=values):
                rows = [dict(row, date=f'2026-10-{28 + index}', usedPercent=value) for index, value in enumerate(values)]
                self.load(data=rows)
                svg   = self.page.locator('#percent-chart')
                ticks = [float(tick.replace(',', '')) for tick in svg.locator('text[text-anchor="end"]').all_text_contents()]
                if bounds is not None:
                    self.assertEqual((ticks[0], ticks[-1]), bounds)
                    self.assertGreater(ticks[-1], ticks[0])
                grid = svg.locator('.grid-line').evaluate_all("nodes => nodes.map(node => Number(node.getAttribute('y1')))")
                self.assertEqual((grid[0], grid[-1]), (212, 16))
                self.assertNotRegex(svg.inner_html(), r'NaN|Infinity')
                path   = svg.locator('.line-percent').get_attribute('d')
                points = [float(y) for _, y in re.findall(r'[ML]([\d.e+\-]+),([\d.e+\-]+)', path)]
                self.assertEqual(len(points), len(values))
                for plotted_y in points:
                    self.assertGreaterEqual(plotted_y, 16)
                    self.assertLessEqual(plotted_y, 212)
                if len(values) == 1:
                    self.assertTrue(svg.locator('circle').is_visible())
                if values == [50, 50]:
                    self.assertEqual(points, [114, 114])

    def test_keyboard_date_inspection_preserves_chart_nodes(self):
        self.load()
        self.page.evaluate("window.originalBar = document.querySelector('#daily-chart .download')")
        self.page.locator('#inspect-date').focus()
        self.page.locator('#inspect-date').press('Home')
        self.assertEqual(self.page.locator('#inspect-date').input_value(), '2026-10-16')
        self.assertIn('2026-10-16', self.page.locator('#total-summary').inner_text())
        self.assertTrue(self.page.evaluate("window.originalBar === document.querySelector('#daily-chart .download')"))
        self.assertEqual(self.page.locator('#daily-chart .selection').count(), 1)

    def test_pointer_inspection_on_phone(self):
        self.page.set_viewport_size({'width': 320, 'height': 844})
        self.load()
        dates = self.page.locator('#inspect-date option').all_text_contents()
        for day in dates:
            self.page.locator('#inspect-date').select_option(day)
            position = float(self.page.locator('#daily-chart .selection').get_attribute('x1'))
            self.page.locator('#inspect-date').select_option(dates[-1])
            self.page.locator('#daily-chart').scroll_into_view_if_needed()
            point = self.page.evaluate("""position => {
                const svg    = document.getElementById('daily-chart');
                const point  = new DOMPoint(position, 124).matrixTransform(svg.getScreenCTM());
                return {x: point.x, y: point.y};
            }""", position)
            self.page.mouse.move(point['x'], point['y'])
            self.assertEqual(self.page.locator('#inspect-date').input_value(), day)
        font_size = self.page.evaluate("""() => {
            const svg = document.getElementById('daily-chart');
            return parseFloat(getComputedStyle(svg.querySelector('text')).fontSize) * svg.getScreenCTM().a;
        }""")
        self.assertGreaterEqual(font_size, 14)

    def test_daily_plot_has_correct_stacked_series(self):
        previous = {'date': '2026-10-28', 'upload': 10, 'download': 100, 'totalUsed': 110, 'usedPercent': 11}
        latest   = {'date': '2026-10-29', 'upload': 15, 'download': 125, 'totalUsed': 140, 'usedPercent': 14}
        self.load(data=[previous, latest], quota=1000, discard=True)
        for fraction, series in [(.5, 'download'), (.11, 'upload')]:
            actual = self.page.evaluate("""fraction => {
                const svg    = document.getElementById('daily-chart');
                const marker = svg.querySelector('.selection');
                const point  = new DOMPoint(Number(marker.getAttribute('x1')) - 3, svg.viewBox.baseVal.height * fraction).matrixTransform(svg.getScreenCTM());
                return document.elementFromPoint(point.x, point.y).getAttribute('class');
            }""", fraction)
            self.assertEqual(actual, series)
        self.assertEqual(self.page.locator('#inspect-values').inner_text(), '下载 25.0 GB · 上传 5.0 GB · 合计 30.0 GB')

    def test_theme_and_storage_failure(self):
        self.load()
        self.page.locator('#theme-toggle').click()
        self.assertEqual(self.page.locator('html').get_attribute('data-theme'), 'dark')
        self.assertEqual(self.page.locator('#theme-toggle').get_attribute('aria-label'), '切换浅色模式')
        self.assertEqual(self.page.evaluate("localStorage.getItem('theme')"), 'dark')
        self.page.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new Error('storage blocked')}})")
        self.page.reload()
        self.page.locator('#theme-toggle').click()
        self.assertEqual(self.page.locator('html').get_attribute('data-theme'), 'dark')
        self.assertEqual(self.page.locator('#inspect-date option').count(), 14)

    def test_dark_system_theme_with_blocked_storage(self):
        self.page.emulate_media(color_scheme='dark')
        self.page.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new Error('storage blocked')}})")
        self.load()
        self.assertEqual(self.page.locator('html').get_attribute('data-theme'), 'dark')
        self.page.locator('#theme-toggle').click()
        self.assertEqual(self.page.locator('html').get_attribute('data-theme'), 'light')

    def test_theme_persistence_over_http(self):
        self.load()
        handler = partial(SimpleHTTPRequestHandler, directory=self.directory.name)
        with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                self.context.set_offline(False)
                self.page.goto(f'http://127.0.0.1:{server.server_port}/dashboard.html')
                self.page.locator('#theme-toggle').click()
                self.page.reload()
                self.assertEqual(self.page.locator('html').get_attribute('data-theme'), 'dark')
            finally:
                server.shutdown()
                worker.join()

    def test_responsive_layout_and_touch_targets(self):
        self.load()
        for width in [320, 390, 700, 768, 960, 1440, 1920]:
            self.page.set_viewport_size({'width': width, 'height': 1000})
            self.page.wait_for_function("document.querySelector('#daily-chart').getAttribute('viewBox').split(' ')[2] == document.querySelector('#daily-chart').clientWidth")
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'), f'overflow at {width}px')
            for button in self.page.locator('button:visible').all():
                bounds = button.bounding_box()
                self.assertGreaterEqual(bounds['height'], 44)
                self.assertGreaterEqual(bounds['width'], 44)
        self.page.set_viewport_size({'width': 1440, 'height': 1000})
        self.page.screenshot(path=str(self.artifacts / 'desktop.png'), full_page=True)
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.screenshot(path=str(self.artifacts / 'mobile.png'), full_page=True)
        self.page.locator('#theme-toggle').click()
        self.page.screenshot(path=str(self.artifacts / 'mobile-dark.png'), full_page=True)

    def test_theme_contrast_and_chart_separators(self):
        def luminance(color):
            channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear   = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
            return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))

        self.load()
        for theme in ['light', 'dark']:
            if theme == 'dark':
                self.page.locator('#theme-toggle').click()
            colors = self.page.evaluate("""() => {
                const styles = getComputedStyle(document.documentElement);
                return Object.fromEntries(['text', 'muted', 'panel', 'surface', 'accent', 'accent-soft', 'upload', 'download', 'ink-text', 'meter-track'].map(name => [name, styles.getPropertyValue('--' + name).trim()]));
            }""")
            pairs = [('text', 'panel', 4.5), ('muted', 'surface', 4.5), ('accent', 'accent-soft', 4.5), ('upload', 'panel', 3), ('download', 'panel', 3), ('upload', 'surface', 3), ('download', 'surface', 3), ('ink-text', 'meter-track', 3)]
            for foreground, background, minimum in pairs:
                values   = sorted([luminance(colors[foreground]), luminance(colors[background])])
                contrast = (values[1] + .05) / (values[0] + .05)
                with self.subTest(theme=theme, foreground=foreground, background=background):
                    self.assertGreaterEqual(contrast, minimum)
            stroke = self.page.locator('#daily-chart .download').first.evaluate("node => ({color: getComputedStyle(node).stroke, width: parseFloat(getComputedStyle(node).strokeWidth)})")
            self.assertNotEqual(stroke['color'], 'none')
            self.assertGreaterEqual(stroke['width'], 1)
            download = float(self.page.locator('#ratio-download').get_attribute('stroke-dasharray').split()[0])
            upload   = float(self.page.locator('#ratio-upload').get_attribute('stroke-dasharray').split()[0])
            self.assertLess(download + upload, 100)

    def test_table_pagination_search_and_keyboard(self):
        self.load()
        self.page.locator('#records summary').focus()
        outline = self.page.locator('#records summary').evaluate("node => ({style: getComputedStyle(node).outlineStyle, offset: parseFloat(getComputedStyle(node).outlineOffset)})")
        self.assertEqual(outline['style'], 'solid')
        self.assertLess(outline['offset'], 0)
        self.page.locator('#records summary').screenshot(path=str(self.artifacts / 'records-focus.png'))
        self.page.locator('#records summary').press('Enter')
        self.assertTrue(self.page.locator('#records').evaluate('node => node.open'))
        self.assertEqual(self.page.locator('#data-table-body tr').count(), 20)
        self.assertEqual(self.page.locator('#data-table-body tr').first.locator('td').all_text_contents(), ['2026-10-29', '49.5', '1,000.1', '1,049.6', '43.7%'])
        self.page.locator('#next-page').click()
        self.assertIn('21–40', self.page.locator('#page-description').inner_text())
        row = self.data[-21]
        self.assertEqual(self.page.locator('#data-table-body tr').first.locator('td').all_text_contents(), [row['date'], f"{row['upload']:,.1f}", f"{row['download']:,.1f}", f"{row['totalUsed']:,.1f}", f"{row['usedPercent']:,.1f}%"])
        self.page.locator('#next-page').click()
        self.assertEqual(self.page.locator('#data-table-body tr').count(), 5)
        self.assertTrue(self.page.locator('#next-page').is_disabled())
        self.page.locator('#date-search').fill('2026-09')
        self.assertEqual(self.page.locator('#record-count').inner_text(), '16 条记录')
        self.assertEqual(self.page.locator('#data-table-body tr').count(), 16)
        self.assertTrue(self.page.locator('#previous-page').is_disabled())
        self.page.locator('#date-search').fill('no match')
        self.assertIn('没有匹配的记录', self.page.locator('#data-table-body').inner_text())

    def test_discard_baseline_and_single_record(self):
        self.load(discard=True)
        self.page.locator('[data-range="all"]').click()
        self.assertEqual(self.page.locator('#daily-average').inner_text(), '13.5 GB')
        self.assertEqual(self.page.locator('#inspect-date option').count(), 45)
        self.assertEqual(self.page.locator('#ratio-total').inner_text(), '1,049.6')
        self.page.locator('#inspect-date').select_option('2026-09-15')
        self.assertIn('首条记录已', self.page.locator('#inspect-values').inner_text())
        self.load(data=self.data[:1], discard=True)
        self.assertIn('所选范围暂无记录', self.page.locator('#daily-chart').text_content())
        self.assertEqual(self.page.locator('#remaining-days').inner_text(), '未知')
        self.assertEqual(self.page.locator('#daily-average').inner_text(), '0.0 GB')
        self.load(data=self.data[:1])
        self.assertTrue(self.page.locator('#daily-chart .download').first.is_visible())
        self.assertEqual(self.page.locator('#daily-average').inner_text(), '453.6 GB')

    def test_forecast_rounding_preserves_whole_and_fractional_days(self):
        previous = {'date': '2026-10-28', 'upload': 1, 'download': 100, 'totalUsed': 101, 'usedPercent': 10.1}
        latest   = {'date': '2026-10-29', 'upload': 1, 'download': 101, 'totalUsed': 102, 'usedPercent': 10.2}
        self.load(data=[previous, latest], quota=1000)
        self.assertEqual(self.page.locator('#remaining-days').inner_text(), '898')
        self.load(data=[previous, dict(latest, download=102, totalUsed=103, usedPercent=10.3)], quota=1000)
        self.assertEqual(self.page.locator('#remaining-days').inner_text(), '449')

    def test_extreme_finite_values_have_safe_chart_output(self):
        row = {'date': '2026-10-29', 'upload': 1e308, 'download': 1e308, 'totalUsed': 1e308, 'usedPercent': 50}
        self.load(data=[row], quota=1e308)
        self.assertEqual(self.page.locator('#ratio-total').inner_text(), '超出范围')
        self.assertIn('50.0%', self.page.locator('#download-ratio').inner_text())
        self.assertIn('50.0%', self.page.locator('#upload-ratio').inner_text())
        self.assertIn('数值超出可显示范围', self.page.locator('#daily-chart').text_content())
        rows = [dict(row, date=f'2026-10-{day}', upload=4e307 if day % 2 else 1, download=4e307 if day % 2 else 1) for day in range(25, 30)]
        self.load(data=rows, quota=1e308)
        self.assertEqual(self.page.locator('#ratio-total').inner_text(), '超出范围')
        self.assertIn('50.0%', self.page.locator('#download-ratio').inner_text())
        self.assertNotRegex(self.page.locator('body').inner_text(), r'∞|NaN|Infinity')
        for svg in self.page.locator('svg').all():
            self.assertNotRegex(svg.inner_html(), r'NaN|Infinity')

    def test_long_history_keeps_dom_bounded_and_dates_inspectable(self):
        rows = [{'date': (date(2000, 1, 1) + timedelta(days=index)).isoformat(), 'upload': index + 1, 'download': (index + 1) * 5, 'totalUsed': (index + 1) * 6, 'usedPercent': (index + 1) / 1000 * 80} for index in range(1000)]
        self.load(data=rows, quota=10000)
        self.page.locator('[data-range="all"]').click()
        self.assertEqual(self.page.locator('#inspect-date option').count(), 1000)
        self.assertLess(self.page.locator('svg *').count(), 100)
        self.page.locator('#inspect-date').select_option(rows[0]['date'])
        self.assertEqual(self.page.locator('#inspect-values').inner_text(), '下载 5.0 GB · 上传 1.0 GB · 合计 6.0 GB')
        self.page.locator('#inspect-date').select_option(rows[-1]['date'])
        self.assertIn('累计已用 6,000.0 GB', self.page.locator('#total-summary').inner_text())
        self.assertEqual(self.page.locator('#ratio-total').inner_text(), '6,000.0')

    def test_empty_and_zero_data(self):
        self.load(data=[])
        self.assertTrue(self.page.locator('#empty-state').is_visible())
        self.assertTrue(self.page.locator('#inspect-date').is_disabled())
        zero = {'date': '2026-10-29', 'upload': 0, 'download': 0, 'totalUsed': 0, 'usedPercent': 0}
        self.load(data=[zero], quota=0)
        self.assertEqual(self.page.locator('#ratio-total').inner_text(), '0.0')
        self.assertEqual(self.page.locator('#remaining-gb').inner_text(), '0.0')
        self.assertNotIn('NaN', self.page.locator('body').inner_text())
        self.assertNotIn('Infinity', self.page.locator('body').inner_text())

    def test_duplicate_dates_sort_and_sparse_intervals(self):
        rows = [self.data[0], self.data[40], self.data[-1], dict(self.data[-1], upload=50.5, totalUsed=1050.6)]
        self.load(data=[rows[1], rows[0], rows[2], rows[3]])
        self.page.locator('[data-range="7"]').click()
        self.assertEqual(self.page.locator('#inspect-date option').count(), 2)
        self.assertEqual(self.page.locator('#total-used').inner_text(), '1,050.6')
        self.assertEqual(self.page.locator('#latest-interval').inner_text(), '过去 4 天的记录增量')
        self.assertEqual(self.page.locator('#daily-average').inner_text(), '13.6 GB')
        self.assertEqual(self.page.locator('#remaining-days').inner_text(), '100')
        self.page.locator('#records summary').click()
        self.assertEqual(self.page.locator('#data-table-body tr').count(), 4)

    def test_counter_reset_uses_current_counter(self):
        previous = {'date': '2026-10-28', 'upload': 10, 'download': 100, 'totalUsed': 110, 'usedPercent': 11}
        latest   = {'date': '2026-10-29', 'upload': 1, 'download': 2, 'totalUsed': 3, 'usedPercent': .3}
        self.load(data=[previous, latest], quota=1000)
        self.assertEqual(self.page.locator('#latest-increment').inner_text(), '3.0')
        self.assertEqual(self.page.locator('#remaining-days').inner_text(), '未知')


if __name__ == '__main__':
    unittest.main(verbosity=2)
