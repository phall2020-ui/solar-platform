# Spreadsheet / Link Data — Retool Import Guide

## Overview

Static mapping tables (Finance Period → Month, Chart of Accounts, etc.) need to be loaded into Retool so they can be joined against live CRM and finance data. There are three approaches depending on how often the data changes.

---

## Approach 1: Retool Database Tables (Recommended)

Retool includes a hosted PostgreSQL database. Create permanent tables for your mapping data here.

### Create the Finance Period Map Table

In Retool → **Database → SQL Query**:

```sql
CREATE TABLE IF NOT EXISTS finance_period_map (
    id              SERIAL PRIMARY KEY,
    financial_year  VARCHAR(10) NOT NULL,   -- e.g. "2024/25"
    period_number   INTEGER NOT NULL,       -- 1 through 12 (or 13)
    period_name     VARCHAR(20) NOT NULL,   -- "P1", "P2" etc.
    calendar_month  INTEGER NOT NULL,       -- 1-12
    calendar_year   INTEGER NOT NULL,
    month_name      VARCHAR(20) NOT NULL,   -- "April", "May" etc.
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    UNIQUE (financial_year, period_number)
);
```

### Populate Finance Period Map

Example data (April-to-March financial year, FY2024/25):

```sql
INSERT INTO finance_period_map
    (financial_year, period_number, period_name, calendar_month, calendar_year, month_name, period_start, period_end)
VALUES
    ('2024/25',  1, 'P1',  4, 2024, 'April',     '2024-04-01', '2024-04-30'),
    ('2024/25',  2, 'P2',  5, 2024, 'May',        '2024-05-01', '2024-05-31'),
    ('2024/25',  3, 'P3',  6, 2024, 'June',       '2024-06-01', '2024-06-30'),
    ('2024/25',  4, 'P4',  7, 2024, 'July',       '2024-07-01', '2024-07-31'),
    ('2024/25',  5, 'P5',  8, 2024, 'August',     '2024-08-01', '2024-08-31'),
    ('2024/25',  6, 'P6',  9, 2024, 'September',  '2024-09-01', '2024-09-30'),
    ('2024/25',  7, 'P7', 10, 2024, 'October',    '2024-10-01', '2024-10-31'),
    ('2024/25',  8, 'P8', 11, 2024, 'November',   '2024-11-01', '2024-11-30'),
    ('2024/25',  9, 'P9', 12, 2024, 'December',   '2024-12-01', '2024-12-31'),
    ('2024/25', 10, 'P10', 1, 2025, 'January',    '2025-01-01', '2025-01-31'),
    ('2024/25', 11, 'P11', 2, 2025, 'February',   '2025-02-01', '2025-02-28'),
    ('2024/25', 12, 'P12', 3, 2025, 'March',      '2025-03-01', '2025-03-31');
-- Repeat for each financial year
```

> **Tip**: If you have a 13-period calendar (e.g., 4-4-5 weeks), add `period_weeks` and `period_type` columns.

### Create the Chart of Accounts Table

```sql
CREATE TABLE IF NOT EXISTS chart_of_accounts (
    id                  SERIAL PRIMARY KEY,
    account_code        VARCHAR(20) NOT NULL UNIQUE,
    account_name        VARCHAR(200) NOT NULL,
    account_category    VARCHAR(100),   -- "Revenue", "Direct Cost", "Overhead" etc.
    account_subcategory VARCHAR(100),   -- "Construction Revenue", "Grid Connection" etc.
    pl_line             VARCHAR(100),   -- P&L line grouping
    cost_type           VARCHAR(50),    -- "CapEx", "OpEx", "Revenue"
    is_active           BOOLEAN DEFAULT true,
    sort_order          INTEGER
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_coa_code ON chart_of_accounts(account_code);
CREATE INDEX IF NOT EXISTS idx_coa_category ON chart_of_accounts(account_category);
```

Populate from your spreadsheet (paste rows as SQL VALUES or use the CSV import below).

### Create Project-Finance Link Table

This is the key link between CRM project IDs and Finance project codes:

```sql
CREATE TABLE IF NOT EXISTS project_finance_link (
    id                  SERIAL PRIMARY KEY,
    crm_project_id      VARCHAR(50) NOT NULL,   -- Dataverse record GUID
    crm_project_name    VARCHAR(200),
    finance_project_code VARCHAR(50) NOT NULL,  -- Code used in Azure SQL
    finance_cost_centre  VARCHAR(50),
    notes               TEXT,
    UNIQUE (crm_project_id),
    UNIQUE (finance_project_code)
);
```

---

## Approach 2: CSV Import via Retool Database UI

1. In Retool → **Database → Import Data**
2. Select your CSV file
3. Map columns to the table schema
4. Click Import

This is the fastest way to load data from existing spreadsheets.

---

## Approach 3: JavaScript Transformer (for truly static data)

If the mapping never changes, embed it directly in a Retool transformer:

```javascript
// transformer: periodMapTransformer
// This is called from other queries to convert period numbers to months

const PERIOD_MAP = {
  "2024/25": {
    1:  { month: 4,  year: 2024, name: "April" },
    2:  { month: 5,  year: 2024, name: "May" },
    3:  { month: 6,  year: 2024, name: "June" },
    4:  { month: 7,  year: 2024, name: "July" },
    5:  { month: 8,  year: 2024, name: "August" },
    6:  { month: 9,  year: 2024, name: "September" },
    7:  { month: 10, year: 2024, name: "October" },
    8:  { month: 11, year: 2024, name: "November" },
    9:  { month: 12, year: 2024, name: "December" },
    10: { month: 1,  year: 2025, name: "January" },
    11: { month: 2,  year: 2025, name: "February" },
    12: { month: 3,  year: 2025, name: "March" }
  }
  // Add more financial years as needed
};

return PERIOD_MAP;
```

---

## Keeping Link Tables Up to Date

| Table | Update Frequency | Recommended Method |
|-------|-----------------|-------------------|
| `finance_period_map` | Once per year (new FY) | Retool Database UI or SQL INSERT |
| `chart_of_accounts` | Infrequently | CSV re-import or SQL UPDATE |
| `project_finance_link` | When new projects start | Retool form/table (see app page "Admin") |

The Retool app includes an **Admin** page where authorised users can manage the project link table without needing database access.

---

## Exporting from Excel/Google Sheets

Before importing, ensure your spreadsheet CSVs have:
1. A header row with clean column names (no spaces — use underscores)
2. No merged cells
3. Date columns in ISO format (`YYYY-MM-DD`)
4. Consistent values in code/category columns (no trailing spaces)

### PowerShell one-liner to clean a CSV
```powershell
Import-Csv "chart_of_accounts.csv" |
  Select-Object @{N='account_code';E={$_.AccountCode.Trim()}},
                @{N='account_name';E={$_.AccountName.Trim()}},
                @{N='account_category';E={$_.Category.Trim()}} |
  Export-Csv "coa_clean.csv" -NoTypeInformation
```
