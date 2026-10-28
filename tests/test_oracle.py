import os
import unittest
from unittest.mock import patch, MagicMock
from copy import deepcopy
from detective import oracle
from detective.fixtures import bundles, REGRESSED, CONTROL
from detective.model import InputError


class OracleTests(unittest.TestCase):
    def test_selection_blocks_sql_injection(self):
        with self.assertRaises(InputError):
            oracle.selection('DEMO', ["a' OR 1=1 --"])
        self.assertEqual(oracle.selection('DEMO', [REGRESSED, REGRESSED])[1], [REGRESSED])

    def test_capture_uses_binds_and_select_only(self):
        s = bundles()[0]
        identity = {k: v for k, v in s['target'].items() if k != 'parsing_schema'}
        calls = []

        def fetch(conn, sql, binds=None):
            calls.append((sql, binds))
            if 'v$database' in sql:
                return [identity]
            if 'FROM v$sql' in sql:
                return deepcopy(s['rows'])
            return [{'plan_table_output': 'Plan hash value: 111111111\n| INDEX RANGE SCAN |'}]

        with patch.object(oracle, 'fetch_dicts', side_effect=fetch):
            result = oracle.capture(object(), 'DEMO', [REGRESSED, CONTROL], 'baseline', 'start')
        self.assertEqual(result['source'], 'oracle')
        for sql, binds in calls:
            self.assertTrue(sql.strip().upper().startswith('SELECT'))
            self.assertNotIn(REGRESSED, sql)
        self.assertEqual(calls[1][1]['schema_name'], 'DEMO')
        self.assertEqual(result['rows'][0]['plan']['status'], 'captured')
        self.assertNotIn('password', str(result).lower())

    def test_plan_error_as_rows(self):
        with patch.object(oracle, 'fetch_dicts', return_value=[{'plan_table_output': 'NOTE: cannot fetch plan for SQL_ID'}]):
            self.assertEqual(oracle.capture_plan(object(), REGRESSED, 0), dict(status='unavailable', text=None))

    def test_plan_exception_suppressed(self):
        with patch.object(oracle, 'fetch_dicts', side_effect=RuntimeError('password=do-not-leak')):
            result = oracle.capture_plan(object(), REGRESSED, 0)
            self.assertNotIn('do-not-leak', str(result))
            self.assertEqual(result['status'], 'unavailable')

    def test_preflight_requires_real_plan_and_selected_sql(self):
        s = bundles()[0]
        with patch.object(oracle, 'capture', return_value=s):
            self.assertEqual(oracle.preflight(object(), 'DEMO', [REGRESSED])['status'], 'passed')
            with self.assertRaises(oracle.OracleError):
                oracle.preflight(object(), 'DEMO', ['0000000000000'])
        for row in s['rows']:
            row['plan'] = dict(status='unavailable', text=None)
        with patch.object(oracle, 'capture', return_value=s):
            with self.assertRaises(oracle.OracleError):
                oracle.preflight(object(), 'DEMO', [REGRESSED])

    def test_connection_missing_and_placeholder(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(oracle.OracleError, 'ORACLE_DSN'):
                oracle.connect(True)
        with patch.dict(os.environ, {'ORACLE_DSN': 'test', 'ORACLE_USER': 'DEMO'}, clear=True):
            with self.assertRaisesRegex(oracle.OracleError, 'missing'):
                oracle.connect(True)
        with patch.dict(os.environ, {'ORACLE_DSN': 'test', 'ORACLE_USER': 'DEMO', 'ORACLE_PASSWORD': '<CURRENT_PASSWORD>'}, clear=True):
            with self.assertRaisesRegex(oracle.OracleError, 'placeholder'):
                oracle.connect(True)

    def test_exception_does_not_leak_connection(self):
        error = oracle.safe_error(RuntimeError('ORA-01031 secret_password tcps://private-host'), 'Capture')
        self.assertIn('ORA-01031', str(error))
        self.assertNotIn('secret_password', str(error))
        self.assertNotIn('private-host', str(error))

    def test_connection_error_is_sanitized(self):
        driver = MagicMock()
        driver.connect.side_effect = RuntimeError('DPY-6005 PASSWORD-SECRET test-service')
        with patch.dict('sys.modules', {'oracledb': driver}), patch.dict(os.environ, {
            'ORACLE_DSN': 'test-service', 'ORACLE_USER': 'DEMO', 'ORACLE_PASSWORD': 'PASSWORD-SECRET'}, clear=True):
            with self.assertRaises(oracle.OracleError) as caught:
                oracle.connect(True)
            self.assertNotIn('PASSWORD-SECRET', str(caught.exception))
            self.assertNotIn('test-service', str(caught.exception))
