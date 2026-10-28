# Verification results

Date: 2026-10-28. Scope: SPEC.md. Task breakdown: TASKS.md.

## Implementation status

| Task | Result |
|---|---|
| T1 Capture contract | Implemented; validation tests pass |
| T2 Interval analyzer | Implemented; arithmetic, weighting, thresholds, data-quality, plan, and ranking tests pass |
| T3 Oracle collector | Implemented; mock-backed collection/error tests pass; driver import verified; live authentication and diagnostic access unvalidated |
| T4 Reports | Implemented; JSON/HTML tests pass; desktop/mobile reports rendered and inspected |
| T5 CLI | Implemented; subprocess tests pass; fixture regression and recovery commands succeed |
| T6 Demo/runbook | Manual Oracle demo scripts and runbook delivered; fixture demonstration passed; live demo and manual diagnosis comparison remain pending |

## Commands actually run

```powershell
.\run.ps1 -m unittest discover -s tests -v
.\run.ps1 -m detective fixtures --output artifacts/captures
.\run.ps1 -m detective analyze --captures artifacts/captures --output artifacts/regression
.\run.ps1 -m detective analyze --captures artifacts/captures --comparison-label recovery --output artifacts/recovery
.\run.ps1 -m unittest tests.test_report -v
```

- Full suite: **38 tests passed**, 3.093 seconds in the recorded full run.
- After formatting thresholds and integer metrics for readability: the 3 report tests passed again, 0.089 seconds; both fixture reports were regenerated successfully.
- Python: 3.12.14. `oracledb`: 3.4.2 installed in the project virtual environment; import successful; thin mode confirmed. Package download initially failed under sandbox network restrictions and succeeded with approved network access.
- Driver-independent analysis and all application tests require only the Python standard library.

## Measured synthetic demonstration

These numbers are derived from labeled synthetic counters, not Oracle executions.

| Check | Result |
|---|---|
| Selected SQL | 2 |
| Regressed target average | 0.080 → 0.920 seconds/execution |
| Slowdown | 11.5x |
| Estimated extra elapsed work | 84 seconds across 100 comparison executions |
| Target plan hash | Changed from `111111111` to `222222222` |
| Target rank | 1 |
| Unchanged control | 0.060 → 0.060 seconds; not flagged |
| Recovery target | 0.084 seconds, 1.05x baseline; not flagged |
| Latest regression report generation | 0.0136 seconds inside the CLI |
| Latest recovery report generation | 0.0100 seconds inside the CLI |

The timing measures reading captures, analysis, and writing both reports; it excludes Python startup and Oracle collection. It does not measure DBA diagnosis time.

## Report inspection

Ran the optional visual smoke check using installed Edge headlessly and the desktop's Playwright package:

```powershell
node scripts/check-report.cjs 'C:/Users/Aleksey.Zhivotchenko/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
```

Passed: one regression card, fixture labeling, recovery with no regression cards, no page errors, and no page-wide horizontal overflow at 390 px. The all-SQL/metrics tables can scroll within their containers on small screens. Desktop and mobile screenshots were inspected; desktop plans appear side by side and mobile plans stack vertically.

Artifacts:

- `artifacts/captures/`: six example capture snapshots.
- `artifacts/regression/report.json` and `report.html`.
- `artifacts/recovery/report.json` and `report.html`.
- `artifacts/regression/desktop.png` and `mobile.png`.

Artifacts and the virtual environment are ignored by Git to keep future live SQL text and captures out of source control. They exist locally and can be regenerated.

## Live dependency result

Loaded the supplied non-secret FreeSQL connection settings and invoked preflight with `--non-interactive`. It stopped before opening a network connection because `ORACLE_PASSWORD` was absent. The user-supplied `<CURRENT_PASSWORD>` is a placeholder, not an available credential. The example SQL ID used for this credential gate was synthetic and must be replaced by a warmed-up live SQL ID.

Therefore the following are **unvalidated**, not passed:

- Service connectivity, authentication, actual Oracle version, and TCPS certificate compatibility.
- Read access to the required V$ views and execution/plan access through DBMS_XPLAN.
- Creation and execution of the disposable Oracle demo workload.
- Actual induced plan regression, restoration, and recovery within 25% of baseline.
- Reduction in manual DBA diagnosis time.

Next live step: follow README.md using a password entered at the hidden local prompt and actual warmed-up SQL IDs. A database administrator may need to arrange diagnostic access on this managed service. No Oracle data, objects, indexes, or grants were changed by this implementation session.

## Known practical limits

- Collection is based on documented 19c views; compatibility with the supplied newer FreeSQL service needs a live check.
- Quiescent, serial, fully fetched SELECT batches are required for this MVP. V$ reads are not an atomic snapshot of a busy workload.
- Missing/evicted cursors, plan changes inside a window, and counter discontinuities are reported conservatively as insufficient data.
- Diagnostic read access is a real dependency. Mock tests cannot establish it.
- The demo index toggle may not cross the default latency thresholds on every database. Report measured behavior honestly and record any explicit threshold change.
