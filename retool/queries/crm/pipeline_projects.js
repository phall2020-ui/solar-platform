/**
 * CRM Query: Pipeline Projects
 * Resource: Dynamics365_CRM
 *
 * Fetches all active pipeline opportunities/projects with stage, value, and dates.
 * Uses OData v4 against the Dataverse API.
 *
 * SETUP REQUIRED:
 * Replace the placeholder entity set name (cr_projects) and field names
 * with your actual Dataverse logical names. Run the entity discovery query
 * in datasources/dynamics365_dataverse.md to find them.
 *
 * In the Retool Dataverse connector query editor:
 *   - Action: List records
 *   - Entity: [your entity set name]
 *   - Paste the $filter, $select, $expand, $orderby values from below
 *
 * If using REST API resource, the full URL path is shown in the URL section.
 */

// ─── CONFIG — UPDATE THESE ───────────────────────────────────────────────────
const ENTITY_SET   = "cr_projects";          // e.g. "cr123_solarprojectses"
const FIELD_PREFIX = "cr_";                  // your publisher prefix

// Field names — update to match your Dataverse schema
const FIELDS = {
  id:                   `${FIELD_PREFIX}projectid`,
  name:                 `${FIELD_PREFIX}name`,
  stage:                `${FIELD_PREFIX}stage`,
  stageFormatted:       `${FIELD_PREFIX}stage@OData.Community.Display.V1.FormattedValue`,
  capacityKw:           `${FIELD_PREFIX}capacity_kw`,
  contractValue:        `${FIELD_PREFIX}contractvalue`,
  expectedStartDate:    `${FIELD_PREFIX}expectedstartdate`,
  expectedCompletion:   `${FIELD_PREFIX}expectedcompletiondate`,
  actualCompletion:     `${FIELD_PREFIX}actualcompletiondate`,
  accountLookup:        `_${FIELD_PREFIX}accountid_value`,
  ownerLookup:          `_ownerid_value`,
  statusCode:           "statecode",
  createdOn:            "createdon",
  modifiedOn:           "modifiedon",
};

// ─── ODATA QUERY PARAMETERS ──────────────────────────────────────────────────
// Use these values in the Dataverse connector query builder:

const oDataParams = {

  // Only active records
  $filter: `statecode eq 0`,

  // Fields to return (comma-separated, no spaces)
  $select: [
    FIELDS.id,
    FIELDS.name,
    FIELDS.stage,
    FIELDS.capacityKw,
    FIELDS.contractValue,
    FIELDS.expectedStartDate,
    FIELDS.expectedCompletion,
    FIELDS.actualCompletion,
    FIELDS.accountLookup,
    FIELDS.statusCode,
    FIELDS.createdOn,
    FIELDS.modifiedOn,
  ].join(","),

  // Expand related account record
  $expand: `${FIELD_PREFIX}accountid($select=name,telephone1,emailaddress1)`,

  // Newest first
  $orderby: `${FIELDS.createdOn} desc`,

  // Page size — Dataverse max is 5000, default is 5000
  $top: 1000,
};

// ─── FULL REST URL (for REST API resource) ───────────────────────────────────
// Path: /{ENTITY_SET}
// Full query string:
const queryString = Object.entries(oDataParams)
  .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
  .join("&");

const fullUrl = `/api/data/v9.2/${ENTITY_SET}?${queryString}`;

// ─── RESPONSE TRANSFORMER ─────────────────────────────────────────────────────
// Paste this into a Retool transformer after the query runs.
// Input: query1.data (the raw OData response)

function transformPipelineProjects(rawData) {
  const records = rawData.value || rawData;

  return records.map(r => ({
    id:                r[FIELDS.id],
    name:              r[FIELDS.name] || "Unnamed",
    stage:             r[FIELDS.stageFormatted] || r[FIELDS.stage],
    stageRaw:          r[FIELDS.stage],
    capacityKw:        parseFloat(r[FIELDS.capacityKw]) || 0,
    contractValue:     parseFloat(r[FIELDS.contractValue]) || 0,
    expectedStart:     r[FIELDS.expectedStartDate]?.slice(0, 10) || null,
    expectedEnd:       r[FIELDS.expectedCompletion]?.slice(0, 10) || null,
    actualEnd:         r[FIELDS.actualCompletion]?.slice(0, 10) || null,
    clientName:        r[`${FIELD_PREFIX}accountid`]?.name || "",
    clientPhone:       r[`${FIELD_PREFIX}accountid`]?.telephone1 || "",
    status:            r[FIELDS.statusCode] === 0 ? "Active" : "Inactive",
    createdOn:         r[FIELDS.createdOn]?.slice(0, 10) || null,
    modifiedOn:        r[FIELDS.modifiedOn]?.slice(0, 10) || null,
  }));
}

// ─── PIPELINE SUMMARY AGGREGATION ─────────────────────────────────────────────
// After transforming, use this to group by stage for the pipeline funnel chart:

function pipelineSummaryByStage(projects) {
  const stageMap = {};
  for (const p of projects) {
    if (!stageMap[p.stage]) {
      stageMap[p.stage] = { stage: p.stage, count: 0, totalCapacityKw: 0, totalValue: 0 };
    }
    stageMap[p.stage].count++;
    stageMap[p.stage].totalCapacityKw += p.capacityKw;
    stageMap[p.stage].totalValue      += p.contractValue;
  }
  return Object.values(stageMap).sort((a, b) => a.stage - b.stage);
}
