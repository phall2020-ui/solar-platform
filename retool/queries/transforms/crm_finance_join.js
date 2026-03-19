/**
 * Transformer: CRM ↔ Finance Cross-Source Join
 *
 * This is the key transformer that links CRM pipeline/project data with
 * Azure SQL finance data to produce project-level P&L views.
 *
 * Data flow:
 *   1. getPipelineProjects   (Dynamics365_CRM)  → CRM project list
 *   2. getRevenueByProject   (AzureSQL_Finance)  → Finance summary per project code
 *   3. getProjectFinanceLink (Retool Database)   → CRM GUID → Finance project code map
 *   4. THIS TRANSFORMER → Joined enriched dataset
 *
 * In Retool:
 *   - Create a transformer named "crmFinanceJoinTransformer"
 *   - Run it after all three source queries complete
 */

// ─── INPUTS (replace with your actual Retool query names) ────────────────────
const crmProjects   = getPipelineProjects.data?.value  || getPipelineProjects.data  || [];
const financeData   = getRevenueByProject.data          || [];
const linkTable     = getProjectFinanceLink.data         || [];

// ─── BUILD LOOKUP: financeCode → finance row ──────────────────────────────────
const financeByCode = {};
for (const row of financeData) {
  financeByCode[row.project_code] = row;
}

// ─── BUILD LOOKUP: crmProjectId → financeCode (from link table) ──────────────
const linkByCrmId = {};
for (const link of linkTable) {
  linkByCrmId[link.crm_project_id] = link.finance_project_code;
}

// ─── JOIN ─────────────────────────────────────────────────────────────────────
const joined = crmProjects.map(crm => {
  // Get the finance project code for this CRM project
  const financeCode = crm.financeCode               // direct field on asset
                   || linkByCrmId[crm.id]           // from link table
                   || null;

  const fin = financeCode ? financeByCode[financeCode] : null;

  return {
    // ── CRM fields
    crmId:            crm.id,
    crmName:          crm.name,
    stage:            crm.stage,
    stageRaw:         crm.stageRaw,
    capacityKw:       crm.capacityKw,
    contractValue:    crm.contractValue,
    clientName:       crm.clientName,
    expectedStart:    crm.expectedStart,
    expectedEnd:      crm.expectedEnd,
    actualEnd:        crm.actualEnd,
    status:           crm.status,

    // ── Finance fields (null if no link exists)
    financeCode:      financeCode,
    financeProject:   fin?.project_name     || null,
    revenue:          fin?.revenue          || 0,
    directCosts:      fin?.direct_costs     || 0,
    overheads:        fin?.overheads        || 0,
    grossProfit:      fin?.gross_profit     || 0,
    marginPct:        fin?.margin_pct       || null,

    // ── Derived / computed
    hasFinanceData:   !!fin,
    isLinked:         !!financeCode,

    // Contract vs actual revenue variance
    contractVsRevenue: crm.contractValue && fin?.revenue
      ? parseFloat((fin.revenue - crm.contractValue).toFixed(2))
      : null,

    contractVsRevenuePct: crm.contractValue && fin?.revenue && crm.contractValue !== 0
      ? parseFloat(((fin.revenue - crm.contractValue) / Math.abs(crm.contractValue) * 100).toFixed(1))
      : null,

    // RAG based on margin
    marginRag: fin?.margin_pct == null   ? "GREY"
             : fin.margin_pct >= 15      ? "GREEN"
             : fin.margin_pct >= 5       ? "AMBER"
             :                             "RED",
  };
});

// ─── SUMMARY STATS ────────────────────────────────────────────────────────────
const summary = {
  totalProjects:       joined.length,
  linkedToFinance:     joined.filter(p => p.isLinked).length,
  notLinked:           joined.filter(p => !p.isLinked).length,
  totalContractValue:  joined.reduce((s, p) => s + (p.contractValue || 0), 0),
  totalRevenue:        joined.reduce((s, p) => s + (p.revenue || 0), 0),
  totalGrossProfit:    joined.reduce((s, p) => s + (p.grossProfit || 0), 0),
  avgMarginPct: (() => {
    const withMargin = joined.filter(p => p.marginPct != null);
    if (!withMargin.length) return null;
    return parseFloat(
      (withMargin.reduce((s, p) => s + p.marginPct, 0) / withMargin.length).toFixed(1)
    );
  })(),
  totalCapacityMw:     parseFloat((joined.reduce((s, p) => s + (p.capacityKw || 0), 0) / 1000).toFixed(2)),
};

// ─── BY-STAGE SUMMARY ─────────────────────────────────────────────────────────
const byStage = {};
for (const p of joined) {
  const stage = p.stage || "Unknown";
  if (!byStage[stage]) {
    byStage[stage] = {
      stage,
      count: 0,
      totalCapacityKw: 0,
      totalContractValue: 0,
      totalRevenue: 0,
    };
  }
  byStage[stage].count++;
  byStage[stage].totalCapacityKw    += p.capacityKw    || 0;
  byStage[stage].totalContractValue += p.contractValue || 0;
  byStage[stage].totalRevenue       += p.revenue       || 0;
}
const byStageArray = Object.values(byStage);

// ─── RETURN ───────────────────────────────────────────────────────────────────
return {
  projects: joined,
  summary,
  byStage: byStageArray,
};
