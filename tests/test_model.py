import unittest
from copy import deepcopy
from detective.fixtures import bundles
from detective.model import InputError, validate_snapshot, validate_windows


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.s = bundles()[:4]

    def test_valid(self):
        validate_windows(self.s)

    def test_invalid_counters(self):
        for value in (-1, float('nan'), float('inf'), '100', True, None):
            with self.subTest(value=value):
                s = deepcopy(self.s[0])
                s['rows'][0]['executions'] = value
                with self.assertRaises(InputError):
                    validate_snapshot(s)

    def test_duplicate_cursor(self):
        self.s[0]['rows'].append(deepcopy(self.s[0]['rows'][0]))
        with self.assertRaises(InputError):
            validate_windows(self.s)

    def test_missing_plan_hash_field(self):
        del self.s[0]['rows'][0]['plan_hash_value']
        with self.assertRaises(InputError):
            validate_windows(self.s)

    def test_incompatible_target(self):
        for field in ('database_id', 'instance_startup', 'container_id', 'parsing_schema'):
            with self.subTest(field=field):
                s = deepcopy(self.s)
                s[3]['target'][field] = 'different'
                with self.assertRaises(InputError):
                    validate_windows(s)

    def test_bad_order_and_timezone(self):
        for value in ('2026-10-28T16:00:00Z', 'not-a-date', '2026-10-28T18:00:00'):
            s = deepcopy(self.s)
            s[3]['captured_at_utc'] = value
            with self.assertRaises(InputError):
                validate_windows(s)

    def test_mixed_source(self):
        self.s[3]['source'] = 'oracle'
        with self.assertRaises(InputError):
            validate_windows(self.s)

    def test_missing_sql_is_per_query_issue(self):
        self.s[0]['rows'] = []
        validate_windows(self.s)

    def test_different_ids_and_edges(self):
        s = deepcopy(self.s)
        s[3]['selected_sql_ids'].append('0000000000000')
        with self.assertRaises(InputError):
            validate_windows(s)
        self.s[0]['edge'] = 'end'
        with self.assertRaises(InputError):
            validate_windows(self.s)
