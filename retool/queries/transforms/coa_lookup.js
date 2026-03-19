/**
 * Transformer: Chart of Accounts Lookup
 *
 * Usage in Retool:
 *   1. Create a transformer named "coaTransformer"
 *   2. Input: getChartOfAccounts.data (from AzureSQL_Finance or Retool DB)
 *   3. Returns lookup functions used by finance report transformers
 *
 * This transformer enriches raw transaction data with COA display names,
 * categories, and P&L groupings.
 */

// Input: array of COA rows from chart_of_accounts.sql
const rows = getChartOfAccounts.data; // Replace with your query name

// ─── BUILD LOOKUP MAPS ────────────────────────────────────────────────────────

// Map: account_code → full COA row
const byCode = {};
for (const row of rows) {
  byCode[row.account_code] = row;
}

// Map: account_category → array of account codes
const byCategory = {};
for (const row of rows) {
  const cat = row.account_category || "Uncategorised";
  if (!byCategory[cat]) byCategory[cat] = [];
  byCategory[cat].push(row.account_code);
}

// Map: pl_line → array of account codes (for P&L subtotal grouping)
const byPLLine = {};
for (const row of rows) {
  const line = row.pl_line || "Other";
  if (!byPLLine[line]) byPLLine[line] = [];
  byPLLine[line].push(row.account_code);
}

// ─── UTILITIES ───────────────────────────────────────────────────────────────

/**
 * Look up display name for an account code
 */
function getAccountName(code) {
  return byCode[code]?.account_name || code;
}

/**
 * Look up category for an account code
 */
function getCategory(code) {
  return byCode[code]?.account_category || "Unknown";
}

/**
 * Look up P&L line for an account code
 */
function getPLLine(code) {
  return byCode[code]?.pl_line || "Other";
}

/**
 * Enrich an array of transaction/actuals rows with COA display fields
 */
function enrichWithCOA(transactionRows) {
  return transactionRows.map(row => ({
    ...row,
    account_name_display:     getAccountName(row.account_code),
    account_category_display: getCategory(row.account_code),
    pl_line_display:          getPLLine(row.account_code),
  }));
}

/**
 * Build dropdown options for account categories
 */
function categoryOptions() {
  return ["", ...Object.keys(byCategory)].map(cat => ({
    label: cat || "All Categories",
    value: cat,
  }));
}

/**
 * Build dropdown options for P&L lines
 */
function plLineOptions() {
  return ["", ...Object.keys(byPLLine)].map(line => ({
    label: line || "All Lines",
    value: line,
  }));
}

/**
 * Group transaction rows by P&L line for a summary table
 */
function groupByPLLine(transactionRows) {
  const groups = {};

  for (const row of transactionRows) {
    const line = getPLLine(row.account_code);
    if (!groups[line]) {
      groups[line] = {
        pl_line:      line,
        actual:       0,
        budget:       0,
        variance:     0,
      };
    }
    groups[line].actual   += row.actual_amount  || row.net_amount || 0;
    groups[line].budget   += row.budget_amount  || 0;
    groups[line].variance += row.variance_amount || 0;
  }

  return Object.values(groups)
    .map(g => ({
      ...g,
      actual:   parseFloat(g.actual.toFixed(2)),
      budget:   parseFloat(g.budget.toFixed(2)),
      variance: parseFloat(g.variance.toFixed(2)),
      variance_pct: g.budget !== 0
        ? parseFloat((g.variance / Math.abs(g.budget) * 100).toFixed(1))
        : null,
    }))
    .sort((a, b) => a.pl_line.localeCompare(b.pl_line));
}

// ─── RETURN ───────────────────────────────────────────────────────────────────
return {
  byCode,
  byCategory,
  byPLLine,
  getAccountName,
  getCategory,
  getPLLine,
  enrichWithCOA,
  categoryOptions,
  plLineOptions,
  groupByPLLine,
};
