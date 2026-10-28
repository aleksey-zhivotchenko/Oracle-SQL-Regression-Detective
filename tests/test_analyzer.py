import unittest
from copy import deepcopy
from detective.analyzer import analyze, interval
from detective.fixtures import bundles, make_row, REGRESSED, CONTROL
from detective.model import InputError


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.s = bundles()[:4]

    def result(self, sql_id=REGRESSED, **options):
        return next(r for r in analyze(self.s, **options)['results'] if r['sql_id'] == sql_id)

    def test_regression_arithmetic_and_control(self):
        r = self.result()
        self.assertEqual(r['status'], 'regressed')
        self.assertAlmostEqual(r['slowdown_ratio'], 11.5)
        self.assertAlmostEqual(r['estimated_extra_elapsed_s'], 84)
        self.assertEqual(r['rank'], 1)
        self.assertEqual(r['plan_change'], 'observed')
        self.assertEqual(self.result(CONTROL)['status'], 'not_regressed')

    def test_weighted_child_deltas(self):
        self.s[0]['rows'] = [make_row(REGRESSED, 100000, 1), make_row(REGRESSED, 900000, 1, child=1)]
        self.s[1]['rows'] = [make_row(REGRESSED, 100000, 91), make_row(REGRESSED, 900000, 11, child=1)]
        metrics, _, _ = interval(self.s[0], self.s[1], REGRESSED)
        self.assertAlmostEqual(metrics['avg_elapsed_s'], .18)
        self.assertEqual(metrics['executions'], 100)

    def test_boundaries(self):
        for index in (2, 3):
            n = self.s[index]['rows'][0]['executions']
            self.s[index]['rows'][0]['elapsed_time_us'] = n * 160000
        self.assertEqual(self.result(min_avg_increase_s=.08)['status'], 'regressed')
        self.assertEqual(self.result(min_avg_increase_s=.080001)['status'], 'not_regressed')

    def test_low_counts_zero_baseline_absent(self):
        self.assertEqual(self.result(min_executions=101)['status'], 'insufficient_data')
        self.s[0]['rows'][0]['elapsed_time_us'] = 0
        self.s[1]['rows'][0]['elapsed_time_us'] = 0
        self.assertEqual(self.result()['status'], 'insufficient_data')
        self.s[0]['rows'].pop(0)
        self.assertEqual(self.result()['status'], 'insufficient_data')
        self.assertEqual(self.result(CONTROL)['status'], 'not_regressed')

    def test_reload_and_negative_counter_and_cohort(self):
        for field, value in [('loads', 2), ('invalidations', 1), ('child_address', 'FFFF'),
                             ('last_load_time', 'different'), ('elapsed_time_us', 0), ('plan_hash_value', '777')]:
            with self.subTest(field=field):
                s = deepcopy(self.s)
                s[1]['rows'][0][field] = value
                r = analyze(s)['results']
                self.assertEqual(next(x for x in r if x['sql_id'] == REGRESSED)['status'], 'insufficient_data')
        self.s[1]['rows'].append(make_row(REGRESSED, 80000, 10, child=3))
        self.assertEqual(self.result()['status'], 'insufficient_data')

    def test_incomplete_or_inflight_work(self):
        self.s[1]['rows'][0]['end_of_fetch_count'] -= 1
        self.assertEqual(self.result()['status'], 'insufficient_data')
        self.s = bundles()[:4]
        self.s[0]['rows'][0]['users_executing'] = 1
        self.assertEqual(self.result()['status'], 'insufficient_data')

    def test_plan_unknown_and_matching(self):
        for i in (2, 3):
            self.s[i]['rows'][0]['plan_hash_value'] = None
        self.assertEqual(self.result()['plan_change'], 'unknown')
        for i in (2, 3):
            self.s[i]['rows'][0]['plan_hash_value'] = '111111111'
        self.assertEqual(self.result()['plan_change'], 'not_observed')

    def test_missing_plan_preserves_metrics(self):
        for s in self.s:
            s['rows'][0]['plan'] = dict(status='unavailable', text=None)
        r = self.result()
        self.assertEqual(r['status'], 'regressed')
        self.assertEqual(r['plan_change'], 'observed')
        self.assertTrue(r['warnings'])

    def test_inactive_child_not_in_plan_set(self):
        for s in self.s:
            s['rows'].append(make_row(REGRESSED, 100000, 1, plan='999', child=2))
        self.assertEqual(self.result()['baseline']['plan_hashes'], ['111111111'])

    def test_tie_ranking(self):
        for s in self.s:
            twin = deepcopy(s['rows'][0])
            twin['sql_id'] = CONTROL
            s['rows'][1] = twin
        results = analyze(self.s)['results']
        self.assertEqual([r['sql_id'] for r in results], [REGRESSED, CONTROL])
        self.assertEqual([r['rank'] for r in results], [1, 2])

    def test_recovery(self):
        s = bundles()
        result = analyze(s[:2] + s[4:])
        self.assertEqual(result['summary']['regressed'], 0)
        r = next(r for r in result['results'] if r['sql_id'] == REGRESSED)
        self.assertAlmostEqual(r['slowdown_ratio'], 1.05)

    def test_new_child_between_windows_is_allowed(self):
        for i in (2, 3):
            self.s[i]['rows'][0].update(child_number=4, child_address='FFFF', last_load_time='later')
        self.assertEqual(self.result()['status'], 'regressed')

    def test_no_executions_and_unattributed_work(self):
        self.s[1]['rows'][0] = deepcopy(self.s[0]['rows'][0])
        self.assertEqual(self.result()['status'], 'insufficient_data')
        self.s[1]['rows'][0]['elapsed_time_us'] += 100
        self.assertEqual(self.result()['status'], 'insufficient_data')

    def test_invalid_thresholds(self):
        for options in ({'min_executions': 0}, {'min_slowdown_ratio': float('nan')}, {'top_n': 6}, {'top_n': 1.5}):
            with self.assertRaises(InputError):
                analyze(self.s, **options)
