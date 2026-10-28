-- Restores the test index after the demonstration, including interrupted demos.
WHENEVER SQLERROR EXIT SQL.SQLCODE
ALTER INDEX osd_demo_customer_ix VISIBLE;
PROMPT Warm up again BEFORE capturing recovery-start.
