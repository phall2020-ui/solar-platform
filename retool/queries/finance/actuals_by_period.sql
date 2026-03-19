-- ============================================================
-- Finance Query: Actuals by Period
-- Resource: AzureSQL_Finance
--
-- Returns actual financial data grouped by financial period,
-- account category, and project.
--
-- SETUP: Replace table/column names with your actual schema.
-- Run the schema discovery queries in datasources/azure_sql_analysis.md
-- to identify your table structure.
-- ============================================================

-- ─── CONFIGURABLE PARAMETERS ─────────────────────────────────────────────────
-- In Retool, these become {{ }} template variables:
--   {{ financial_year }}  — e.g. '2024/25'
--   {{ period_from }}     — e.g. 1
--   {{ period_to }}       — e.g. 12
--   {{ project_code }}    — e.g. 'PROJ-001' (optional, NULL = all projects)
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
    d.financial_year,
    d.period_number,
    d.period_name,
    d.calendar_month,
    d.calendar_year,
    d.month_name,
    d.period_start,
    d.period_end,

    a.account_code,
    a.account_name,
    a.account_category,
    a.account_subcategory,
    a.pl_line,
    a.cost_type,

    p.project_code,
    p.project_name,
    p.cost_centre,

    -- Amounts
    SUM(f.debit_amount)  AS total_debits,
    SUM(f.credit_amount) AS total_credits,
    SUM(f.net_amount)    AS net_amount,
    COUNT(f.transaction_id) AS transaction_count

FROM fact_actuals f

-- Join to date/period dimension
INNER JOIN dim_date d
    ON f.date_key = d.date_key

-- Join to account/COA dimension
INNER JOIN dim_account a
    ON f.account_key = a.account_key

-- Join to project dimension
INNER JOIN dim_project p
    ON f.project_key = p.project_key

WHERE
    d.financial_year = {{financial_year}}
    AND d.period_number BETWEEN {{period_from}} AND {{period_to}}
    AND (
        {{project_code}} IS NULL
        OR p.project_code = {{project_code}}
    )
    AND f.is_reversal = 0   -- exclude reversal entries if applicable
    AND f.posting_status = 'Posted'

GROUP BY
    d.financial_year,
    d.period_number,
    d.period_name,
    d.calendar_month,
    d.calendar_year,
    d.month_name,
    d.period_start,
    d.period_end,
    a.account_code,
    a.account_name,
    a.account_category,
    a.account_subcategory,
    a.pl_line,
    a.cost_type,
    p.project_code,
    p.project_name,
    p.cost_centre

ORDER BY
    d.period_number,
    a.account_category,
    p.project_code;


-- ─── SIMPLIFIED VERSION (if you have a flatter schema) ────────────────────────
/*
SELECT
    financial_year,
    period_number,
    period_name,
    account_code,
    account_name,
    account_category,
    project_code,
    SUM(amount) AS total_amount
FROM your_transactions_table
WHERE
    financial_year = {{financial_year}}
    AND period_number BETWEEN {{period_from}} AND {{period_to}}
GROUP BY
    financial_year, period_number, period_name,
    account_code, account_name, account_category, project_code
ORDER BY period_number, account_code;
*/
