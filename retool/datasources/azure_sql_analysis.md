# Azure SQL / Analysis Services — Retool Connection Guide

## Overview

Your finance data is stored in Azure SQL and exposed through SQL Server Analysis Services (SSAS).

**Recommended approach**: Connect Retool directly to Azure SQL for most reporting. Use Analysis Services queries only for measures/calculations that are exclusively defined in the SSAS model and can't be replicated in SQL.

---

## Option A: Direct Azure SQL Connection (Recommended)

### Prerequisites
- Azure SQL server name (e.g., `yourserver.database.windows.net`)
- Database name
- SQL login credentials (or set up a dedicated reporting user)
- Firewall rule allowing Retool's IP ranges

### Retool Firewall Setup
Add these Retool IP addresses to your Azure SQL firewall (Azure Portal → SQL Server → Networking → Firewall rules):

**Retool Cloud IPs** (check https://docs.retool.com/docs/ip-allowlisting for current list):
```
34.218.156.197
34.218.150.91
52.10.129.73
```

For self-hosted Retool, allow your Retool server's outbound IP.

### Retool Resource Setup
1. Retool → **Resources → Create New Resource → Microsoft SQL Server**
2. Settings:
   ```
   Host:       yourserver.database.windows.net
   Port:       1433
   Database:   FinanceDB (your database name)
   Username:   retool_reader (dedicated read-only SQL user)
   Password:   <password>
   SSL:        Enabled (required for Azure SQL)
   ```
3. Name: `AzureSQL_Finance`
4. Click **Test → Save**

### Create a Read-Only SQL User (run once in Azure SQL)
```sql
-- Run in master database
CREATE LOGIN retool_reader WITH PASSWORD = 'StrongPassword123!';

-- Run in your finance database
CREATE USER retool_reader FOR LOGIN retool_reader;

-- Grant read-only access
ALTER ROLE db_datareader ADD MEMBER retool_reader;

-- If using specific schemas only:
GRANT SELECT ON SCHEMA::fact TO retool_reader;
GRANT SELECT ON SCHEMA::dim TO retool_reader;
GRANT SELECT ON SCHEMA::dbo TO retool_reader;
```

---

## Option B: Analysis Services via REST API

SSAS Tabular (Azure Analysis Services) exposes an XMLA endpoint and an execute REST endpoint for DAX queries.

### Retool Resource Setup for SSAS
1. Retool → **Resources → Create New Resource → REST API**
2. Settings:
   ```
   Base URL:         https://eastus.asazure.windows.net/servers/yourserver/models/yourmodel
   Authentication:   OAuth 2.0
   Token URL:        https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token
   Client ID:        <app-registration-client-id>
   Client Secret:    <client-secret>
   Scope:            https://*.asazure.windows.net/.default
   ```
3. Name: `SSAS_Finance`

### Azure App Registration for SSAS
1. Azure Portal → **Azure Active Directory → App Registrations → New Registration**
2. Name: `Retool-SSAS-Connector`
3. **API Permissions → Add permission → Azure Analysis Services → user_impersonation**
4. In SSAS: add the service principal as a **Server Administrator** or **Database Reader**

### DAX Query via REST API
```javascript
// Method: POST
// Path: /query
// Body:
{
  "queries": [
    {
      "query": "EVALUATE SUMMARIZECOLUMNS('Date'[Year], 'Date'[Period], ADDCOLUMNS(VALUES('Date'[Period]), \"Revenue\", [Total Revenue], \"Cost\", [Total Cost]))"
    }
  ],
  "serializerSettings": {
    "includeNulls": true
  }
}
```

---

## Option C: Power BI Premium / XMLA Endpoint

If your Analysis Services model is published to Power BI Premium, you can query it via the XMLA endpoint using the same DAX REST pattern above.

```
Base URL: powerbi://api.powerbi.com/v1.0/myorg/YourWorkspace
```

---

## Recommended Schema Pattern

Most finance databases for solar/energy companies follow a star schema. The queries in `queries/finance/` assume this structure:

```
dim_date          — date/period/financial year calendar
dim_project       — project reference (links to CRM project ID)
dim_account       — chart of accounts
dim_costcentre    — cost centres
fact_actuals      — actual transactions
fact_budget       — budget entries
```

Update `schemas/finance_tables.md` with your actual table and column names before using the query files.

---

## Schema Discovery Queries

Run these in Retool or SSMS to understand your table structure:

```sql
-- List all user tables
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_SCHEMA, TABLE_NAME;

-- List columns for a specific table
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'your_table_name'
ORDER BY ORDINAL_POSITION;

-- Row counts across all tables
SELECT
    t.name AS table_name,
    i.rows AS row_count
FROM sys.tables t
INNER JOIN sys.sysindexes i ON t.object_id = i.id AND i.indid < 2
ORDER BY i.rows DESC;
```

---

## Finance Period Handling

If your finance data uses financial periods (P1–P12 or P1–P13) rather than calendar months, there are two approaches:

### Approach 1: Period map in dim_date
Your `dim_date` table likely has a `FinancialPeriod` column. Join through it:
```sql
SELECT d.CalendarMonth, d.FinancialPeriod, f.Amount
FROM fact_actuals f
JOIN dim_date d ON f.DateKey = d.DateKey
```

### Approach 2: External mapping table
If the mapping is in a spreadsheet, load it into Retool Database or as a transformer. See `datasources/spreadsheet_imports.md`.

---

## Connecting SSAS via Power BI REST API (alternative)

If your model is in Power BI Premium and you have a Premium/Fabric workspace, you can embed reports or datasets:

```
// Resource: REST API
// Base URL: https://api.powerbi.com/v1.0/myorg
// Auth: OAuth2 with Power BI scope
// Scope: https://analysis.windows.net/powerbi/api/.default
```

DAX query endpoint:
```
POST /datasets/{datasetId}/executeQueries
Body: { "queries": [{ "query": "EVALUATE ..." }], "serializerSettings": { "includeNulls": true } }
```

This lets Retool directly query your existing Power BI dataset — preserving all your existing measure definitions and relationships without rebuilding anything.
