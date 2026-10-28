# Oracle SQL Regression Detective

A local CLI that captures selected Oracle SQL cursors, compares two completed workload windows, and writes a ranked JSON/HTML investigation report. The collector only issues SELECT statements. The demo SQL files are separate manual actions on a disposable schema.

Scope: [SPEC.md](SPEC.md). Task dependencies, files, criteria, and targeted tests: [TASKS.md](TASKS.md). Actual verification results: [RESULTS.md](RESULTS.md).

## Quick start: no database required

From the repository directory in PowerShell:

```powershell
.\run.ps1 -m unittest discover -s tests -v
.\run.ps1 -m detective fixtures --output artifacts/captures
.\run.ps1 -m detective analyze --captures artifacts/captures --output artifacts/regression
.\run.ps1 -m detective analyze --captures artifacts/captures --comparison-label recovery --output artifacts/recovery
```

Open `artifacts/regression/report.html` and `artifacts/recovery/report.html`. Every fixture artifact is explicitly synthetic. JSON includes all selected SQL; HTML shows top-N regression details and an all-SQL status table. Reports are self-contained and load no external resources.

`run.ps1` uses the project virtual environment if present, then Python on PATH, then this desktop's bundled runtime. On macOS/Linux or a standard Python environment use `python` in place of `.\run.ps1`. Python 3.10+ is required. Offline analysis uses only the standard library.

## Install the Oracle driver

```powershell
.\run.ps1 -m venv .venv
.\run.ps1 -m pip install -r requirements.txt
```

The current workspace already has `.venv` and the driver installed. Default connection mode is thin and does not use the local 19c Oracle client. TLS verification remains enabled. There is no DSN, user, or password CLI argument; connection values are environment variables and passwords can be entered at a hidden local prompt.

## Live dependency gate

The supplied service uses TCPS at `db.freesql.com:2484`, service `26ai_un3c1`, with user/schema `ALEKSEY_ZHIVOTCHE_SCHEMA_DS5JT`. It has not yet been authenticated by this tool. Load the non-secret settings:

```powershell
. .\connection.example.ps1
```

`ORACLE_PASSWORD`, if set locally, is used; otherwise the CLI prompts without echoing or saving it. Do not put a real password in chat, command arguments, scripts, captures, or Git. `--non-interactive` fails immediately if the variable is absent. The placeholder `<CURRENT_PASSWORD>` is rejected explicitly.

Required diagnostic access is to `V_$DATABASE`, `V_$INSTANCE`, `V_$SQL`, and the views used by `DBMS_XPLAN.DISPLAY_CURSOR`: `V_$SQL_PLAN`, `V_$SESSION`, and `V_$SQL_PLAN_STATISTICS_ALL`, plus execution of that package. An administrator must arrange appropriate read access if the service permits it. Owning application tables does not imply these privileges. No grants are attempted by the program.

Create and warm up the disposable workload (next section), then copy the two real SQL IDs:

```powershell
$targetSql = 'REPLACE_WITH_13_CHAR_SQL_ID'
$controlSql = 'REPLACE_WITH_13_CHAR_SQL_ID'
$schemaName = $env:ORACLE_USER
.\run.ps1 -m detective preflight --schema $schemaName --sql-id $targetSql --sql-id $controlSql
```

Preflight reports actual database version, identity, and captured-plan count. It fails if selected SQL is missing or no plan can be retrieved. A connection error exposes only its error code, not raw driver text. FreeSQL version and privilege compatibility remain a live prerequisite; the collector is based on Oracle 19c documented views.

## Controlled live demo

Use a SQLcl/SQL*Plus session connected interactively to the disposable schema; do not embed passwords in connection commands. The setup creates approximately 500,000 padded rows and two indexes, so verify test-schema space and privileges first. It does not replace or drop existing objects.

1. In the SQL session, run `@demo/setup.sql`, `@demo/workload.sql 1`, then `@demo/find_sql_ids.sql`. Set `$targetSql` and `$controlSql` in PowerShell from that output. The data and plan behavior depend on the database; this workload has not yet been verified on the supplied service.
2. Run the preflight above. Keep the SQL session idle at each capture boundary.
3. Capture the baseline start:

```powershell
.\run.ps1 -m detective capture --schema $schemaName --sql-id $targetSql --sql-id $controlSql --label baseline --edge start --output artifacts/live
```

4. In the SQL session run `@demo/workload.sql 100`, wait for it to finish, then capture the baseline end:

```powershell
.\run.ps1 -m detective capture --schema $schemaName --sql-id $targetSql --sql-id $controlSql --label baseline --edge end --output artifacts/live
```

5. In the SQL session run `@demo/slowdown.sql` and `@demo/workload.sql 1`. Confirm that the target plan changed. Warm-up is outside measured windows; any invalidation during a window makes that interval insufficient data.
6. Capture `comparison/start`, run `@demo/workload.sql 100`, then capture `comparison/end`, using the same capture command with the label and edge changed.
7. Generate the report:

```powershell
.\run.ps1 -m detective analyze --captures artifacts/live --output artifacts/live-regression
```

8. Run `@demo/restore.sql`, then warm up with `@demo/workload.sql 1`. Capture `recovery/start`, run `@demo/workload.sql 100`, and capture `recovery/end`.

```powershell
.\run.ps1 -m detective analyze --captures artifacts/live --comparison-label recovery --output artifacts/live-recovery
```

Run `restore.sql` even if the demo is interrupted after hiding the index. Cleanup/deletion of demo tables is deliberately manual. Existing capture files are not overwritten; use a fresh directory for repeated trials. Report files may be regenerated.

A full scan is not intrinsically a defect. The demo tests a known selective predicate whose measured behavior must establish the slowdown. If it does not pass the default 2x and 50ms thresholds, record that result; do not claim a successful live regression. Thresholds can be changed explicitly for a different workload, but document the changed criteria. Do not flush shared pools or buffer caches for this demo.

## Options and interpretation

```powershell
.\run.ps1 -m detective --help
.\run.ps1 -m detective analyze --help
```

Defaults: `--min-executions 10 --min-slowdown-ratio 2 --min-avg-increase-s 0.05 --top-n 5`. Top-N is 1–5. All selected queries remain in JSON regardless of rank.

- Each JSON snapshot has schema version `1.0`, source `oracle`/`fixture`, UTC time, full target identity, selected IDs, label/edge, and child cursor rows. `detective/model.py` validates the contract. Six examples are generated by the `fixtures` command.
- The report follows the output contract in SPEC.md; it adds `plan_hashes_complete` per window and a comparison label to distinguish recovery. Unknown metrics are null, not zero.
- Metric values are interval counter deltas divided by completed execution counts. Elapsed and CPU counters are converted from microseconds to seconds.
- Rank is estimated extra elapsed work: positive increase in average elapsed seconds multiplied by comparison execution count. It is not saved CPU time or application downtime.
- Child cohorts must be stable within a window; plans and child cohorts may differ between windows. Missing cursors, reloads, decreasing counters, incomplete fetches, and active boundary executions cause `insufficient_data` for the affected SQL.
- Snapshot queries are not atomic across Oracle views. Plan text is checked against the observed hash, but the quiescent controlled workload is still essential. No claim is made about arbitrary concurrent production traffic.
- Use serial fully fetched SELECTs with the same binds. Parallel execution, bind sensitivity, other users executing the same SQL, cache warmth, and row-count changes can distort interpretation.
- A changed plan hash is evidence to investigate, not proof of causation. A matching hash does not guarantee equivalent execution behavior.
- Reports include selected SQL and plan text. The program does not record connection credentials; it cannot scrub arbitrary sensitive literals that are already present in SQL text. Keep live reports local.

Exit status: `0` for a completed command (including reports with insufficient data), `2` for invalid input/preflight/connection/file errors, `130` for cancellation. Consumers must inspect report statuses rather than interpreting exit 0 as a clean database.

## Acceptance and remaining live work

Run the full automated suite with `.\run.ps1 -m unittest discover -s tests -v`. Per-task commands are in TASKS.md.

Live acceptance requires correct culprit and control classification, matching saved plan evidence, report generation under 30 seconds, and recovery within 25% of baseline under the same warmed-up workload. Measure manual diagnosis versus assisted diagnosis separately if claiming time saved. Automated fixtures and mocked collector checks do not validate network connectivity, actual Oracle grants, or performance improvement.
