# Retool Reporting Dashboard — Setup Guide

This guide covers connecting all three data sources to Retool and building the reporting dashboard.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        RETOOL APP                               │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │  Pipeline &  │  │  Finance &   │  │  Construction &     │  │
│  │  CRM Reports │  │  Budget View │  │  Asset Register     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬──────────┘  │
│         │                 │                      │             │
│  ┌──────┴─────────────────┴──────────────────────┴──────────┐  │
│  │              Query Layer + Transformers                   │  │
│  │     (OData / SQL / JavaScript transformer joins)          │  │
│  └──────┬──────────────────┬──────────────────┬─────────────┘  │
└─────────┼──────────────────┼──────────────────┼─────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ Dynamics 365 │   │ Azure SQL /      │   │ Spreadsheets     │
│ Dataverse    │   │ Analysis         │   │ (CSV uploads /   │
│ (ampyrprod.) │   │ Services         │   │  static tables)  │
└──────────────┘   └──────────────────┘   └──────────────────┘
```

---

## Step 1 — Connect Dynamics 365 Dataverse

### Using a REST API Resource
Retool does not have a native Dataverse connector. Use Retool's **REST API** resource type:

1. In Retool, go to **Resources → Create New Resource → REST API**
2. Fill in:
   - **Name**: `Dynamics365_CRM`
   - **Base URL**: `https://ampyrproduction.crm.dynamics.com/api/data/v9.2`
   - **Authentication**: OAuth 2.0 (Client Credentials flow)
   - **Token URL**: `https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token`
   - **Client ID** and **Client Secret**: from your Azure App Registration
   - **Scope**: `https://ampyrproduction.crm.dynamics.com/.default`
3. Add default headers: `OData-MaxVersion: 4.0`, `OData-Version: 4.0`, `Accept: application/json`

### Azure App Registration Setup
1. Azure Portal → **Azure Active Directory → App Registrations → New Registration**
2. Name: `Retool-CRM-Connector`
3. After creation, go to **API Permissions → Add Permission → Dynamics CRM → user_impersonation**
4. Create a **Client Secret** under Certificates & Secrets
5. In Dynamics 365 admin, add this app as an Application User with a Security Role that has read access to required tables

See `datasources/dynamics365_dataverse.md` for full details.

---

## Step 2 — Connect Azure SQL / Analysis Services

### Option A: Direct Azure SQL Connection (Recommended)
If the underlying data lives in Azure SQL tables:

1. Retool → **Resources → Create New → Microsoft SQL Server**
2. Fill in:
   - **Host**: `your-server.database.windows.net`
   - **Port**: `1433`
   - **Database**: your finance database name
   - **Username / Password**: SQL auth credentials, or use Managed Identity
   - Enable **SSL**
3. Name the resource: `AzureSQL_Finance`

### Option B: Analysis Services via XMLA (Tabular Model)
If you need to query Analysis Services cubes/tabular models with DAX:

1. Retool → **Resources → Create New → REST API** (Analysis Services doesn't have a native Retool connector)
2. **Base URL**: `https://your-region.asazure.windows.net/servers/your-server/models/your-model/`
3. **Authentication**: OAuth 2.0 with Azure AD
4. Queries are sent as HTTP POST with DAX in the request body (see `queries/finance/` folder)

> **Recommendation**: Where possible, expose Analysis Services measures as views in Azure SQL or use SSAS DAX via the REST endpoint. Direct SQL is simpler to manage in Retool.

See `datasources/azure_sql_analysis.md` for full details.

---

## Step 3 — Load Spreadsheet / Link Data

Retool handles static mapping tables (Finance Period → Month, Chart of Accounts etc.) in two ways:

### Option A: Retool Database (Recommended for small tables)
1. Retool → **Database → Create Table**
2. Create `finance_period_map` and `chart_of_accounts` tables
3. Import your CSV data directly
4. Query with standard SQL in any Retool query

### Option B: JavaScript Transformer (for truly static lookups)
Paste the mapping data directly into a Retool transformer as a JS object. Good for lookup tables that rarely change.

### Option C: CSV Upload via Retool Storage
Upload CSVs to Retool Storage and parse them via query. Useful when the data is updated periodically by non-developers.

See `datasources/spreadsheet_imports.md` for full details including SQL DDL for creating the link tables.

---

## Step 4 — Data Model & Joins

Because the three sources live in different systems, joins are handled via **Retool Transformers** (JavaScript). The pattern is:

1. Run queries against each source (CRM, Finance, Retool DB)
2. Pass the results into a transformer
3. The transformer performs the join in-memory using JavaScript

For large datasets (>50k rows), consider:
- Pre-joining in Azure SQL using linked server or SSIS pipeline
- Exposing a combined view from Analysis Services
- Using Retool's server-side query chaining

See `queries/transforms/` for all transformer code.

---

## Step 5 — Dashboard Pages

The app (`app/retool_app_export.json`) contains these pages:

| Page | Data Sources | Description |
|------|-------------|-------------|
| **Pipeline Overview** | CRM | All opportunities by stage, deal value, close date |
| **Construction Tracker** | CRM | Active builds, milestones, completion dates |
| **Asset Register** | CRM | Commissioned assets with capacity and location |
| **Finance Summary** | Azure SQL | Revenue, costs, margin by period |
| **Budget vs Actual** | Azure SQL | Variance analysis against budget |
| **COA Breakdown** | Azure SQL + COA map | Cost breakdown by account code |
| **Combined P&L** | CRM + Finance | Project-level profitability linking pipeline to finance |

---

## Directory Structure

```
retool/
├── README.md                          ← this file
├── datasources/
│   ├── dynamics365_dataverse.md       ← Dataverse setup (detailed)
│   ├── azure_sql_analysis.md          ← Azure SQL/SSAS setup (detailed)
│   └── spreadsheet_imports.md        ← CSV/link table setup
├── queries/
│   ├── crm/
│   │   ├── pipeline_projects.js       ← OData: opportunities/pipeline
│   │   ├── construction_stages.js     ← OData: construction records
│   │   ├── accounts.js                ← OData: accounts/clients
│   │   └── assets.js                  ← OData: commissioned assets
│   ├── finance/
│   │   ├── actuals_by_period.sql      ← Period-level actuals
│   │   ├── budget_vs_actual.sql       ← Budget variance
│   │   ├── revenue_by_project.sql     ← Revenue linked to projects
│   │   └── chart_of_accounts.sql     ← COA reference query
│   └── transforms/
│       ├── period_to_month_map.js     ← Finance period → calendar month
│       ├── coa_lookup.js              ← Account code → category mapping
│       ├── crm_finance_join.js        ← Cross-source project P&L join
│       └── pipeline_summary.js        ← Pipeline roll-up calculations
├── schemas/
│   ├── dataverse_tables.md            ← CRM table field reference
│   ├── finance_tables.md              ← Finance table field reference
│   └── link_tables.md                 ← Mapping table schemas + DDL
└── app/
    └── retool_app_export.json         ← Import this into Retool
```

---

## Importing the App

1. In Retool, go to **Apps → Import**
2. Select `app/retool_app_export.json`
3. After import, remap each query's resource to your actual resource names
4. Update the environment variables at the top of each query (server names, org URLs)

---

## Environment / Config Variables

Set these as **Retool Environment Variables** (Settings → Environment Variables):

| Variable | Description | Example |
|----------|-------------|---------|
| `DATAVERSE_ORG_URL` | Your Dataverse org URL | `https://ampyrproduction.crm.dynamics.com` |
| `DATAVERSE_API_VERSION` | OData API version | `v9.2` |
| `FINANCE_DB_SERVER` | Azure SQL server FQDN | `myserver.database.windows.net` |
| `FINANCE_DB_NAME` | Finance database name | `FinanceDB` |
| `FINANCE_DB_SCHEMA` | Default schema | `dbo` or `fact` |
| `SSAS_SERVER` | Analysis Services server | `asazure://eastus/myserver` |
| `SSAS_DATABASE` | SSAS database/model name | `FinanceModel` |
