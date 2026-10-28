-- Run manually only against the test object created by setup.sql.
WHENEVER SQLERROR EXIT SQL.SQLCODE
ALTER INDEX osd_demo_customer_ix INVISIBLE;
PROMPT Warm up again BEFORE capturing comparison-start. Verify the changed plan.
