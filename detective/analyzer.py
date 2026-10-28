"""Interval deltas with conservative data-quality handling."""
import math
from .model import InputError, utc_now, validate_windows

DEFAULTS = dict(min_executions=10, min_slowdown_ratio=2.0, min_avg_increase_s=0.05, top_n=5)
DELTAS = ('executions', 'end_of_fetch_count', 'elapsed_time_us', 'cpu_time_us', 'buffer_gets', 'disk_reads')
INCARNATION = ('child_address', 'first_load_time', 'last_load_time', 'loads', 'invalidations', 'plan_hash_value')


def interval(start, end, sql_id):
    before = {r['child_number']: r for r in start['rows'] if r['sql_id'] == sql_id}
    after = {r['child_number']: r for r in end['rows'] if r['sql_id'] == sql_id}
    warnings, plans = [], []
    if not before or not after:
        return None, [], ['SQL is absent from a window boundary.']
    if before.keys() != after.keys():
        return None, [], ['Child cursor cohort changed within the window.']
    sums = dict.fromkeys(DELTAS, 0)
    hashes, unknown = set(), False
    for child, a in before.items():
        b = after[child]
        if any(a[k] != b[k] for k in INCARNATION):
            return None, [], ['Cursor reloaded, invalidated, or changed plan within the window.']
        if a['users_executing'] or b['users_executing']:
            return None, [], ['SQL was executing at a snapshot boundary.']
        delta = {k: b[k] - a[k] for k in DELTAS}
        if any(v < 0 for v in delta.values()):
            return None, [], ['Cumulative counter decreased; interval is unreliable.']
        if delta['end_of_fetch_count'] != delta['executions']:
            return None, [], ['Executions were not fully fetched within the window.']
        if not delta['executions']:
            if any(delta[k] for k in DELTAS if k != 'executions'):
                return None, [], ['Counter activity without completed executions.']
            continue
        for k, v in delta.items():
            sums[k] += v
        ph = b['plan_hash_value']
        if ph in (None, '0'):
            unknown = True
        else:
            hashes.add(ph)
        plan = b['plan'] if b['plan']['status'] == 'captured' else a['plan']
        plans.append(dict(window=start['label'], child_number=child, plan_hash=ph,
                          status=plan['status'], text=plan.get('text')))
        if plan['status'] == 'unavailable':
            warnings.append('Plan text unavailable for child ' + str(child) + '.')
    n = sums['executions']
    if not n:
        return None, plans, ['No completed executions in this window.']
    metrics = dict(executions=n, avg_elapsed_s=sums['elapsed_time_us'] / n / 1e6,
                   avg_cpu_s=sums['cpu_time_us'] / n / 1e6,
                   buffer_gets_per_exec=sums['buffer_gets'] / n,
                   disk_reads_per_exec=sums['disk_reads'] / n,
                   plan_hashes=sorted(hashes), plan_hashes_complete=not unknown)
    return metrics, plans, warnings


def analyze(snapshots, **overrides):
    validate_windows(snapshots)
    thresholds = DEFAULTS | overrides
    if set(thresholds) != set(DEFAULTS):
        raise InputError('Unknown threshold option.')
    for k, v in thresholds.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise InputError('Thresholds must be positive finite numbers.')
    if type(thresholds['min_executions']) is not int or type(thresholds['top_n']) is not int or thresholds['top_n'] > 5:
        raise InputError('Execution count and top-N must be integers; top-N is at most 5.')
    a, b, c, d = snapshots
    results = []
    for sql_id in sorted(a['selected_sql_ids']):
        base, bp, bw = interval(a, b, sql_id)
        recent, cp, cw = interval(c, d, sql_id)
        texts = [r['sql_text'] for s in reversed(snapshots) for r in s['rows'] if r['sql_id'] == sql_id]
        row = dict(rank=None, sql_id=sql_id, status='insufficient_data', sql_text=texts[0] if texts else '',
                   baseline=base, comparison=recent, slowdown_ratio=None, estimated_extra_elapsed_s=None,
                   plan_change='unknown', plans=bp + cp, evidence=[], next_checks=[],
                   warnings=['Baseline: ' + w for w in bw] + ['Comparison: ' + w for w in cw])
        if base and recent:
            if base['plan_hashes_complete'] and recent['plan_hashes_complete']:
                row['plan_change'] = 'not_observed' if base['plan_hashes'] == recent['plan_hashes'] else 'observed'
            if min(base['executions'], recent['executions']) < thresholds['min_executions']:
                row['warnings'].append('Too few executions for the configured minimum.')
            elif base['avg_elapsed_s'] <= 0:
                row['warnings'].append('Baseline average must be positive.')
            else:
                increase = recent['avg_elapsed_s'] - base['avg_elapsed_s']
                ratio = recent['avg_elapsed_s'] / base['avg_elapsed_s']
                ratio_pass = ratio >= thresholds['min_slowdown_ratio'] or math.isclose(ratio, thresholds['min_slowdown_ratio'], rel_tol=1e-12)
                increase_pass = increase >= thresholds['min_avg_increase_s'] or math.isclose(increase, thresholds['min_avg_increase_s'], rel_tol=1e-12)
                row.update(slowdown_ratio=ratio, estimated_extra_elapsed_s=max(0, increase) * recent['executions'],
                           status='regressed' if ratio_pass and increase_pass else 'not_regressed')
                row['evidence'] = [f'Average elapsed ratio: {ratio:.3g}x.',
                                   f'Executions: {base["executions"]} baseline, {recent["executions"]} comparison.',
                                   'Plan change: ' + row['plan_change'] + '.']
                if row['status'] == 'regressed':
                    row['next_checks'] = ['Verify comparable bind values, row counts, and workload conditions.']
                    if row['plan_change'] == 'observed':
                        row['next_checks'].append('Compare captured access paths and joins; inspect relevant index availability and optimizer statistics. A changed plan does not prove causation.')
                    else:
                        row['next_checks'].append('Inspect CPU and logical reads per execution; investigate contention or changed inputs. Matching plan hashes do not prove identical runtime behavior.')
        if row['status'] == 'insufficient_data':
            row['next_checks'] = ['Warm up, wait for complete fetching, and recapture both boundaries with stable cursors.']
        results.append(row)
    ranked = sorted((r for r in results if r['status'] == 'regressed'), key=lambda r: (-r['estimated_extra_elapsed_s'], r['sql_id']))
    for i, r in enumerate(ranked, 1):
        r['rank'] = i
    results.sort(key=lambda r: (r['rank'] is None, r['rank'] or 0, r['sql_id']))
    return dict(schema_version='1.0', source=a['source'], generated_at_utc=utc_now(), target=a['target'],
                windows=dict(baseline=dict(start_utc=a['captured_at_utc'], end_utc=b['captured_at_utc']),
                             comparison=dict(label=c['label'], start_utc=c['captured_at_utc'], end_utc=d['captured_at_utc'])),
                thresholds=thresholds, summary=dict(selected=len(results), **{status: sum(r['status'] == status for r in results) for status in ('regressed', 'not_regressed', 'insufficient_data')}),
                results=results, warnings=['Fixture data: Oracle integration is not validated.'] if a['source'] == 'fixture' else
                ['Assumes serial, fully fetched SELECT workloads with comparable inputs; elapsed work is not application response time.'])
