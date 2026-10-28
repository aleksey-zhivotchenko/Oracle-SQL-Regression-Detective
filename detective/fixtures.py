"""Synthetic serial completed workloads. Never presented as live Oracle data."""
from copy import deepcopy
from pathlib import Path
from .model import write_json

REGRESSED = 'abc1234567890'
CONTROL = 'abc1234567891'


def make_row(sql_id, avg_us, executions, plan='111111111', child=0):
    return dict(sql_id=sql_id, child_number=child, child_address=f'00A{child}',
                plan_hash_value=plan, first_load_time='2026-10-28/12:00:00',
                last_load_time='2026-10-28/12:00:00', loads=1, invalidations=0,
                executions=executions, end_of_fetch_count=executions, users_executing=0,
                elapsed_time_us=avg_us * executions, cpu_time_us=avg_us * executions // 2,
                buffer_gets=(35000 if avg_us > 500000 else 400) * executions,
                disk_reads=0, sql_text=f'select /* detective {sql_id} */ count(*) from demo_orders where customer_id = :id',
                plan=dict(status='captured', text=f'Plan hash value: {plan}\n| Operation |\n| {"TABLE ACCESS FULL" if plan == "222222222" else "INDEX RANGE SCAN"} |'))


def bundles():
    target = dict(database_id='123456', instance_name='fixture', instance_startup='2026-10-28 12:00:00',
                  container_id='3', container_name='FIXTURE_PDB', parsing_schema='DEMO', database_version='fixture')
    snapshots = []
    for i, (label, avg, plan) in enumerate([('baseline', 80000, '111111111'), ('comparison', 920000, '222222222'), ('recovery', 84000, '111111111')]):
        for edge, n, minute in [('start', 1, i * 10), ('end', 101, i * 10 + 5)]:
            snapshots.append(dict(schema_version='1.0', source='fixture',
                captured_at_utc=f'2026-10-28T17:{minute:02d}:00Z', target=deepcopy(target),
                selected_sql_ids=[REGRESSED, CONTROL], label=label, edge=edge,
                rows=[make_row(REGRESSED, avg, n, plan), make_row(CONTROL, 60000, n)]))
    return snapshots


def generate(directory):
    for s in bundles():
        write_json(Path(directory) / f'{s["label"]}-{s["edge"]}.json', s)
