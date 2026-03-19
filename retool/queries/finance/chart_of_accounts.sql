-- ============================================================
-- Finance Query: Chart of Accounts Reference
-- Resource: AzureSQL_Finance  (or Retool Database if loaded there)
--
-- Returns the full COA for dropdowns, filtering, and report labels.
-- ============================================================

SELECT
    account_code,
    account_name,
    account_category,
    account_subcategory,
    pl_line,
    cost_type,
    sort_order,
    is_active
FROM dim_account
WHERE is_active = 1
ORDER BY sort_order, account_code;


-- ─── ALTERNATIVE: if COA is in Retool Database ────────────────────────────────
/*
SELECT
    account_code,
    account_name,
    account_category,
    account_subcategory,
    pl_line,
    cost_type,
    sort_order,
    is_active
FROM chart_of_accounts
WHERE is_active = true
ORDER BY sort_order NULLS LAST, account_code;
*/
