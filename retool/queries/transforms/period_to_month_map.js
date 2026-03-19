/**
 * Transformer: Finance Period → Calendar Month Mapping
 *
 * Usage in Retool:
 *   1. Create a transformer named "periodMapTransformer"
 *   2. If using Retool Database: set input to the finance_period_map query result
 *   3. If using hardcoded: use the static map below
 *
 * This transformer provides two utility functions used by other transformers:
 *   - periodToMonthLabel(fy, period)  → "April 2024"
 *   - periodToDate(fy, period)        → { month: 4, year: 2024, label: "April 2024" }
 *   - buildPeriodOptions(fy)          → dropdown options array
 */

// ─── OPTION A: Loaded from Retool Database query ──────────────────────────────
// If you've run getFinancePeriodMap query (Retool DB), use this:
// const rows = getFinancePeriodMap.data;  // Array of period rows

// ─── OPTION B: Static hardcoded map ──────────────────────────────────────────
// Update this when you add a new financial year.
const PERIOD_MAP = {
  "2023/24": [
    { period: 1,  month: 4,  year: 2023, name: "April",     start: "2023-04-01", end: "2023-04-30" },
    { period: 2,  month: 5,  year: 2023, name: "May",        start: "2023-05-01", end: "2023-05-31" },
    { period: 3,  month: 6,  year: 2023, name: "June",       start: "2023-06-01", end: "2023-06-30" },
    { period: 4,  month: 7,  year: 2023, name: "July",       start: "2023-07-01", end: "2023-07-31" },
    { period: 5,  month: 8,  year: 2023, name: "August",     start: "2023-08-01", end: "2023-08-31" },
    { period: 6,  month: 9,  year: 2023, name: "September",  start: "2023-09-01", end: "2023-09-30" },
    { period: 7,  month: 10, year: 2023, name: "October",    start: "2023-10-01", end: "2023-10-31" },
    { period: 8,  month: 11, year: 2023, name: "November",   start: "2023-11-01", end: "2023-11-30" },
    { period: 9,  month: 12, year: 2023, name: "December",   start: "2023-12-01", end: "2023-12-31" },
    { period: 10, month: 1,  year: 2024, name: "January",    start: "2024-01-01", end: "2024-01-31" },
    { period: 11, month: 2,  year: 2024, name: "February",   start: "2024-02-01", end: "2024-02-29" },
    { period: 12, month: 3,  year: 2024, name: "March",      start: "2024-03-01", end: "2024-03-31" },
  ],
  "2024/25": [
    { period: 1,  month: 4,  year: 2024, name: "April",     start: "2024-04-01", end: "2024-04-30" },
    { period: 2,  month: 5,  year: 2024, name: "May",        start: "2024-05-01", end: "2024-05-31" },
    { period: 3,  month: 6,  year: 2024, name: "June",       start: "2024-06-01", end: "2024-06-30" },
    { period: 4,  month: 7,  year: 2024, name: "July",       start: "2024-07-01", end: "2024-07-31" },
    { period: 5,  month: 8,  year: 2024, name: "August",     start: "2024-08-01", end: "2024-08-31" },
    { period: 6,  month: 9,  year: 2024, name: "September",  start: "2024-09-01", end: "2024-09-30" },
    { period: 7,  month: 10, year: 2024, name: "October",    start: "2024-10-01", end: "2024-10-31" },
    { period: 8,  month: 11, year: 2024, name: "November",   start: "2024-11-01", end: "2024-11-30" },
    { period: 9,  month: 12, year: 2024, name: "December",   start: "2024-12-01", end: "2024-12-31" },
    { period: 10, month: 1,  year: 2025, name: "January",    start: "2025-01-01", end: "2025-01-31" },
    { period: 11, month: 2,  year: 2025, name: "February",   start: "2025-02-01", end: "2025-02-28" },
    { period: 12, month: 3,  year: 2025, name: "March",      start: "2025-03-01", end: "2025-03-31" },
  ],
  "2025/26": [
    { period: 1,  month: 4,  year: 2025, name: "April",     start: "2025-04-01", end: "2025-04-30" },
    { period: 2,  month: 5,  year: 2025, name: "May",        start: "2025-05-01", end: "2025-05-31" },
    { period: 3,  month: 6,  year: 2025, name: "June",       start: "2025-06-01", end: "2025-06-30" },
    { period: 4,  month: 7,  year: 2025, name: "July",       start: "2025-07-01", end: "2025-07-31" },
    { period: 5,  month: 8,  year: 2025, name: "August",     start: "2025-08-01", end: "2025-08-31" },
    { period: 6,  month: 9,  year: 2025, name: "September",  start: "2025-09-01", end: "2025-09-30" },
    { period: 7,  month: 10, year: 2025, name: "October",    start: "2025-10-01", end: "2025-10-31" },
    { period: 8,  month: 11, year: 2025, name: "November",   start: "2025-11-01", end: "2025-11-30" },
    { period: 9,  month: 12, year: 2025, name: "December",   start: "2025-12-01", end: "2025-12-31" },
    { period: 10, month: 1,  year: 2026, name: "January",    start: "2026-01-01", end: "2026-01-31" },
    { period: 11, month: 2,  year: 2026, name: "February",   start: "2026-02-01", end: "2026-02-28" },
    { period: 12, month: 3,  year: 2026, name: "March",      start: "2026-03-01", end: "2026-03-31" },
  ],
};

// ─── UTILITIES ───────────────────────────────────────────────────────────────

/**
 * Get calendar info for a given financial year + period number
 * @param {string} fy   - "2024/25"
 * @param {number} period - 1 to 12
 * @returns {{ month, year, name, label, start, end } | null}
 */
function periodToDate(fy, period) {
  const fyData = PERIOD_MAP[fy];
  if (!fyData) return null;
  const row = fyData.find(r => r.period === period);
  if (!row) return null;
  return {
    ...row,
    label: `${row.name} ${row.year}`,
    shortLabel: `${row.name.slice(0, 3)} ${String(row.year).slice(2)}`,
  };
}

/**
 * Build a dropdown options array for all periods in a financial year
 */
function buildPeriodOptions(fy) {
  const fyData = PERIOD_MAP[fy];
  if (!fyData) return [];
  return fyData.map(r => ({
    label: `P${r.period} — ${r.name} ${r.year}`,
    value: r.period,
  }));
}

/**
 * Build financial year options for the FY selector dropdown
 */
function buildFYOptions() {
  return Object.keys(PERIOD_MAP)
    .sort()
    .reverse()
    .map(fy => ({ label: `FY ${fy}`, value: fy }));
}

/**
 * Given a calendar date string (YYYY-MM-DD), return the period info
 */
function dateToFYPeriod(dateStr, fy) {
  const d = new Date(dateStr);
  const month = d.getMonth() + 1;
  const year  = d.getFullYear();
  const fyData = PERIOD_MAP[fy];
  if (!fyData) return null;
  return fyData.find(r => r.month === month && r.year === year) || null;
}

// ─── RETURN VALUE ─────────────────────────────────────────────────────────────
// This transformer returns the full map + utilities
return {
  map: PERIOD_MAP,
  periodToDate,
  buildPeriodOptions,
  buildFYOptions,
  dateToFYPeriod,
};
