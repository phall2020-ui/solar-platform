/**
 * CRM Query: Commissioned Assets / Asset Register
 * Resource: Dynamics365_CRM
 *
 * Fetches the commissioned solar asset register. These are completed/live
 * sites, as opposed to pipeline projects still under development.
 */

// ─── CONFIG — UPDATE THESE ───────────────────────────────────────────────────
const ENTITY_SET   = "cr_assets";       // your commissioned asset entity
const FIELD_PREFIX = "cr_";

const FIELDS = {
  id:               `${FIELD_PREFIX}assetid`,
  name:             `${FIELD_PREFIX}name`,
  projectLookup:    `_${FIELD_PREFIX}projectid_value`,
  accountLookup:    `_${FIELD_PREFIX}accountid_value`,
  capacityKwp:      `${FIELD_PREFIX}capacity_kwp`,
  capacityKw:       `${FIELD_PREFIX}capacity_kw`,
  commissionDate:   `${FIELD_PREFIX}commissiondate`,
  gridConnectionDate:`${FIELD_PREFIX}gridconnectiondate`,
  location:         `${FIELD_PREFIX}location`,
  latitude:         `${FIELD_PREFIX}latitude`,
  longitude:        `${FIELD_PREFIX}longitude`,
  technologyType:   `${FIELD_PREFIX}technologytype`,
  typeFormatted:    `${FIELD_PREFIX}technologytype@OData.Community.Display.V1.FormattedValue`,
  assetStatus:      `${FIELD_PREFIX}assetstatus`,
  statusFormatted:  `${FIELD_PREFIX}assetstatus@OData.Community.Display.V1.FormattedValue`,
  financeCode:      `${FIELD_PREFIX}financecode`,     // link field to Azure SQL
  inverterPlatform: `${FIELD_PREFIX}inverterplatform`,
  annualYieldKwh:   `${FIELD_PREFIX}annualyield_kwh`,
  notes:            `${FIELD_PREFIX}notes`,
  createdOn:        "createdon",
};

// ─── ODATA QUERY ─────────────────────────────────────────────────────────────
const oDataParams = {
  $filter: `statecode eq 0`,
  $select: [
    FIELDS.id, FIELDS.name, FIELDS.projectLookup, FIELDS.accountLookup,
    FIELDS.capacityKwp, FIELDS.capacityKw, FIELDS.commissionDate,
    FIELDS.gridConnectionDate, FIELDS.location, FIELDS.latitude,
    FIELDS.longitude, FIELDS.technologyType, FIELDS.assetStatus,
    FIELDS.financeCode, FIELDS.inverterPlatform, FIELDS.annualYieldKwh,
    FIELDS.notes, FIELDS.createdOn,
  ].join(","),

  $expand: [
    `${FIELD_PREFIX}projectid($select=${FIELD_PREFIX}name)`,
    `${FIELD_PREFIX}accountid($select=name)`,
  ].join(","),

  $orderby: `${FIELDS.commissionDate} desc`,
  $top: 2000,
};

// ─── RESPONSE TRANSFORMER ─────────────────────────────────────────────────────
function transformAssets(rawData) {
  const records = rawData.value || rawData;

  return records.map(r => ({
    id:               r[FIELDS.id],
    name:             r[FIELDS.name] || "Unnamed Asset",
    projectId:        r[FIELDS.projectLookup],
    projectName:      r[`${FIELD_PREFIX}projectid`]?.[`${FIELD_PREFIX}name`] || "",
    clientId:         r[FIELDS.accountLookup],
    clientName:       r[`${FIELD_PREFIX}accountid`]?.name || "",
    capacityKwp:      parseFloat(r[FIELDS.capacityKwp]) || 0,
    capacityKw:       parseFloat(r[FIELDS.capacityKw])  || 0,
    commissionDate:   r[FIELDS.commissionDate]?.slice(0, 10) || null,
    gridConnDate:     r[FIELDS.gridConnectionDate]?.slice(0, 10) || null,
    location:         r[FIELDS.location] || "",
    lat:              parseFloat(r[FIELDS.latitude])  || null,
    lng:              parseFloat(r[FIELDS.longitude]) || null,
    technology:       r[FIELDS.typeFormatted] || r[FIELDS.technologyType],
    status:           r[FIELDS.statusFormatted] || r[FIELDS.assetStatus],
    financeCode:      r[FIELDS.financeCode] || "",       // used to join to Azure SQL
    inverterPlatform: r[FIELDS.inverterPlatform] || "",
    annualYieldKwh:   parseFloat(r[FIELDS.annualYieldKwh]) || 0,
    notes:            r[FIELDS.notes] || "",
    // Computed
    capacityMwp:      parseFloat(r[FIELDS.capacityKwp]) / 1000 || 0,
  }));
}

// ─── PORTFOLIO SUMMARY ────────────────────────────────────────────────────────
function portfolioSummary(assets) {
  const active = assets.filter(a => a.status?.toLowerCase().includes("active") || a.status === "1");
  return {
    totalAssets:       assets.length,
    activeAssets:      active.length,
    totalCapacityKwp:  assets.reduce((s, a) => s + a.capacityKwp, 0),
    totalCapacityMwp:  assets.reduce((s, a) => s + a.capacityMwp, 0).toFixed(2),
    annualYieldGwh:    (assets.reduce((s, a) => s + a.annualYieldKwh, 0) / 1_000_000).toFixed(2),
    byTechnology:      groupBy(assets, "technology"),
    byClient:          groupBy(assets, "clientName"),
  };
}

function groupBy(arr, key) {
  const result = {};
  for (const item of arr) {
    const k = item[key] || "Unknown";
    result[k] = (result[k] || 0) + 1;
  }
  return Object.entries(result).map(([name, count]) => ({ name, count }));
}
