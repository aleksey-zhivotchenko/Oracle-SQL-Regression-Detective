# MVP implementation tasks

Commands below use `python`; on this workstation use `./run.ps1` instead (it resolves the bundled Python runtime). No task requires real credentials for its automated tests.

| Task | Dependencies | Relevant files | Acceptance criteria | Test command |
|---|---|---|---|---|
| T1 Capture contract and validation | SPEC.md | detective/model.py, tests/test_model.py | Reject malformed/non-finite counters, duplicate cursors, incompatible targets, mixed sources, bad time order; preserve missing selected SQL for explicit status | `python -m unittest tests.test_model -v` |
| T2 Interval analysis and ranking | T1 | detective/analyzer.py, tests/test_analyzer.py | Weighted deltas; threshold boundaries; deterministic ranking; resets/cohort changes/partial work are insufficient data; observed/matching/unknown plan sets | `python -m unittest tests.test_analyzer -v` |
| T3 Read-only Oracle collector | T1 | detective/oracle.py, tests/test_oracle.py, connection.example.ps1 | Bind SQL IDs/schema; read identity and cursor counters; save plans; actionable sanitized failures; actual plan retrieval required by preflight | `python -m unittest tests.test_oracle -v` |
| T4 JSON and standalone HTML reports | T2 | detective/report.py, tests/test_report.py | All SQL statuses retained, top-N details, both windows/metrics/plans, visible fixture label, escaped text, warnings | `python -m unittest tests.test_report -v` |
| T5 CLI and reproducible fixture flow | T1–T4 | detective/__main__.py, detective/fixtures.py, run.ps1, tests/test_cli.py | Fixture generation, preflight, capture, analysis/recovery commands; clear exit codes; reports generated end to end without Oracle driver | `python -m unittest tests.test_cli -v` |
| T6 Demo and runbook verification | T1–T5 | README.md, demo/*.sql, RESULTS.md | Full tests pass, fixture regression/recovery measured, generated JSON/HTML inspected; live checks separately recorded as passed or unvalidated | `python -m unittest discover -s tests -v`; `python -m detective fixtures --output artifacts/captures`; `python -m detective analyze --captures artifacts/captures --output artifacts/regression`; `python -m detective analyze --captures artifacts/captures --comparison-label recovery --output artifacts/recovery` |

## Live dependency gate

Provided target: FreeSQL over TCPS, service `26ai_un3c1`, schema/user `ALEKSEY_ZHIVOTCHE_SCHEMA_DS5JT`. The password supplied in chat is a placeholder, not a credential. Oracle version, V$ privileges, plan access, and disposable-workload permission remain unverified. This target is newer than the spec's 19c reference; preflight records the actual version.

Live command after setting connection environment variables: `python -m detective preflight --schema ALEKSEY_ZHIVOTCHE_SCHEMA_DS5JT --sql-id <warmed-up-sql-id>`.

Fixtures validate application behavior only. Live diagnosis, regression/recovery, and manual-time comparison require a successful live run. Implementation status and measured outcomes are recorded in RESULTS.md: T1–T5 are implemented and automatically tested; T6 passed fixture and report checks, while live Oracle acceptance remains unvalidated due to the unavailable password.

Optional T4/T6 browser check: `node scripts/check-report.cjs [path-to-playwright-module]` uses installed Edge headlessly after fixture reports have been generated. Its source is `scripts/check-report.cjs`; product usage does not depend on Node or Playwright.
