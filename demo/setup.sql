-- Run manually ONLY in a disposable schema. Creates new uniquely named objects;
-- existing objects cause failure rather than being replaced or dropped.
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET ECHO ON
CREATE TABLE osd_demo_orders AS
SELECT level order_id,
       MOD(level, 10000) customer_id,
       MOD(level, 97) amount,
       RPAD('demo', 200, 'x') payload
FROM dual CONNECT BY level <= 500000;
ALTER TABLE osd_demo_orders ADD CONSTRAINT osd_demo_orders_pk PRIMARY KEY (order_id);
CREATE INDEX osd_demo_customer_ix ON osd_demo_orders(customer_id);
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(USER, 'OSD_DEMO_ORDERS', cascade => TRUE);
END;
/
PROMPT Setup complete. Keep this SQL session available for workload runs.
