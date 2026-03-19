# Dataverse Tables — Schema Reference

## How to Populate This File

Run the following OData queries in Retool (against your Dynamics365_CRM resource) to discover your actual table and field names. Then replace the placeholder names below.

### Discover custom entities
```
GET /EntityDefinitions?$select=LogicalName,EntitySetName,DisplayName,IsCustomEntity
    &$filter=IsCustomEntity eq true
    &$orderby=LogicalName
```

### Get fields for a specific entity
```
GET /EntityDefinitions(LogicalName='your_entity_name')/Attributes
    ?$select=LogicalName,DisplayName,AttributeType
    &$orderby=LogicalName
```

---

## Table 1: Projects (Pipeline & Construction)

**Entity Set Name**: `cr_???_set` — *update after discovery*
**Display Name**: Projects (or your custom name)
**Purpose**: Core pipeline and construction records — one row per solar project.

| Field (LogicalName) | Type | Description | Notes |
|--------------------|----- |-------------|-------|
| `cr_projectid`     | UniqueIdentifier | Primary key | Auto-generated GUID |
| `cr_name`          | String | Project name | |
| `cr_stage`         | OptionSet | Pipeline stage | See stage values below |
| `cr_capacity_kw`   | Decimal | Installed/planned capacity (kW) | |
| `cr_capacity_kwp`  | Decimal | Peak DC capacity (kWp) | |
| `cr_contractvalue` | Money | Contract value (£) | |
| `cr_expectedstartdate` | DateTime | Expected construction start | |
| `cr_expectedcompletiondate` | DateTime | Expected completion | |
| `cr_actualcompletiondate` | DateTime | Actual completion | |
| `_cr_accountid_value` | Lookup | Client/account GUID | FK to accounts entity |
| `_ownerid_value`  | Lookup | CRM owner/user | |
| `cr_financecode`  | String | Finance project code | Links to Azure SQL |
| `cr_location`     | String | Site address | |
| `cr_latitude`     | Decimal | Site latitude | |
| `cr_longitude`    | Decimal | Site longitude | |
| `cr_inverterplatform` | OptionSet | Inverter monitoring platform | |
| `cr_notes`        | Memo | Free text notes | |
| `statecode`       | State | 0=Active, 1=Inactive | Standard Dataverse field |
| `createdon`       | DateTime | Record created date | Standard field |
| `modifiedon`      | DateTime | Last modified | Standard field |

### Stage Option Set Values
*Update with your actual option set integer values:*

| Value | Label |
|-------|-------|
| 1 | Lead |
| 2 | Prospect |
| 3 | Qualified |
| 4 | Proposal Sent |
| 5 | Contracted |
| 6 | Under Construction |
| 7 | Commissioned |
| 8 | Complete |

---

## Table 2: Construction Stages / Milestones

**Entity Set Name**: `cr_???` — *update after discovery*
**Purpose**: Individual build milestones per project (one-to-many with Projects).

| Field (LogicalName) | Type | Description |
|--------------------|----- |-------------|
| `cr_constructionstageid` | UniqueIdentifier | Primary key |
| `cr_name`          | String | Stage name / description |
| `_cr_projectid_value` | Lookup | Parent project GUID |
| `cr_stagename`     | String | Display name (e.g. "Planning", "Grid Connection") |
| `cr_stageorder`    | Integer | Sort order for Gantt |
| `cr_plannedstartdate` | DateTime | Planned start |
| `cr_plannedenddate` | DateTime | Planned end |
| `cr_actualstartdate` | DateTime | Actual start |
| `cr_actualenddate` | DateTime | Actual end |
| `cr_completionpercentage` | Decimal | 0–100 |
| `cr_status`        | OptionSet | Stage status |
| `cr_notes`         | Memo | Notes |
| `statecode`        | State | 0=Active |

---

## Table 3: Accounts / Clients

**Entity Set Name**: `accounts` (standard Dataverse entity)
**Purpose**: Client organisations, landowners, investors.

| Field (LogicalName) | Type | Description |
|--------------------|----- |-------------|
| `accountid`        | UniqueIdentifier | Primary key |
| `name`             | String | Organisation name |
| `telephone1`       | String | Primary phone |
| `emailaddress1`    | String | Primary email |
| `websiteurl`       | String | Website |
| `address1_line1`   | String | Address line 1 |
| `address1_city`    | String | City |
| `address1_postalcode` | String | Postcode |
| `customertypecode` | OptionSet | Customer type |
| `statecode`        | State | 0=Active |

---

## Table 4: Commissioned Assets

**Entity Set Name**: `cr_???` — *update after discovery*
**Purpose**: Live/commissioned solar installations. Distinct from pipeline projects.

| Field (LogicalName) | Type | Description |
|--------------------|----- |-------------|
| `cr_assetid`       | UniqueIdentifier | Primary key |
| `cr_name`          | String | Asset name |
| `_cr_projectid_value` | Lookup | Source project GUID |
| `_cr_accountid_value` | Lookup | Client GUID |
| `cr_capacity_kwp`  | Decimal | DC peak capacity (kWp) |
| `cr_capacity_kw`   | Decimal | AC capacity (kW) |
| `cr_commissiondate` | DateTime | Commission date |
| `cr_gridconnectiondate` | DateTime | Grid connection date |
| `cr_location`      | String | Site address |
| `cr_latitude`      | Decimal | Latitude |
| `cr_longitude`     | Decimal | Longitude |
| `cr_technologytype` | OptionSet | PV / Wind / BESS etc. |
| `cr_assetstatus`   | OptionSet | Active / Inactive / Decommissioned |
| `cr_financecode`   | String | **Finance system project code** — key link field |
| `cr_inverterplatform` | String | SolarEdge / Solis / Huawei etc. |
| `cr_annualyield_kwh` | Decimal | Expected annual generation (kWh) |
| `cr_notes`         | Memo | Notes |
| `statecode`        | State | 0=Active |

---

## Table 5: Contacts

**Entity Set Name**: `contacts` (standard Dataverse entity)
**Purpose**: Individual contacts at client organisations.

| Field (LogicalName) | Type | Description |
|--------------------|----- |-------------|
| `contactid`        | UniqueIdentifier | Primary key |
| `fullname`         | String | Full name |
| `emailaddress1`    | String | Email |
| `telephone1`       | String | Phone |
| `_parentcustomerid_value` | Lookup | Parent account |
| `jobtitle`         | String | Job title |
| `statecode`        | State | 0=Active |

---

## Table 6: [Your 6th Custom Table]

**Entity Set Name**: — *to be discovered*
**Purpose**: — *describe here*

---

## Key Relationships

```
accounts (1) ──────────────────────────────── (M) projects
                                                        │
projects (1) ─────────────── (M) construction_stages   │
                                                        │
projects (1) ──── (1) assets                           │
                        │                               │
                        └─── finance_code ─── Azure SQL project dimension
```

---

## OData Relationship Navigation

To traverse relationships in a single OData call, use `$expand`:

```
# Get projects with their parent account and child construction stages
GET /cr_projects
    ?$expand=cr_accountid($select=name),cr_constructionstages
    &$select=cr_name,cr_stage,cr_capacity_kw
```

Note: Deep nesting (expand within expand) is supported in Dataverse OData v4.
