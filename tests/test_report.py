import tempfile
import unittest
import json
from pathlib import Path
from detective.analyzer import analyze
from detective.fixtures import bundles
from detective.report import render, save


class ReportTests(unittest.TestCase):
    def test_escaping_and_fixture_label(self):
        s = bundles()[:4]
        for snap in s:
            snap['rows'][0]['sql_text'] = '<script>alert("secret")</script>'
            snap['rows'][0]['plan']['text'] = '<img src=x onerror=alert(1)>'
        html = render(analyze(s))
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('SYNTHETIC FIXTURE', html)
        self.assertIn('Baseline plans', html)
        self.assertIn('Comparison plans', html)

    def test_json_and_all_statuses(self):
        r = analyze(bundles()[:4])
        with tempfile.TemporaryDirectory() as temp:
            save(r, temp)
            saved = json.loads((Path(temp) / 'report.json').read_text())
            html = (Path(temp) / 'report.html').read_text(encoding='utf-8')
            self.assertEqual(saved, r)
            self.assertIn('35,000', html)
            self.assertIn('50 ms average increase', html)
            for row in r['results']:
                self.assertIn(row['sql_id'], html)
                self.assertIn(row['status'], html)

    def test_no_regressions(self):
        s = bundles()
        self.assertIn('No eligible regressions', render(analyze(s[:2] + s[4:])))
