-- Run after warm-up. String concatenation keeps this diagnostic out of the match.
SELECT DISTINCT sql_id, sql_text
FROM v$sql
WHERE parsing_schema_name = USER
  AND (sql_text LIKE 'select /* osd_demo_' || 'target */%'
       OR sql_text LIKE 'select /* osd_demo_' || 'control */%');
