/**
 * CRM Query: Accounts / Clients
 * Resource: Dynamics365_CRM
 *
 * Fetches client/organisation accounts. Used to populate dropdowns and
 * for linking projects to clients in combined views.
 */

// ─── CONFIG — UPDATE THESE ───────────────────────────────────────────────────
// Accounts uses the standard Dataverse entity — no prefix needed for core fields
const ENTITY_SET = "accounts";

const FIELDS = {
  id:           "accountid",
  name:         "name",
  phone:        "telephone1",
  email:        "emailaddress1",
  website:      "websiteurl",
  address1:     "address1_line1",
  city:         "address1_city",
  postcode:     "address1_postalcode",
  accountType:  "customertypecode",
  typeFormatted:"customertypecode@OData.Community.Display.V1.FormattedValue",
  status:       "statecode",
  createdOn:    "createdon",
};

// ─── ODATA QUERY ─────────────────────────────────────────────────────────────
const oDataParams = {
  $filter: `statecode eq 0`,
  $select: Object.values(FIELDS).filter(f => !f.includes("@")).join(","),
  $orderby: "name asc",
  $top: 500,
};

// ─── RESPONSE TRANSFORMER ─────────────────────────────────────────────────────
function transformAccounts(rawData) {
  const records = rawData.value || rawData;

  return records.map(r => ({
    id:          r[FIELDS.id],
    name:        r[FIELDS.name] || "Unknown",
    phone:       r[FIELDS.phone] || "",
    email:       r[FIELDS.email] || "",
    city:        r[FIELDS.city] || "",
    postcode:    r[FIELDS.postcode] || "",
    accountType: r[FIELDS.typeFormatted] || r[FIELDS.accountType],
    // Display label for dropdowns
    label:       r[FIELDS.name],
    value:       r[FIELDS.id],
  }));
}
