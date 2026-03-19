-- ============================================================
-- Finance Query: Revenue by Project
-- Resource: AzureSQL_Finance
--
-- Summarises revenue and costs per project, enabling project-level
-- P&L. The project_code field links to the CRM via the
-- project_finance_link table in Retool Database.
--
-- Parameters:
--   {{ financial_year }}   — e.g. '2024/25'
--   {{ period_from }}      — integer
--   {{ period_to }}        — integer
-- ============================================================

SELECT
    p.project_code,
    p.project_name,
    p.cost_centre,

    -- Revenue lines
    SUM(CASE WHEN a.account_category = 'Revenue'      THEN f.net_amount ELSE 0 END) AS revenue,
    SUM(CASE WHEN a.account_category = 'Direct Cost'  THEN f.net_amount ELSE 0 END) AS direct_costs,
    SUM(CASE WHEN a.account_category = 'Overhead'     THEN f.net_amount ELSE 0 END) AS overheads,

    -- Derived
    SUM(CASE WHEN a.account_category = 'Revenue'      THEN f.net_amount ELSE 0 END)
    - SUM(CASE WHEN a.account_category IN ('Direct Cost', 'Overhead') THEN f.net_amount ELSE 0 END)
        AS gross_profit,

    -- Margin %
    CASE
        WHEN SUM(CASE WHEN a.account_category = 'Revenue' THEN f.net_amount ELSE 0 END) = 0
        THEN NULL
        ELSE ROUND(
            (
                SUM(CASE WHEN a.account_category = 'Revenue'     THEN f.net_amount ELSE 0 END)
                - SUM(CASE WHEN a.account_category IN ('Direct Cost','Overhead') THEN f.net_amount ELSE 0 END)
            )
            / SUM(CASE WHEN a.account_category = 'Revenue' THEN f.net_amount ELSE 0 END) * 100
        , 1)
    END AS margin_pct,

    COUNT(DISTINCT d.period_number) AS periods_with_data

FROM fact_actuals f
INNER JOIN dim_date    d ON f.date_key    = d.date_key
INNER JOIN dim_account a ON f.account_key = a.account_key
INNER JOIN dim_project p ON f.project_key = p.project_key

WHERE
    d.financial_year = {{financial_year}}
    AND d.period_number BETWEEN {{period_from}} AND {{period_to}}
    AND f.posting_status = 'Posted'
    AND f.is_reversal = 0

GROUP BY
    p.project_code,
    p.project_name,
    p.cost_centre

ORDER BY
    revenue DESC;
