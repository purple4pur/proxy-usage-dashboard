"""Run real browser checks. Install the browser group and Chromium first."""
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
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
        self.assertEqual(self.page.locator('#daily-chart rect').count(), 28)
        self.assertEqual(self.page.locator('svg[role="img"]').count(), 4)
        self.assertEqual(self.page.locator('#daily-average').inner_text(), '12.7 GB')

    def test_all_range_buttons_update_every_chart(self):
        self.load()
        for value, count in [('7', 7), ('30', 30), ('all', 45), ('14', 14)]:
            self.page.locator('[data-range="' + value + '"]').click()
            self.assertEqual(self.page.locator('#inspect-date option').count(), count)
            self.assertEqual(self.page.locator('#daily-chart rect').count(), count * 2)
            self.assertEqual(self.page.locator('.range-btn[aria-pressed="true"]').count(), 1)
            self.assertEqual(self.page.locator('.range-btn[aria-pressed="true"]').get_attribute('data-range'), value)
            self.assertIn('2026-10-29', self.page.locator('#total-summary').inner_text())
            self.assertIn('43.7%', self.page.locator('#percent-summary').inner_text())
        self.page.locator('[data-range="all"]').click()
        self.assertEqual(self.page.locator('#ratio-total').inner_text(), '1,049.6')

    def test_keyboard_date_inspection_preserves_chart_nodes(self):
        self.load()
        self.page.evaluate("window.originalBar = document.querySelector('#daily-chart rect')")
        self.page.locator('#inspect-date').focus()
        self.page.locator('#inspect-date').press('Home')
        self.assertEqual(self.page.locator('#inspect-date').input_value(), '2026-10-16')
        self.assertIn('2026-10-16', self.page.locator('#total-summary').inner_text())
        self.assertTrue(self.page.evaluate("window.originalBar === document.querySelector('#daily-chart rect')"))
        self.assertEqual(self.page.locator('#daily-chart .selection').count(), 1)

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
            self.page.wait_for_function("document.querySelector('#daily-chart').getAttribute('viewBox').split(' ')[2] == Math.max(280, document.querySelector('#daily-chart').clientWidth)")
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

    def test_table_pagination_search_and_keyboard(self):
        self.load()
        self.page.locator('#records summary').focus()
        self.page.locator('#records summary').press('Enter')
        self.assertTrue(self.page.locator('#records').evaluate('node => node.open'))
        self.assertEqual(self.page.locator('#data-table-body tr').count(), 20)
        self.assertEqual(self.page.locator('#data-table-body td').first.inner_text(), '2026-10-29')
        self.page.locator('#next-page').click()
        self.assertIn('21–40', self.page.locator('#page-description').inner_text())
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
        self.assertEqual(self.page.locator('#daily-chart rect').count(), 88)
        self.assertEqual(self.page.locator('#inspect-date option').count(), 45)
        self.assertEqual(self.page.locator('#ratio-total').inner_text(), '1,049.6')
        self.page.locator('#inspect-date').select_option('2026-09-15')
        self.assertIn('首条记录已', self.page.locator('#inspect-values').inner_text())
        self.load(data=self.data[:1], discard=True)
        self.assertIn('所选范围暂无记录', self.page.locator('#daily-chart').text_content())
        self.assertEqual(self.page.locator('#remaining-days').inner_text(), '未知')
        self.assertEqual(self.page.locator('#daily-average').inner_text(), '0.0 GB')
        self.load(data=self.data[:1])
        self.assertEqual(self.page.locator('#daily-chart rect').count(), 2)
        self.assertEqual(self.page.locator('#daily-average').inner_text(), '453.6 GB')

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
