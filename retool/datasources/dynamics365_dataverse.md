# Dynamics 365 Dataverse — Retool Connection Guide

## Overview

Your Dataverse environment (`ampyrproduction`) is accessed via the OData v4 REST API.
All table names in Dataverse use a logical name with a publisher prefix (e.g., `cr123_projects`).

---

## Azure App Registration (one-time setup)

### 1. Register the Application
1. Sign in to **Azure Portal** → **Azure Active Directory → App Registrations → New Registration**
2. Name: `Retool-Dataverse-Connector`
3. Supported account types: **Single tenant**
4. Redirect URI: leave blank for client credentials flow
5. Click **Register**

### 2. Add API Permissions
1. In the app, go to **API Permissions → Add a permission**
2. Select **Dynamics CRM**
3. Check **user_impersonation** (delegated) — or for server-to-server, select **Application permissions**
4. Click **Grant admin consent**

### 3. Create a Client Secret
1. **Certificates & Secrets → New client secret**
2. Set expiry (e.g., 24 months)
3. **Copy the secret value immediately** — it's only shown once

### 4. Note Your IDs
- **Tenant ID**: Azure AD → Overview → Tenant ID
- **Client ID**: App Registration → Overview → Application (client) ID
- **Client Secret**: from step 3 above

### 5. Add as Application User in Dynamics 365
1. Go to **Power Platform Admin Center → Environments → ampyrproduction → Settings → Users + Permissions → Application Users**
2. **New App User → Add an App**
3. Search for `Retool-Dataverse-Connector`
4. Assign a **Security Role** with read access to the required tables (create a custom "Retool Read" role)

---

## Retool Resource Setup

> **Note**: Retool does not have a native Microsoft Dataverse connector. The correct approach is to use Retool's **REST API** resource type, pointing directly at the Dataverse OData endpoint. This is the standard method.

### Step 1: Create a REST API Resource
1. Retool → **Resources → Create New Resource → REST API**
2. Settings:
   ```
   Name:             Dynamics365_CRM
   Base URL:         https://ampyrproduction.crm.dynamics.com/api/data/v9.2
   Authentication:   OAuth 2.0 (Client Credentials flow)
   Token URL:        https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token
   Client ID:        <your-client-id>
   Client Secret:    <your-client-secret>
   Scope:            https://ampyrproduction.crm.dynamics.com/.default
   ```
3. Add default headers (under **Headers** in the resource config):
   ```
   OData-MaxVersion: 4.0
   OData-Version:    4.0
   Accept:           application/json; odata.metadata=minimal
   Prefer:           odata.include-annotations=OData.Community.Display.V1.FormattedValue
   ```
4. Click **Test → Save**

### Step 2: Create Queries in Your App
Each CRM query is a **GET** request on this resource. Example — list active projects:
```
Method: GET
Path:   /cr_projects?$filter=statecode eq 0&$top=1000&$select=cr_name,cr_stage,cr_capacity_kw
```

See the `queries/crm/` folder for full OData parameters for each table.

### Alternative: CData Connect Cloud (no-code middleware)
If OAuth setup is blocked by IT policy, [CData Connect Cloud](https://www.cdata.com/kb/tech/dataverse-cloud-retool.rst) can act as middleware, exposing Dataverse as either an **OpenAPI** resource or a **SQL Server** resource in Retool. This adds a paid dependency but avoids the Azure App Registration.

---

## Discovering Your Table Names

Run this query in Retool (GET request) to list all custom tables:

```
GET /EntityDefinitions?$select=LogicalName,DisplayName,IsCustomEntity
    &$filter=IsCustomEntity eq true
    &$orderby=LogicalName
```

Run this as a GET query on the `Dynamics365_CRM` REST API resource.

Common Dataverse entity set names follow the pattern `{logicalname}s` or custom plurals. To find exact collection names:

```
GET /EntityDefinitions(LogicalName='your_table_name')?$select=EntitySetName
```

---

## Key Table Logical Names to Discover

Update `schemas/dataverse_tables.md` once you've identified your actual table names. Based on a typical solar pipeline & construction CRM, look for tables matching:

| Purpose | Likely Logical Name Pattern |
|---------|----------------------------|
| Projects / Opportunities | `opportunity`, `cr???_project`, `cr???_solarproject` |
| Sites / Installations | `cr???_site`, `cr???_installation`, `account` |
| Construction stages | `cr???_constructionstage`, `cr???_milestone` |
| Contacts / Clients | `contact`, `account` |
| Commissioned assets | `cr???_asset`, `cr???_commissionedasset` |
| Pipeline stages | Standard `opportunity` with custom fields |

To list all entities and find yours:
```
GET /EntityDefinitions?$select=LogicalName,EntitySetName,DisplayName
    &$filter=IsCustomEntity eq true
```

---

## OData Query Patterns

### Basic record fetch
```
GET /{entity_set_name}?$top=100&$select=field1,field2,field3
```

### Filter by status
```
GET /opportunities?$filter=statecode eq 0&$select=name,estimatedvalue,closedate
```

### Expand a lookup field
```
GET /cr123_projects?$expand=cr123_accountid($select=name,telephone1)
    &$select=cr123_name,cr123_startdate,cr123_capacity_kw
```

### Order and paginate
```
GET /cr123_projects?$orderby=createdon desc&$top=500&$skip=0
```

### Count records
```
GET /cr123_projects?$count=true
```

### OData filter operators
```
eq, ne, gt, ge, lt, le, and, or, not, contains(), startswith(), endswith()
```

---

## Handling Formatted Values

Retool queries should include the `Prefer` header to get both raw and display values:

```
Prefer: odata.include-annotations=OData.Community.Display.V1.FormattedValue
```

This returns fields like:
```json
{
  "statecode": 0,
  "statecode@OData.Community.Display.V1.FormattedValue": "Active"
}
```

Use the `_FormattedValue` fields for display in dropdowns/tables.

---

## Retool Query Example — Pipeline Projects

In Retool, create a new query on the `Dynamics365_CRM` resource:

```javascript
// Resource: Dynamics365_CRM (Dataverse connector)
// Action: List records
// Entity: cr???_projects (replace with your actual entity set name)
// Filter: statecode eq 0
// Select: cr???_name, cr???_capacity_kw, cr???_stage, cr???_startdate, cr???_expectedcompletiondate, _cr???_accountid_value
// Top: 1000
// Expand: cr???_accountid($select=name)
```

See `queries/crm/` for full query implementations.
