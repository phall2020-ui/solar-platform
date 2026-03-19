# Link / Mapping Tables — Schema Reference

These tables live in **Retool Database** (the hosted PostgreSQL instance) and act as the glue between CRM and Finance data.

---

## Table: project_finance_link

**Purpose**: Maps CRM project GUIDs (from Dataverse) to Finance project codes (from Azure SQL).

This is the most important link table. Without it, Retool can't automatically join pipeline data to financial data.

```sql
CREATE TABLE IF NOT EXISTS project_finance_link (
    id                   SERIAL PRIMARY KEY,
    crm_project_id       VARCHAR(50) NOT NULL,
    crm_project_name     VARCHAR(200),
    finance_project_code VARCHAR(50) NOT NULL,
    finance_cost_centre  VARCHAR(50),
    link_status          VARCHAR(20) DEFAULT 'active',   -- 'active', 'archived'
    notes                TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (crm_project_id),
    UNIQUE (finance_project_code)
);

CREATE INDEX idx_pfl_crm    ON project_finance_link (crm_project_id);
CREATE INDEX idx_pfl_fin    ON project_finance_link (finance_project_code);
```

### How to populate
Either:
- **Via the Admin page** in the Retool app (the "Project Links" management table)
- **Directly via SQL** using a bulk INSERT from your existing records:

```sql
INSERT INTO project_finance_link (crm_project_id, crm_project_name, finance_project_code, finance_cost_centre)
VALUES
    ('guid-1111-...', 'Blachford Solar Farm', 'PROJ-001', 'CC-SOUTH'),
    ('guid-2222-...', 'Cromwell Tools Rooftop', 'PROJ-002', 'CC-NORTH'),
    -- ... add all your projects
;
```

**Alternative**: If your CRM assets already have a `cr_financecode` field, you can populate the link table automatically with a Retool workflow/query that syncs them.

---

## Table: finance_period_map

**Purpose**: Maps financial period numbers to calendar months. See full DDL in `datasources/spreadsheet_imports.md`.

```sql
-- Quick reference
SELECT financial_year, period_number, period_name, calendar_month, calendar_year, month_name
FROM finance_period_map
ORDER BY financial_year, period_number;
```

---

## Table: chart_of_accounts

**Purpose**: Account code → display name + category mappings. Mirrors `dim_account` in Azure SQL but stored in Retool Database for use in transformer joins.

> **Note**: Only needed here if your Azure SQL doesn't have a `dim_account` table, or if you want Retool-editable COA categories.

```sql
-- Quick reference
SELECT account_code, account_name, account_category, pl_line, cost_type
FROM chart_of_accounts
ORDER BY sort_order, account_code;
```

---

## Cross-Source Join Map

```
Retool Database: project_finance_link
  crm_project_id    ←→   Dataverse: cr_projects.cr_projectid
  finance_project_code ←→ Azure SQL: dim_project.project_code

Retool Database: finance_period_map
  financial_year + period_number ←→ Azure SQL: fact_actuals.financial_year + period_number

Retool Database: chart_of_accounts
  account_code ←→ Azure SQL: dim_account.account_code  (or fact_actuals.account_code)
```

---

## Managing Link Tables in the Retool App

The Retool app includes an **Admin** page with:

1. **Project Links** — editable table showing all CRM projects and their Finance codes. Users with admin access can add/edit/remove links.

2. **COA Manager** — view/edit account category assignments.

3. **Period Map** — view the period → month mapping (read-only, updated manually for new FYs).

### Retool Queries for Admin Page

**Get all projects with link status:**
```javascript
// This runs in sequence: first CRM, then join to link table
// Use a transformer to merge:

const crmProjects   = getPipelineProjects.data?.value || [];
const existingLinks = getProjectLinks.data || [];

const linkByCrmId = Object.fromEntries(existingLinks.map(l => [l.crm_project_id, l]));

return crmProjects.map(p => ({
  crm_project_id:      p.cr_projectid,
  crm_project_name:    p.cr_name,
  finance_project_code: linkByCrmId[p.cr_projectid]?.finance_project_code || "",
  finance_cost_centre:  linkByCrmId[p.cr_projectid]?.finance_cost_centre  || "",
  is_linked:            !!linkByCrmId[p.cr_projectid],
}));
```

**Upsert a project link:**
```sql
INSERT INTO project_finance_link
    (crm_project_id, crm_project_name, finance_project_code, finance_cost_centre, updated_at)
VALUES
    ({{ crmId }}, {{ crmName }}, {{ financeCode }}, {{ costCentre }}, NOW())
ON CONFLICT (crm_project_id)
DO UPDATE SET
    crm_project_name     = EXCLUDED.crm_project_name,
    finance_project_code = EXCLUDED.finance_project_code,
    finance_cost_centre  = EXCLUDED.finance_cost_centre,
    updated_at           = NOW();
```
