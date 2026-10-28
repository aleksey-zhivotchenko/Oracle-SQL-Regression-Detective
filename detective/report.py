"""Dependency-free local report. All variable content is HTML-escaped."""
from html import escape
from pathlib import Path
from .model import write_json


def esc(value):
    return escape(str(value), quote=True)


def number(value):
    if value is None:
        return 'Unavailable'
    if value == int(value):
        return f'{value:,.0f}'
    if abs(value) < 0.000001:
        return f'{value:.3g}'
    return f'{value:,.6f}'.rstrip('0').rstrip('.')


def render(report):
    summary = report['summary']
    fixture = report['source'] == 'fixture'
    limits = report['thresholds']
    threshold_text = (f'At least {limits["min_executions"]} executions in each window; '
                      f'{number(limits["min_slowdown_ratio"])}× slower and '
                      f'{number(limits["min_avg_increase_s"] * 1000)} ms average increase. '
                      f'Showing up to {limits["top_n"]} priority investigations.')
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
             '<title>Oracle SQL Regression Detective</title><style>',
             'body{font:16px system-ui,sans-serif;color:#172c3c;background:#f3f6f8;margin:0}main{max-width:1100px;margin:auto;padding:32px}h1{font-size:30px}h2{margin-top:32px}article{background:white;padding:24px;margin:20px 0;border:1px solid #d5dfe5;border-radius:12px}table{width:100%;border-collapse:collapse;margin:16px 0}th,td{text-align:left;padding:10px;border-bottom:1px solid #d5dfe5;vertical-align:top}th{background:#eaf0f4}.banner{padding:16px;background:#fff0c2;border-left:5px solid #997200}.stats{font-size:20px;color:#125b68}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf2f5;padding:16px}code{overflow-wrap:anywhere}.plans{display:grid;grid-template-columns:1fr 1fr;gap:16px}.warning{color:#8a3f0c}small{color:#486070}@media(max-width:700px){main{padding:16px}.plans{grid-template-columns:1fr}table{display:block;overflow:auto}}</style><main>',
             '<h1>Oracle SQL Regression Detective</h1>',
             '<p class="banner">' + ('SYNTHETIC FIXTURE — analysis demonstration only. Live Oracle integration and performance improvement are unvalidated.' if fixture else 'Oracle capture — observations guide investigation; they do not establish root cause.') + '</p>',
             '<p>' + esc(' | '.join(report['target'][k] for k in ('instance_name', 'container_name', 'parsing_schema'))) + '</p>',
             '<p class="stats">' + esc(f'{summary["selected"]} selected · {summary["regressed"]} regressed · {summary["not_regressed"]} not regressed · {summary["insufficient_data"]} insufficient data') + '</p>',
             '<p>Baseline: ' + esc(report['windows']['baseline']['start_utc']) + ' → ' + esc(report['windows']['baseline']['end_utc']) + '<br>Comparison (' + esc(report['windows']['comparison']['label']) + '): ' + esc(report['windows']['comparison']['start_utc']) + ' → ' + esc(report['windows']['comparison']['end_utc']) + '</p>',
             '<p><small>' + esc(threshold_text) + ' Averages use execution-weighted interval deltas. Estimated extra elapsed work is not application downtime.</small></p>']
    for warning in report['warnings']:
        parts.append('<p class="warning">' + esc(warning) + '</p>')
    parts.append('<h2>Priority investigations</h2>')
    top = [r for r in report['results'] if r['rank'] and r['rank'] <= report['thresholds']['top_n']]
    if not top:
        parts.append('<p>No eligible regressions met both thresholds. Review all statuses below for data gaps.</p>')
    for r in top:
        parts.append(f'<article><h3>#{r["rank"]} · <code>{esc(r["sql_id"])}</code></h3><p>{number(r["slowdown_ratio"])}× elapsed ratio · {number(r["estimated_extra_elapsed_s"])} s estimated extra elapsed work · Plan change: {esc(r["plan_change"])}</p>')
        parts.append('<table><thead><tr><th>Metric</th><th>Baseline</th><th>Comparison</th></tr></thead><tbody>')
        for key, label in [('executions','Executions'),('avg_elapsed_s','Elapsed seconds/execution'),('avg_cpu_s','CPU seconds/execution'),('buffer_gets_per_exec','Buffer gets/execution'),('disk_reads_per_exec','Disk reads/execution')]:
            parts.append(f'<tr><td>{label}</td><td>{number(r["baseline"][key])}</td><td>{number(r["comparison"][key])}</td></tr>')
        parts.append('</tbody></table><pre>' + esc(r['sql_text']) + '</pre><h4>Evidence and next checks</h4><ul>')
        for line in r['evidence'] + r['next_checks'] + r['warnings']:
            parts.append('<li>' + esc(line) + '</li>')
        parts.append('</ul><div class="plans">')
        for window in ('baseline', report['windows']['comparison']['label']):
            parts.append('<section><h4>' + esc(window.title()) + ' plans</h4>')
            for p in r['plans']:
                if p['window'] == window:
                    parts.append('<p>Child ' + esc(p['child_number']) + ' · hash ' + esc(p['plan_hash']) + '</p><pre>' + esc(p['text'] or 'Plan unavailable') + '</pre>')
            parts.append('</section>')
        parts.append('</div></article>')
    parts.append('<h2>All selected SQL</h2><table><thead><tr><th>SQL ID</th><th>Status</th><th>Plan change</th><th>Warnings / next check</th></tr></thead><tbody>')
    for r in report['results']:
        parts.append('<tr>' + ''.join('<td>' + esc(v) + '</td>' for v in (r['sql_id'], r['status'], r['plan_change'], ' '.join(r['warnings'] + (r['next_checks'] if r['status'] == 'insufficient_data' else [])))) + '</tr>')
    parts.append('</tbody></table><small>Generated ' + esc(report['generated_at_utc']) + ' · Full metrics and all results are in report.json.</small></main></html>')
    return '\n'.join(parts)


def save(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / 'report.json', report)
    (directory / 'report.html').write_text(render(report), encoding='utf-8')
