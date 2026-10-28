"""Read-only Oracle collection; database exception text is never echoed."""
import getpass
import os
import re
from .model import InputError, SQL_ID, utc_now, validate_snapshot


class OracleError(RuntimeError):
    pass


def safe_error(exc, context):
    # Driver errors can contain connect descriptors or SQL; expose only error codes.
    match = re.search(r'\b(?:ORA|DPY|DPI)-\d+\b', str(exc))
    code = match.group(0) if match else 'driver error'
    return OracleError(f'{context} failed ({code}). Check connectivity, credentials, and diagnostic read grants; raw driver details are suppressed.')


def connect(non_interactive=False):
    dsn, user = os.getenv('ORACLE_DSN'), os.getenv('ORACLE_USER')
    password = os.getenv('ORACLE_PASSWORD')
    if not dsn or not user:
        raise OracleError('Set ORACLE_DSN and ORACLE_USER; the password is prompted locally.')
    if password and ('<CURRENT_PASSWORD>' in password):
        raise OracleError('ORACLE_PASSWORD is a placeholder; supply the actual password locally.')
    if not password:
        if non_interactive:
            raise OracleError('ORACLE_PASSWORD is missing; rerun interactively for a hidden password prompt.')
        password = getpass.getpass('Oracle password (not saved): ')
    if not password:
        raise OracleError('An Oracle password is required.')
    try:
        import oracledb
    except ImportError:
        raise OracleError('Install the Oracle driver: python -m pip install -r requirements.txt') from None
    try:
        # Thin mode by default; TLS certificate verification remains enabled.
        connection = oracledb.connect(user=user, password=password, dsn=dsn, tcp_connect_timeout=15)
        connection.call_timeout = 30000
        return connection
    except Exception as exc:
        raise safe_error(exc, 'Oracle connection') from None


def selection(schema, ids):
    if not schema or not schema.strip():
        raise InputError('A parsing schema is required.')
    ids = sorted(set(ids))
    if not ids or len(ids) > 20 or any(not SQL_ID.fullmatch(x) for x in ids):
        raise InputError('Select 1–20 valid 13-character SQL IDs.')
    return schema, ids


def fetch_dicts(connection, sql, binds=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, binds or {})
        keys = [d[0].lower() for d in cursor.description]
        return [dict(zip(keys, row)) for row in cursor.fetchall()]


def capture_plan(connection, sql_id, child):
    try:
        rows = fetch_dicts(connection,
            "SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(:sql_id, :child, 'TYPICAL'))",
            dict(sql_id=sql_id, child=child))
        text = '\n'.join(str(r['plan_table_output']) for r in rows)
        # DISPLAY_CURSOR may return an explanatory error as rows, not raise an exception.
        if not re.search(r'Plan hash value:\s*\d+', text, re.I) or re.search(r'cannot fetch|ORA-\d+|Error:', text, re.I):
            return dict(status='unavailable', text=None)
        return dict(status='captured', text=text)
    except Exception:
        return dict(status='unavailable', text=None)


def capture(connection, schema, ids, label, edge):
    schema, ids = selection(schema, ids)
    captured_at = utc_now()
    try:
        identity = fetch_dicts(connection, """
            SELECT TO_CHAR(d.dbid) database_id, i.instance_name,
                   TO_CHAR(i.startup_time, 'YYYY-MM-DD HH24:MI:SS') instance_startup,
                   SYS_CONTEXT('USERENV', 'CON_ID') container_id,
                   SYS_CONTEXT('USERENV', 'CON_NAME') container_name,
                   i.version database_version
            FROM v$database d CROSS JOIN v$instance i
        """)[0]
        identity = {k: str(v) for k, v in identity.items()}
        identity['parsing_schema'] = schema
        binds = {'schema_name': schema} | {f'id{i}': value for i, value in enumerate(ids)}
        placeholders = ','.join(':' + f'id{i}' for i in range(len(ids)))
        rows = fetch_dicts(connection, """
            SELECT sql_id, child_number, RAWTOHEX(child_address) child_address,
                   TO_CHAR(plan_hash_value) plan_hash_value,
                   first_load_time, last_load_time, loads, invalidations,
                   executions, end_of_fetch_count, users_executing,
                   elapsed_time elapsed_time_us, cpu_time cpu_time_us,
                   buffer_gets, disk_reads, sql_fulltext sql_text
            FROM v$sql WHERE parsing_schema_name = :schema_name
            AND sql_id IN (""" + placeholders + ') ORDER BY sql_id, child_number', binds)
        if len(rows) > 200:
            raise OracleError('More than 200 selected child cursors; narrow the SQL selection.')
        for row in rows:
            if hasattr(row['sql_text'], 'read'):
                row['sql_text'] = row['sql_text'].read()
            row['plan'] = capture_plan(connection, row['sql_id'], row['child_number'])
            if row['plan']['status'] == 'captured':
                observed = re.search(r'Plan hash value:\s*(\d+)', row['plan']['text'], re.I).group(1)
                if observed != row['plan_hash_value']:
                    row['plan'] = dict(status='unavailable', text=None)
        snapshot = dict(schema_version='1.0', source='oracle', captured_at_utc=captured_at,
                        target=identity, selected_sql_ids=ids, label=label, edge=edge, rows=rows)
        return validate_snapshot(snapshot)
    except (InputError, OracleError):
        raise
    except Exception as exc:
        raise safe_error(exc, 'Diagnostic collection') from None


def preflight(connection, schema, ids):
    snapshot = capture(connection, schema, ids, 'baseline', 'start')
    missing = set(ids) - {r['sql_id'] for r in snapshot['rows']}
    if missing:
        raise OracleError('Selected SQL is absent from this schema/cache; warm up and verify SQL IDs: ' + ', '.join(sorted(missing)))
    if not any(r['plan']['status'] == 'captured' for r in snapshot['rows']):
        raise OracleError('No cursor plan retrieved. Verify DBMS_XPLAN execution and SELECT/READ on V_$SQL, V_$SQL_PLAN, V_$SESSION, V_$SQL_PLAN_STATISTICS_ALL.')
    return dict(status='passed', target=snapshot['target'], selected_sql_count=len(ids),
                captured_plans=sum(r['plan']['status'] == 'captured' for r in snapshot['rows']))
