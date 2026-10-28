-- Usage in SQLcl/SQL*Plus: @demo/workload.sql 1 (warm-up), or 100 (measured batch).
-- Both SELECTs return one aggregate row and use the same bind and SQL text in all phases.
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET TIMING ON
ALTER SESSION DISABLE PARALLEL QUERY;
ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
DECLARE
  result_value NUMBER;
BEGIN
  FOR i IN 1..&1 LOOP
    EXECUTE IMMEDIATE
      'select /* osd_demo_target */ sum(amount) from osd_demo_orders where customer_id = :id'
      INTO result_value USING 42;
    EXECUTE IMMEDIATE
      'select /* osd_demo_control */ sum(amount) from osd_demo_orders where order_id = :id'
      INTO result_value USING 42;
  END LOOP;
END;
/
