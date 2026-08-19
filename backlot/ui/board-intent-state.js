const DRAFT_VERSION = "1.0";
const STORAGE_PREFIX = "backlot.intent-draft.v1";

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, stable(value[key])]),
    );
  }
  return value;
}

function digest(text) {
  let hash = 5381;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) + hash + text.charCodeAt(index)) | 0;
  }
  return `h${(hash >>> 0).toString(36)}`;
}

function storageKey(projectId, stage) {
  return `${STORAGE_PREFIX}:${projectId}:${stage}`;
}

function updatedAt() {
  return new Date().toISOString();
}

export function decisionRevision({
  projectId,
  stage,
  timestamp,
  decision,
}) {
  return digest(JSON.stringify(stable({
    projectId,
    stage,
    timestamp,
    decision,
  })));
}

export function createDraft({ projectId, stage, revision }) {
  return {
    version: DRAFT_VERSION,
    project_id: projectId,
    stage,
    revision,
    selections: [],
    note: "",
    updated_at: updatedAt(),
  };
}

export function selectOption(draft, decisionKey, option) {
  const optionId = option.id ?? option.option_id;
  const selection = {
    decision_key: decisionKey,
    option_id: optionId,
    label_zh: option.label_zh ?? option.label ?? optionId,
  };
  const existingIndex = draft.selections.findIndex(
    (item) => item.decision_key === decisionKey,
  );
  const selections = [...draft.selections];
  if (existingIndex === -1) {
    selections.push(selection);
  } else {
    selections[existingIndex] = selection;
  }

  return {
    ...draft,
    selections,
    updated_at: updatedAt(),
  };
}

export function setDraftNote(draft, note) {
  return {
    ...draft,
    note: String(note ?? ""),
    updated_at: updatedAt(),
  };
}

export function summarizeDraft(draft) {
  const lines = [
    "【Backlot待确认】",
    `项目：${draft.project_id}`,
    `阶段：${draft.stage}`,
    "待确认选择：",
  ];

  if (draft.selections.length === 0) {
    lines.push("（尚未选择）");
  } else {
    draft.selections.forEach((selection, index) => {
      lines.push(
        `${index + 1}. ${selection.label_zh || selection.option_id}`,
      );
    });
  }

  const note = draft.note.trim();
  if (note) lines.push(`备注：${note}`);
  lines.push(
    `点「${draft.stage === "assets_gate" ? "开始出片" : "进入下一步"}」后请留在本页。`,
    "以上选择仍在等待确认，尚未正式执行。",
  );
  return lines.join("\n");
}

export function selectedOptionId(draft, decisionKey) {
  const hit = (draft?.selections || []).find((item) => item.decision_key === decisionKey);
  return hit?.option_id || "";
}

export function gapPlanReady(draft, gapPlan) {
  const currentChoice = (draft?.selections || []).find(
    (item) => String(item.decision_key || "").endsWith("::current")
  );
  if (!currentChoice) return false;
  if (currentChoice.option_id !== "continue") return true;
  const gaps = Array.isArray(gapPlan?.gaps) ? gapPlan.gaps : [];
  if (!gaps.length) return true;
  for (const gap of gaps) {
    const beatId = gap.beat_id;
    const choice = selectedOptionId(draft, `gap::${beatId}`);
    if (!choice) return false;
    if (choice === "i2i") {
      if (!gapPlan.image_key_present) return false;
    }
    if (choice === "reuse" && !selectedOptionId(draft, `gap_reuse::${beatId}`)) {
      return false;
    }
  }
  const needsI2i = gaps.some(
    (gap) => selectedOptionId(draft, `gap::${gap.beat_id}`) === "i2i",
  );
  if (needsI2i && !selectedOptionId(draft, "image_model::project")) {
    const legacy = gaps.some(
      (gap) => selectedOptionId(draft, `gap_model::${gap.beat_id}`),
    );
    if (!legacy) return false;
  }
  return true;
}

export function saveDraft(storage, draft) {
  try {
    storage.setItem(
      storageKey(draft.project_id, draft.stage),
      JSON.stringify(draft),
    );
  } catch {
    // Session-scoped persistence is best-effort.
  }
}

export function inspectStoredDraft(storage, { projectId, stage, revision }) {
  let raw;
  try {
    raw = storage.getItem(storageKey(projectId, stage));
  } catch {
    return { status: "missing", draft: null };
  }
  if (raw === null) return { status: "missing", draft: null };

  try {
    const draft = JSON.parse(raw);
    if (
      !draft
      || typeof draft !== "object"
      || draft.version !== DRAFT_VERSION
      || draft.project_id !== projectId
      || draft.stage !== stage
      || draft.revision !== revision
    ) {
      return { status: "stale", draft: null };
    }
    return { status: "current", draft };
  } catch {
    return { status: "corrupt", draft: null };
  }
}

export function restoreDraft(storage, { projectId, stage, revision }) {
  return inspectStoredDraft(storage, {
    projectId,
    stage,
    revision,
  }).draft;
}

export function clearDraft(storage, { projectId, stage }) {
  try {
    storage.removeItem(storageKey(projectId, stage));
  } catch {
    // Session-scoped persistence is best-effort.
  }
}
