import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable, '-m', 'detective', *args], capture_output=True, text=True, env=env, timeout=30)

    def test_full_fixture_regression_and_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            captures = str(Path(temp) / 'captures')
            output = str(Path(temp) / 'reports')
            result = self.run_cli('fixtures', '--output', captures)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SYNTHETIC', result.stdout)
            for label, expected in [('comparison', 1), ('recovery', 0)]:
                result = self.run_cli('analyze', '--captures', captures, '--output', output, '--comparison-label', label)
                self.assertEqual(result.returncode, 0, result.stderr)
                metrics = json.loads(result.stdout)
                self.assertLess(metrics['elapsed_seconds'], 30)
                self.assertEqual(metrics['summary']['regressed'], expected)
                report = json.loads((Path(output) / 'report.json').read_text())
                self.assertEqual(report['source'], 'fixture')
                self.assertTrue((Path(output) / 'report.html').exists())

    def test_bad_json_and_invalid_threshold_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as temp:
            self.run_cli('fixtures', '--output', temp)
            result = self.run_cli('analyze', '--captures', temp, '--output', temp, '--top-n', '0')
            self.assertEqual(result.returncode, 2)
            (Path(temp) / 'baseline-start.json').write_text('{bad')
            result = self.run_cli('analyze', '--captures', temp, '--output', temp)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('Traceback', result.stderr)

    def test_noninteractive_preflight_no_password(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('ORACLE_')}
        env.update(ORACLE_DSN='test-service', ORACLE_USER='DEMO')
        result = self.run_cli('preflight', '--schema', 'DEMO', '--sql-id', 'abc1234567890', '--non-interactive', env=env)
        self.assertEqual(result.returncode, 2)
        self.assertIn('password', result.stderr.lower())
        self.assertNotIn('Traceback', result.stderr)

    def test_capture_does_not_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'baseline-start.json'
            path.write_text('preserve me')
            result = self.run_cli('capture', '--schema', 'DEMO', '--sql-id', 'abc1234567890', '--label', 'baseline', '--edge', 'start', '--output', temp, '--non-interactive')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_text(), 'preserve me')
            self.assertIn('already exists', result.stderr)
