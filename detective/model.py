"""Versioned capture validation. Invalid input never becomes a performance claim."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

COUNTERS = ('executions', 'end_of_fetch_count', 'elapsed_time_us', 'cpu_time_us',
            'buffer_gets', 'disk_reads', 'loads', 'invalidations', 'users_executing')
TARGET_KEYS = ('database_id', 'instance_name', 'instance_startup', 'container_id',
               'container_name', 'parsing_schema')
SQL_ID = re.compile(r'^[0-9a-z]{13}$')


class InputError(ValueError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.utcoffset() is None:
            raise ValueError()
        return dt
    except (ValueError, TypeError, AttributeError):
        raise InputError('Snapshot timestamps must be timezone-aware ISO 8601 strings.') from None


def validate_snapshot(s):
    if not isinstance(s, dict) or s.get('schema_version') != '1.0':
        raise InputError('Unsupported capture schema; expected 1.0.')
    if s.get('source') not in ('oracle', 'fixture'):
        raise InputError('Capture source must be oracle or fixture.')
    timestamp(s.get('captured_at_utc'))
    if s.get('label') not in ('baseline', 'comparison', 'recovery') or s.get('edge') not in ('start', 'end'):
        raise InputError('Invalid capture label or edge.')
    target = s.get('target')
    if not isinstance(target, dict) or any(not isinstance(target.get(k), str) or not target[k] for k in TARGET_KEYS):
        raise InputError('Capture target identity is incomplete.')
    ids = s.get('selected_sql_ids')
    if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not SQL_ID.fullmatch(x) for x in ids):
        raise InputError('Provide an explicit nonempty list of 13-character SQL IDs.')
    if len(set(ids)) != len(ids):
        raise InputError('Duplicate selected SQL IDs.')
    if not isinstance(s.get('rows'), list):
        raise InputError('Capture rows must be a list.')
    seen = set()
    for row in s['rows']:
        if not isinstance(row, dict) or row.get('sql_id') not in ids:
            raise InputError('Cursor is outside the selected SQL IDs.')
        child = row.get('child_number')
        if type(child) is not int or child < 0:
            raise InputError('Invalid child number.')
        key = (row['sql_id'], child)
        if key in seen:
            raise InputError('Duplicate child cursor in capture.')
        seen.add(key)
        for k in ('child_address', 'first_load_time', 'last_load_time'):
            if not isinstance(row.get(k), str) or not row[k]:
                raise InputError('Missing cursor incarnation metadata.')
        for k in COUNTERS:
            if type(row.get(k)) is not int or row[k] < 0:
                raise InputError('Cursor counters must be nonnegative integers: ' + k)
        if row['end_of_fetch_count'] > row['executions']:
            raise InputError('Fetch count exceeds execution count.')
        if 'plan_hash_value' not in row:
            raise InputError('Missing plan_hash_value; use null when unavailable.')
        ph = row.get('plan_hash_value')
        if ph is not None and (not isinstance(ph, str) or not ph.isdigit()):
            raise InputError('Plan hashes must be decimal strings or null.')
        if not isinstance(row.get('sql_text'), str):
            raise InputError('SQL text must be a string.')
        plan = row.get('plan')
        if not isinstance(plan, dict) or plan.get('status') not in ('captured', 'unavailable'):
            raise InputError('Missing plan capture status.')
        if plan['status'] == 'captured' and (not isinstance(plan.get('text'), str) or not plan['text']):
            raise InputError('Captured plan must contain text.')
        if plan['status'] == 'unavailable' and plan.get('text') is not None:
            raise InputError('Unavailable plan text must be null.')
    return s


def validate_windows(snapshots):
    if len(snapshots) != 4:
        raise InputError('Analysis requires four snapshots.')
    for s in snapshots:
        validate_snapshot(s)
    first = snapshots[0]
    for s in snapshots[1:]:
        if any(s['target'][k] != first['target'][k] for k in TARGET_KEYS):
            raise InputError('Incompatible database/instance startup/container/schema identities.')
        if s['source'] != first['source'] or set(s['selected_sql_ids']) != set(first['selected_sql_ids']):
            raise InputError('Capture sources and selected SQL IDs must match.')
    a, b, c, d = snapshots
    if a['label'] != 'baseline' or b['label'] != 'baseline' or c['label'] != d['label'] or c['label'] not in ('comparison', 'recovery'):
        raise InputError('Expected baseline and comparison/recovery window labels.')
    if [s['edge'] for s in snapshots] != ['start', 'end', 'start', 'end']:
        raise InputError('Each window needs a start followed by an end snapshot.')
    times = [timestamp(s['captured_at_utc']) for s in snapshots]
    if not (times[0] < times[1] <= times[2] < times[3]):
        raise InputError('Windows must be positive, ordered, and non-overlapping.')


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise InputError('Cannot read a valid JSON capture file: ' + str(path)) from None


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
