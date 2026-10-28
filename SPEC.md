# Oracle SQL Regression Detective — MVP scope

Status: scope recorded before coding; implementation and verification status are tracked in TASKS.md and RESULTS.md.
Time budget: 90–120 minutes. Date: 2026-10-28.

## Outcome

A DBA compares two captured workload windows in one Oracle database and receives a ranked report of SQL statements that became slower, whether their observed execution plans changed, and what evidence to investigate next.

The smallest end-to-end slice is: connect → capture baseline → capture comparison → generate a local JSON and HTML report → apply a DBA-selected fix in the test schema → capture again and verify recovery.

Success means identifying a deliberately regressed query, leaving an unchanged control query unflagged, and showing measured recovery. The tool automates evidence collection and prioritization; it does not establish root cause or apply fixes.

## Scope and implementation shape

- One Oracle instance, one connected PDB (or one non-CDB database), one parsing schema.
- One local Python CLI using `python-oracledb`; JSON files for persistence and a standalone HTML report. No web server or database-side installation.
- Oracle 19c is the initial reference target; actual version and connection compatibility must be checked before implementation proceeds beyond connection setup.
- Use `V$SQL` for cumulative statistics at child-cursor level. This keeps statistics and observed plan hashes associated with the same cursor. Do not infer per-plan performance from a single SQL-level plan hash.
- Save available plan text through `DBMS_XPLAN.DISPLAY_CURSOR` during capture, while each cursor is still cached.
- Query Oracle read-only. Store all tool outputs locally. Test-workload setup and changes are separate, explicitly run demo SQL in a disposable schema.
- No AWR, ASH, SQL Tuning Advisor, or SQL Monitor dependency in this MVP.

## Input contract

### Connection and selection

- DSN/service, username, and password supplied through environment variables or a password prompt; never command-line password arguments, committed configuration, or reports.
- Required `schema` and explicit allowlist of demo `SQL_ID` values, keeping collection bounded and excluding the collector's own SQL.
- Required output directory and capture label: `baseline`, `comparison`, or `recovery`.
- Configurable thresholds, initially: slowdown ratio >= 2.0; absolute average increase >= 0.050 seconds; >= 10 executions in both windows; maximum 5 ranked rows.
- User identifies the demo SQL IDs after warm-up. Automatic discovery is outside this slice.

### Capture bundle

Each workload window consists of two snapshots, taken before and after a completed workload batch. A baseline/comparison analysis therefore needs four snapshots. Wait until demo queries finish and fetch all rows before taking the end snapshot.

Each snapshot records:

- `schema_version`, capture timestamp in UTC, database identity, instance identity and startup time, connected container identity, parsing schema, and capture label.
- Per child cursor: `sql_id`, `child_number`, `child_address`, `plan_hash_value`, `first_load_time`, `last_load_time`, `loads`, `invalidations`, `executions`, `end_of_fetch_count`, `users_executing`, `elapsed_time_us`, `cpu_time_us`, `buffer_gets`, and `disk_reads`.
- SQL text and available plan text, with capture status. Preserve plan hashes as strings.

Database identity comes from `V$DATABASE`, instance/startup identity from `V$INSTANCE`, and connected-container identity from session context. Selected-schema filtering uses `V$SQL.PARSING_SCHEMA_NAME`.

Comparison accepts saved capture bundles as well as newly collected ones. Synthetic fixtures must be labeled `fixture`; they demonstrate analysis only and do not establish successful Oracle integration.

## Calculation and comparison rules

1. Compare snapshots only when database, instance startup, container, schema, and selected SQL IDs match. The comparison window must follow the baseline window.
2. Within each window, match cursor incarnations using SQL ID, child number/address, and load metadata. Detect changed child cohorts, reloads/invalidations, plan changes within the window, or decreasing cumulative counters. Mark affected SQL as `insufficient_data` instead of guessing missing work.
3. New plans/child cursors between windows are allowed. Warm up after a demo change and before the next start snapshot, so each individual window has stable cursor identities.
4. For eligible cursors, subtract start counters from end counters. Aggregate the deltas across children by SQL ID. Use only children with executions in the window to construct the observed plan-hash set.
5. `avg_elapsed_s = sum(delta_elapsed_time_us) / sum(delta_executions) / 1_000_000`. Compute CPU seconds, buffer gets, and disk reads per execution similarly. Never average child averages without execution weighting.
6. Require the minimum execution count in both windows and a positive baseline average. Zero denominators and missing SQL become `insufficient_data`, not infinite slowdown.
7. `slowdown_ratio = comparison_avg_elapsed_s / baseline_avg_elapsed_s`.
8. `estimated_extra_elapsed_s = max(0, comparison_avg_elapsed_s - baseline_avg_elapsed_s) * comparison_executions`.
9. Flag `regressed` only when both slowdown and absolute-increase thresholds pass. Rank flagged SQL by estimated extra elapsed seconds descending, then SQL ID for a deterministic tie-breaker.
10. `plan_change` is `observed` when the active plan-hash sets differ, `not_observed` when complete sets match, and `unknown` when hashes are unavailable. This is an observation, not a causal conclusion. Multiple plans remain visible as sets.

Elapsed statistics describe Oracle SQL work and are not application downtime. Parallel execution and work crossing snapshot boundaries complicate interpretation. The MVP demo uses serial SELECT statements, identical bind values, complete fetching, and quiescent snapshot boundaries. Capture violations visible in the counters produce warnings or `insufficient_data`; the tool cannot prove workload equivalence from these views alone.

## Output schema

Produce `report.json` as the machine-readable contract and `report.html` presenting the same results. The following example is illustrative, not measured data:

```json
{
  "schema_version": "1.0",
  "source": "oracle",
  "generated_at_utc": "2026-10-28T18:00:00Z",
  "target": {
    "database_id": "123456",
    "instance_name": "demo",
    "container_name": "DEMO_PDB",
    "parsing_schema": "DEMO"
  },
  "windows": {
    "baseline": {"start_utc": "2026-10-28T17:00:00Z", "end_utc": "2026-10-28T17:05:00Z"},
    "comparison": {"start_utc": "2026-10-28T17:10:00Z", "end_utc": "2026-10-28T17:15:00Z"}
  },
  "thresholds": {
    "min_executions": 10,
    "min_slowdown_ratio": 2.0,
    "min_avg_increase_s": 0.05,
    "top_n": 5
  },
  "summary": {"selected": 2, "regressed": 1, "not_regressed": 1, "insufficient_data": 0},
  "results": [
    {
      "rank": 1,
      "sql_id": "example_sqlid",
      "status": "regressed",
      "sql_text": "select ...",
      "baseline": {
        "executions": 100,
        "avg_elapsed_s": 0.08,
        "avg_cpu_s": 0.05,
        "buffer_gets_per_exec": 400,
        "disk_reads_per_exec": 0,
        "plan_hashes": ["111111111"]
      },
      "comparison": {
        "executions": 100,
        "avg_elapsed_s": 0.92,
        "avg_cpu_s": 0.70,
        "buffer_gets_per_exec": 35000,
        "disk_reads_per_exec": 0,
        "plan_hashes": ["222222222"]
      },
      "slowdown_ratio": 11.5,
      "estimated_extra_elapsed_s": 84.0,
      "plan_change": "observed",
      "plans": [
        {"window": "baseline", "child_number": 0, "plan_hash": "111111111", "status": "captured", "text": "..."},
        {"window": "comparison", "child_number": 1, "plan_hash": "222222222", "status": "captured", "text": "..."}
      ],
      "evidence": ["Average elapsed time increased 11.5x", "Observed plan-hash set changed"],
      "next_checks": ["Compare captured access paths and join methods; inspect relevant index availability and optimizer statistics"],
      "warnings": []
    }
  ],
  "warnings": []
}
```

- `source`: `oracle` or `fixture`.
- `status`: `regressed`, `not_regressed`, or `insufficient_data`.
- `plan_change`: `observed`, `not_observed`, or `unknown`.
- Plan capture `status`: `captured` or `unavailable`; unavailable text is null and carries a warning.
- Include every selected SQL in JSON so missing/excluded data is visible. `rank` is null for non-regressions; unknown metrics are null, never fabricated zeros. HTML shows the top five regressions plus a compact status list for all selected SQL.
- Missing plan text does not erase valid runtime findings. Distinguish a missing plan from evidence that a plan did not change.
- Evidence and next checks use deterministic templates. No model/API call is needed. A full table scan alone is not labeled a defect.
- Escape SQL and plan text in HTML. Reports contain SQL text and remain local.

## User flow

1. Configure the connection and run a preflight that verifies connectivity, target identity, selected-view access, and plan-display access. Return actionable errors without credentials.
2. Warm up the demo workload, identify its SQL IDs, and capture baseline start/end snapshots around repeated completed executions.
3. In the disposable test schema, introduce the known slowdown. Keep SQL text and binds unchanged. For example, make a dedicated demo index invisible, then warm up and verify the intended plan change.
4. Capture comparison start/end snapshots and generate the report with one analysis command.
5. Open the HTML report: see the highest-impact SQL, measurements, plan-change status, saved plans, and next checks.
6. The DBA restores the known test condition, warms up, captures recovery, and compares baseline versus recovery with the same analyzer.

## Non-goals

- Automatic fixes, index creation, statistics gathering, plan forcing, SQL Profiles, or production workload changes.
- Autonomous root-cause diagnosis, SQL rewriting, or natural-language chat.
- Fleet discovery, RAC aggregation, cross-PDB analysis, scheduled monitoring, alert delivery, or authentication UI.
- Historical analysis before local collection began; AWR/ASH integration.
- Handling arbitrary production workloads, parallel-query response-time attribution, percentile latency, or bind-value capture.
- A general execution-plan diff engine. Side-by-side saved plan text and observed plan hashes are sufficient.
- Persistent monitoring tables inside Oracle, dashboards requiring a server, or deployment packaging.

## Acceptance checks

### Analyzer checks using small fixtures

1. Arithmetic: 100 executions at 0.08 seconds versus 100 at 0.92 seconds yields 11.5x slowdown and 84 estimated extra elapsed seconds. Unequal child execution counts verify weighted aggregation.
2. Classification: unchanged control is not flagged; low sample counts, zero baseline, and absent SQL yield explicit insufficient-data results. Threshold boundaries behave as specified.
3. Data quality: cursor reload/reset, changed child cohort within a window, and different instance startup are detected. Incompatible target bundles fail comparison; per-SQL gaps are reported without suppressing valid peers.
4. Plans: changed/matching/unknown plan sets are distinguished; missing plan text preserves runtime findings with a warning.
5. Report: ranking is deterministic, all selected SQL have status, fixture data is labeled, and SQL containing HTML characters renders as text. No password or connection secret is written to artifacts.

### Live end-to-end demo

- Preflight succeeds against the actual test Oracle instance and retrieves at least one cursor plan.
- Baseline, slowdown, and recovery each contain at least 10 fully fetched serial executions for the target and an unchanged control.
- The known slowdown meets the configured thresholds and ranks first; the control is not flagged; captured plan evidence matches the induced change.
- After capture completes, the bounded report generates within 30 seconds.
- After restoring the test condition, target average elapsed time is within 25% of baseline, under the same warmed-up workload. Record actual measurements; a miss is investigated, not reported as success.
- Time a manual diagnosis and a report-assisted diagnosis on the same scenario. Target a 50% reduction; report it as a small demo observation, not a proven operational saving. If no manual baseline is measured, claim only measured tool time.
- A fixture-only demo passes analyzer checks but does not pass live integration acceptance.

## Riskiest dependency and first gate

**A reachable Oracle test database with sufficient diagnostic read privileges, retrievable cursor plans, and permission to prepare a reproducible slowdown in a disposable schema.** These conditions are not yet verified.

Use the first 15 minutes to connect, read the required views, retrieve a plan, and confirm that the test workload can generate a stable baseline and a slower execution of the same SQL. Confirm existing Python/driver availability during this gate.

If access or privileges cannot be obtained within that time, continue with clearly labeled fixtures to validate the analyzer/report. Explicitly leave Oracle integration and live performance improvement unvalidated; do not substitute a fixture result for end-to-end success.

Secondary risk: real execution noise or bind sensitivity may swamp the intended regression. Keep the demo data, bind values, fetch behavior, and serial execution settings fixed; warm up each phase before snapshots.

## Delivery budget

- 0–15 min: dependency gate and repeatable workload.
- 15–50 min: snapshot collection, validation, interval calculations, and ranking.
- 50–70 min: JSON contract and HTML report.
- 70–90 min: analyzer checks and first live demonstration.
- 90–120 min, if available: recovery verification, diagnosis timing, and demo polish.

Deliverables: collector/analyzer CLI, local capture bundles, `report.json`, `report.html`, a short runbook, and measured demo results.

## Technical references

- Oracle 19c V$SQL: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html
- Oracle 19c DBMS_XPLAN and required privileges: https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html
- Oracle 19c V$SQLSTATS (SQL-level alternative, not the MVP collector): https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQLSTATS.html
