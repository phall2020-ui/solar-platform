-- ============================================================
-- Finance Query: Budget vs Actual Variance
-- Resource: AzureSQL_Finance
--
-- Side-by-side budget and actual with variance amounts and %.
-- Parameters:
--   {{ financial_year }}     — e.g. '2024/25'
--   {{ period_from }}        — integer, e.g. 1
--   {{ period_to }}          — integer, e.g. 12
--   {{ account_category }}   — optional filter, e.g. 'Revenue'
-- ============================================================

WITH actuals AS (
    SELECT
        d.financial_year,
        d.period_number,
        d.period_name,
        d.month_name,
        a.account_code,
        a.account_name,
        a.account_category,
        a.account_subcategory,
        a.pl_line,
        p.project_code,
        p.project_name,
        SUM(f.net_amount) AS actual_amount
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
        d.financial_year, d.period_number, d.period_name, d.month_name,
        a.account_code, a.account_name, a.account_category, a.account_subcategory,
        a.pl_line, p.project_code, p.project_name
),

budget AS (
    SELECT
        d.financial_year,
        d.period_number,
        a.account_code,
        a.account_category,
        p.project_code,
        SUM(b.budget_amount) AS budget_amount
    FROM fact_budget b
    INNER JOIN dim_date    d ON b.date_key    = d.date_key
    INNER JOIN dim_account a ON b.account_key = a.account_key
    INNER JOIN dim_project p ON b.project_key = p.project_key
    WHERE
        d.financial_year = {{financial_year}}
        AND d.period_number BETWEEN {{period_from}} AND {{period_to}}
    GROUP BY
        d.financial_year, d.period_number,
        a.account_code, a.account_category,
        p.project_code
)

SELECT
    COALESCE(act.financial_year, bud.financial_year) AS financial_year,
    COALESCE(act.period_number,  bud.period_number)  AS period_number,
    COALESCE(act.period_name,    '')                  AS period_name,
    COALESCE(act.month_name,     '')                  AS month_name,
    COALESCE(act.account_code,   bud.account_code)   AS account_code,
    COALESCE(act.account_name,   '')                  AS account_name,
    COALESCE(act.account_category, bud.account_category) AS account_category,
    act.account_subcategory,
    act.pl_line,
    COALESCE(act.project_code,   bud.project_code)   AS project_code,
    act.project_name,

    COALESCE(bud.budget_amount, 0)                    AS budget_amount,
    COALESCE(act.actual_amount, 0)                    AS actual_amount,

    -- Variance: positive = better than budget
    COALESCE(act.actual_amount, 0) - COALESCE(bud.budget_amount, 0) AS variance_amount,

    -- Variance %: guard against division by zero
    CASE
        WHEN COALESCE(bud.budget_amount, 0) = 0 THEN NULL
        ELSE ROUND(
            (COALESCE(act.actual_amount, 0) - COALESCE(bud.budget_amount, 0))
            / ABS(bud.budget_amount) * 100,
            1
        )
    END AS variance_pct,

    -- RAG flag
    CASE
        WHEN COALESCE(bud.budget_amount, 0) = 0 THEN 'GREY'
        WHEN ABS(
            (COALESCE(act.actual_amount, 0) - COALESCE(bud.budget_amount, 0))
            / NULLIF(bud.budget_amount, 0)
        ) <= 0.05 THEN 'GREEN'
        WHEN ABS(
            (COALESCE(act.actual_amount, 0) - COALESCE(bud.budget_amount, 0))
            / NULLIF(bud.budget_amount, 0)
        ) <= 0.10 THEN 'AMBER'
        ELSE 'RED'
    END AS rag_status

FROM actuals act
FULL OUTER JOIN budget bud
    ON  act.financial_year = bud.financial_year
    AND act.period_number  = bud.period_number
    AND act.account_code   = bud.account_code
    AND act.project_code   = bud.project_code

WHERE
    (
        {{account_category}} = ''
        OR COALESCE(act.account_category, bud.account_category) = {{account_category}}
    )

ORDER BY
    COALESCE(act.period_number, bud.period_number),
    COALESCE(act.account_category, bud.account_category),
    COALESCE(act.account_code, bud.account_code);
