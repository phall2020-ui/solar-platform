# Finance Tables — Schema Reference

## Discovery

Run these in SSMS or Retool (AzureSQL_Finance resource) to identify your actual schema:

```sql
-- All tables
SELECT TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_SCHEMA, TABLE_NAME;

-- All columns in a table
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'your_table'
ORDER BY ORDINAL_POSITION;
```

---

## Assumed Star Schema

The SQL queries in `queries/finance/` assume a star schema. Update column names to match your actual structure.

---

## dim_date (Date / Period Dimension)

**Purpose**: Maps transaction dates to financial periods, months, years.

| Column | Type | Description |
|--------|------|-------------|
| `date_key` | INT | Surrogate key (YYYYMMDD or sequential integer) |
| `calendar_date` | DATE | Actual calendar date |
| `calendar_month` | INT | 1–12 |
| `calendar_year` | INT | e.g. 2024 |
| `month_name` | VARCHAR | "April", "May" etc. |
| `financial_year` | VARCHAR | "2024/25" |
| `period_number` | INT | 1–12 (or 1–13) |
| `period_name` | VARCHAR | "P1", "P2" etc. |
| `quarter` | INT | 1–4 |
| `financial_quarter` | VARCHAR | "Q1 2024/25" |
| `is_current_period` | BIT | 1 = current period |
| `is_current_year` | BIT | 1 = current FY |

**Note**: If your database doesn't have a `dim_date`, the `fact_actuals` table likely has a `transaction_date` column and a `financial_period` column directly. In that case, join to the `finance_period_map` table in Retool Database.

---

## dim_account (Chart of Accounts)

**Purpose**: Account code reference — links transaction account codes to display names and categories.

| Column | Type | Description |
|--------|------|-------------|
| `account_key` | INT | Surrogate key |
| `account_code` | VARCHAR(20) | Natural key (e.g. "4000", "6100") |
| `account_name` | VARCHAR(200) | Display name |
| `account_category` | VARCHAR(100) | "Revenue", "Direct Cost", "Overhead", "Balance Sheet" |
| `account_subcategory` | VARCHAR(100) | Sub-grouping |
| `pl_line` | VARCHAR(100) | P&L summary line (e.g. "Gross Profit", "EBITDA") |
| `cost_type` | VARCHAR(50) | "CapEx", "OpEx", "Revenue" |
| `sort_order` | INT | Display sort order |
| `is_active` | BIT | 1 = active account |

---

## dim_project (Project / Cost Centre)

**Purpose**: Project reference — links finance transactions to CRM projects.

| Column | Type | Description |
|--------|------|-------------|
| `project_key` | INT | Surrogate key |
| `project_code` | VARCHAR(50) | Natural key — **must match `cr_financecode` in CRM** |
| `project_name` | VARCHAR(200) | Display name |
| `cost_centre` | VARCHAR(50) | Cost centre code |
| `project_type` | VARCHAR(100) | "Construction", "O&M", "Development" etc. |
| `client_code` | VARCHAR(50) | Client reference |
| `start_date` | DATE | Project start |
| `end_date` | DATE | Project end / completion |
| `is_active` | BIT | 1 = active |

---

## fact_actuals (Actuals Transactions)

**Purpose**: All posted financial transactions (GL entries, invoices, expenses etc.)

| Column | Type | Description |
|--------|------|-------------|
| `transaction_id` | BIGINT | Primary key |
| `date_key` | INT | FK → dim_date |
| `account_key` | INT | FK → dim_account |
| `project_key` | INT | FK → dim_project |
| `costcentre_key` | INT | FK → dim_costcentre (if separate) |
| `transaction_date` | DATE | Transaction date |
| `financial_year` | VARCHAR | "2024/25" (denormalised for performance) |
| `period_number` | INT | Financial period (denormalised) |
| `debit_amount` | DECIMAL(18,2) | Debit value |
| `credit_amount` | DECIMAL(18,2) | Credit value |
| `net_amount` | DECIMAL(18,2) | Net (debit - credit, or signed) |
| `description` | VARCHAR(500) | Transaction description |
| `reference` | VARCHAR(100) | Invoice/PO reference |
| `posting_status` | VARCHAR(20) | "Posted", "Draft", "Reversed" |
| `is_reversal` | BIT | 1 = reversal entry |
| `source_system` | VARCHAR(50) | Source (e.g. "Sage", "Xero", "Dynamics 365 Finance") |
| `created_at` | DATETIME | Row created timestamp |

---

## fact_budget (Budget Entries)

**Purpose**: Annual/period budget allocations for comparison against actuals.

| Column | Type | Description |
|--------|------|-------------|
| `budget_id` | BIGINT | Primary key |
| `date_key` | INT | FK → dim_date |
| `account_key` | INT | FK → dim_account |
| `project_key` | INT | FK → dim_project |
| `budget_amount` | DECIMAL(18,2) | Budget value for the period |
| `budget_version` | VARCHAR(50) | "Original", "Revised", "Forecast" |
| `financial_year` | VARCHAR | Denormalised |
| `period_number` | INT | Denormalised |

---

## Alternative: Flat Table Schema

If your Azure SQL schema is flatter (all data in one or two tables rather than a star), the equivalent structure would be:

```sql
-- Single transactions table (flat schema)
CREATE TABLE transactions (
    id              BIGINT PRIMARY KEY,
    transaction_date DATE,
    financial_year  VARCHAR(10),
    period_number   INT,
    account_code    VARCHAR(20),
    account_name    VARCHAR(200),
    category        VARCHAR(100),
    project_code    VARCHAR(50),
    project_name    VARCHAR(200),
    debit           DECIMAL(18,2),
    credit          DECIMAL(18,2),
    net             DECIMAL(18,2),
    description     VARCHAR(500),
    is_budget       BIT DEFAULT 0   -- 0=actual, 1=budget
);
```

If you have a flat schema, simplify the SQL queries in `queries/finance/` accordingly — remove the joins to dim_* tables and query the columns directly.

---

## Analysis Services Model (if using SSAS)

If your data is surfaced through Analysis Services, the DAX equivalents are:

| SSAS Measure | SQL Equivalent |
|-------------|---------------|
| `[Total Revenue]` | `SUM(fact_actuals[net_amount]) WHERE account_category = 'Revenue'` |
| `[Total Cost]` | `SUM(fact_actuals[net_amount]) WHERE account_category IN ('Direct Cost','Overhead')` |
| `[Gross Profit]` | `[Total Revenue] - [Total Cost]` |
| `[Margin %]` | `DIVIDE([Gross Profit], [Total Revenue])` |
| `[Budget Revenue]` | `SUM(fact_budget[budget_amount]) WHERE account_category = 'Revenue'` |
| `[Variance]` | `[Total Revenue] - [Budget Revenue]` |

DAX query template for Retool REST call:
```dax
EVALUATE
SUMMARIZECOLUMNS(
    'dim_date'[financial_year],
    'dim_date'[period_number],
    'dim_date'[month_name],
    'dim_project'[project_code],
    'dim_project'[project_name],
    "Revenue",     [Total Revenue],
    "Direct Cost", [Total Direct Cost],
    "Gross Profit",[Gross Profit],
    "Margin Pct",  [Margin %]
)
ORDER BY
    'dim_date'[financial_year],
    'dim_date'[period_number]
```
