/**
 * CRM Query: Construction Stages / Milestones
 * Resource: Dynamics365_CRM
 *
 * Fetches construction stage records linked to projects. This shows
 * the progress of active builds across milestones.
 *
 * SETUP REQUIRED: Replace entity set name and field names with your actual
 * Dataverse logical names.
 */

// ─── CONFIG — UPDATE THESE ───────────────────────────────────────────────────
const ENTITY_SET   = "cr_constructionstages";  // your construction stage entity
const FIELD_PREFIX = "cr_";

const FIELDS = {
  id:                `${FIELD_PREFIX}constructionstageid`,
  name:              `${FIELD_PREFIX}name`,
  projectLookup:     `_${FIELD_PREFIX}projectid_value`,
  stageName:         `${FIELD_PREFIX}stagename`,
  stageOrder:        `${FIELD_PREFIX}stageorder`,
  plannedStart:      `${FIELD_PREFIX}plannedstartdate`,
  plannedEnd:        `${FIELD_PREFIX}plannedenddate`,
  actualStart:       `${FIELD_PREFIX}actualstartdate`,
  actualEnd:         `${FIELD_PREFIX}actualenddate`,
  completionPct:     `${FIELD_PREFIX}completionpercentage`,
  statusCode:        `${FIELD_PREFIX}status`,
  statusFormatted:   `${FIELD_PREFIX}status@OData.Community.Display.V1.FormattedValue`,
  notes:             `${FIELD_PREFIX}notes`,
};

// ─── ODATA QUERY PARAMETERS ──────────────────────────────────────────────────
const oDataParams = {
  // Only stages belonging to active projects (adjust if your schema differs)
  $filter: `statecode eq 0`,

  $select: [
    FIELDS.id,
    FIELDS.name,
    FIELDS.projectLookup,
    FIELDS.stageName,
    FIELDS.stageOrder,
    FIELDS.plannedStart,
    FIELDS.plannedEnd,
    FIELDS.actualStart,
    FIELDS.actualEnd,
    FIELDS.completionPct,
    FIELDS.statusCode,
    FIELDS.notes,
  ].join(","),

  // Expand parent project
  $expand: `${FIELD_PREFIX}projectid($select=${FIELD_PREFIX}name,${FIELD_PREFIX}capacity_kw)`,

  $orderby: `${FIELDS.projectLookup},${FIELDS.stageOrder}`,
  $top: 2000,
};

// ─── RESPONSE TRANSFORMER ─────────────────────────────────────────────────────
function transformConstructionStages(rawData) {
  const records = rawData.value || rawData;

  return records.map(r => ({
    id:             r[FIELDS.id],
    stageName:      r[FIELDS.stageName] || r[FIELDS.name],
    stageOrder:     r[FIELDS.stageOrder] || 0,
    projectId:      r[FIELDS.projectLookup],
    projectName:    r[`${FIELD_PREFIX}projectid`]?.[`${FIELD_PREFIX}name`] || "",
    projectCapKw:   r[`${FIELD_PREFIX}projectid`]?.[`${FIELD_PREFIX}capacity_kw`] || 0,
    plannedStart:   r[FIELDS.plannedStart]?.slice(0, 10) || null,
    plannedEnd:     r[FIELDS.plannedEnd]?.slice(0, 10) || null,
    actualStart:    r[FIELDS.actualStart]?.slice(0, 10) || null,
    actualEnd:      r[FIELDS.actualEnd]?.slice(0, 10) || null,
    completionPct:  parseFloat(r[FIELDS.completionPct]) || 0,
    status:         r[FIELDS.statusFormatted] || r[FIELDS.statusCode],
    notes:          r[FIELDS.notes] || "",
    isComplete:     parseFloat(r[FIELDS.completionPct]) >= 100,
    isOverdue: (
      r[FIELDS.plannedEnd] &&
      !r[FIELDS.actualEnd] &&
      new Date(r[FIELDS.plannedEnd]) < new Date()
    ),
  }));
}

// ─── GROUP STAGES BY PROJECT (for Gantt/timeline display) ─────────────────────
function groupStagesByProject(stages) {
  const projects = {};

  for (const stage of stages) {
    if (!projects[stage.projectId]) {
      projects[stage.projectId] = {
        projectId:   stage.projectId,
        projectName: stage.projectName,
        projectCapKw: stage.projectCapKw,
        stages:      [],
        overallPct:  0,
      };
    }
    projects[stage.projectId].stages.push(stage);
  }

  // Calculate overall completion per project
  for (const proj of Object.values(projects)) {
    const total = proj.stages.reduce((sum, s) => sum + s.completionPct, 0);
    proj.overallPct = proj.stages.length > 0
      ? Math.round(total / proj.stages.length)
      : 0;
    proj.stagesComplete = proj.stages.filter(s => s.isComplete).length;
    proj.stagesOverdue  = proj.stages.filter(s => s.isOverdue).length;
    proj.stages.sort((a, b) => a.stageOrder - b.stageOrder);
  }

  return Object.values(projects);
}

// ─── GANTT DATA FORMAT (for Retool Gantt/Timeline component) ─────────────────
function toGanttFormat(stages) {
  return stages.map(s => ({
    id:       s.id,
    group:    s.projectName,
    title:    s.stageName,
    start:    s.actualStart || s.plannedStart,
    end:      s.actualEnd   || s.plannedEnd,
    progress: s.completionPct,
    color:    s.isComplete ? "#22c55e"
            : s.isOverdue  ? "#ef4444"
            :                "#3b82f6",
  }));
}
