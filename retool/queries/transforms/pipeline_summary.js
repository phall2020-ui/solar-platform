/**
 * Transformer: Pipeline Summary & Funnel
 *
 * Produces aggregated pipeline metrics for the Pipeline Overview dashboard.
 * Input: crmFinanceJoinTransformer.projects (the joined dataset)
 *
 * In Retool:
 *   - Create a transformer named "pipelineSummaryTransformer"
 *   - Depends on: crmFinanceJoinTransformer
 */

// Input from the join transformer
const projects = crmFinanceJoinTransformer.projects || [];

// ─── PIPELINE FUNNEL ──────────────────────────────────────────────────────────
// Groups projects by stage with counts and cumulative value.
// Stage order is inferred alphabetically; update STAGE_ORDER to match your CRM.

const STAGE_ORDER = [
  "Lead",
  "Prospect",
  "Qualified",
  "Proposal",
  "Negotiation",
  "Contracted",
  "Under Construction",
  "Commissioned",
  "Complete",
];

function stageIndex(stageName) {
  const idx = STAGE_ORDER.findIndex(s =>
    stageName?.toLowerCase().includes(s.toLowerCase())
  );
  return idx >= 0 ? idx : STAGE_ORDER.length;
}

const stageMap = {};
for (const p of projects) {
  const stage = p.stage || "Unknown";
  if (!stageMap[stage]) {
    stageMap[stage] = {
      stage,
      order:          stageIndex(stage),
      count:          0,
      totalCapKw:     0,
      totalCapMw:     0,
      totalValue:     0,
      totalRevenue:   0,
      redCount:       0,
      amberCount:     0,
      greenCount:     0,
    };
  }
  stageMap[stage].count++;
  stageMap[stage].totalCapKw   += p.capacityKw    || 0;
  stageMap[stage].totalCapMw    = parseFloat((stageMap[stage].totalCapKw / 1000).toFixed(2));
  stageMap[stage].totalValue   += p.contractValue || 0;
  stageMap[stage].totalRevenue += p.revenue       || 0;
  if (p.marginRag === "RED")   stageMap[stage].redCount++;
  if (p.marginRag === "AMBER") stageMap[stage].amberCount++;
  if (p.marginRag === "GREEN") stageMap[stage].greenCount++;
}

const funnel = Object.values(stageMap)
  .sort((a, b) => a.order - b.order)
  .map(s => ({
    ...s,
    avgValuePerProject: s.count > 0 ? Math.round(s.totalValue / s.count) : 0,
  }));

// ─── KPI TILES ────────────────────────────────────────────────────────────────
const activeStages  = ["Lead","Prospect","Qualified","Proposal","Negotiation","Contracted"];
const buildStages   = ["Under Construction"];
const liveStages    = ["Commissioned","Complete"];

function inStages(p, stageList) {
  return stageList.some(s => p.stage?.toLowerCase().includes(s.toLowerCase()));
}

const kpis = {
  // Pipeline
  pipelineCount:        projects.filter(p => inStages(p, activeStages)).length,
  pipelineValueTotal:   projects.filter(p => inStages(p, activeStages))
                          .reduce((s, p) => s + (p.contractValue || 0), 0),
  pipelineCapacityMw:   parseFloat(
    (projects.filter(p => inStages(p, activeStages))
      .reduce((s, p) => s + (p.capacityKw || 0), 0) / 1000).toFixed(2)
  ),

  // Under construction
  underConstructionCount: projects.filter(p => inStages(p, buildStages)).length,
  underConstructionMw:    parseFloat(
    (projects.filter(p => inStages(p, buildStages))
      .reduce((s, p) => s + (p.capacityKw || 0), 0) / 1000).toFixed(2)
  ),

  // Live / commissioned
  liveCount:            projects.filter(p => inStages(p, liveStages)).length,
  liveMw:               parseFloat(
    (projects.filter(p => inStages(p, liveStages))
      .reduce((s, p) => s + (p.capacityKw || 0), 0) / 1000).toFixed(2)
  ),

  // Finance health (projects with finance data)
  linkedCount:          projects.filter(p => p.isLinked).length,
  greenMargin:          projects.filter(p => p.marginRag === "GREEN").length,
  amberMargin:          projects.filter(p => p.marginRag === "AMBER").length,
  redMargin:            projects.filter(p => p.marginRag === "RED").length,

  // Totals
  totalProjects:        projects.length,
  totalContractedMw:    parseFloat(
    (projects.reduce((s, p) => s + (p.capacityKw || 0), 0) / 1000).toFixed(2)
  ),
};

// ─── CHART DATA: Monthly close forecasts ──────────────────────────────────────
// Groups expected completion by month (for a bar/line chart)
const closingByMonth = {};
for (const p of projects) {
  if (!p.expectedEnd) continue;
  const monthKey = p.expectedEnd.slice(0, 7); // "YYYY-MM"
  if (!closingByMonth[monthKey]) {
    closingByMonth[monthKey] = { month: monthKey, count: 0, value: 0, capacityKw: 0 };
  }
  closingByMonth[monthKey].count++;
  closingByMonth[monthKey].value      += p.contractValue || 0;
  closingByMonth[monthKey].capacityKw += p.capacityKw    || 0;
}

const closingForecast = Object.values(closingByMonth)
  .sort((a, b) => a.month.localeCompare(b.month));

// ─── RETURN ───────────────────────────────────────────────────────────────────
return {
  funnel,
  kpis,
  closingForecast,
};
