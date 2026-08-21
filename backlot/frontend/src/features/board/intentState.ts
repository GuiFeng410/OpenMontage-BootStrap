import type { CommercialDecision, DecisionOption, GapPlan } from "./types";

export const DRAFT_VERSION = "1.0";
const STORAGE_PREFIX = "backlot.intent-draft.v1";

export type IntentDraft = {
  version: string;
  project_id: string;
  stage: string;
  revision: string;
  selections: { decision_key: string; option_id: string; label_zh: string }[];
  note: string;
  updated_at: string;
};

export type DraftStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

function stable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value as Record<string, unknown>)
        .sort()
        .map((key) => [key, stable((value as Record<string, unknown>)[key])]),
    );
  }
  return value;
}

function digest(text: string) {
  let hash = 5381;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) + hash + text.charCodeAt(index)) | 0;
  }
  return `h${(hash >>> 0).toString(36)}`;
}

function storageKey(projectId: string, stage: string) {
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
}: {
  projectId: string;
  stage: string;
  timestamp?: string;
  decision: unknown;
}) {
  return digest(
    JSON.stringify(
      stable({
        projectId,
        stage,
        timestamp,
        decision,
      }),
    ),
  );
}

export function decisionFingerprint(decision?: CommercialDecision | null) {
  /** Stable subset only — full decision JSON churns on each poll and freezes the panel. */
  const gap = decision?.gap_plan;
  return {
    title_zh: decision?.title_zh || "",
    prompt_zh: decision?.prompt_zh || "",
    options: (Array.isArray(decision?.options) ? decision!.options : []).map((item) =>
      String(item.id ?? item.option_id ?? ""),
    ),
    gap: gap
      ? {
          enough: Boolean(gap.enough),
          locked: Boolean(gap.locked),
          image_key_present: Boolean(gap.image_key_present),
          default_image_model: gap.default_image_model || "",
          covered: (Array.isArray(gap.covered) ? gap.covered : []).map((item) =>
            String(item.beat_id || ""),
          ),
          gaps: (Array.isArray(gap.gaps) ? gap.gaps : []).map((item) => String(item.beat_id || "")),
          reuse_paths: Array.isArray(gap.reuse_paths) ? [...gap.reuse_paths].sort() : [],
          image_models: (Array.isArray(gap.image_models) ? gap.image_models : []).map((item) =>
            String(item.id || ""),
          ),
        }
      : null,
  };
}

export function revisionForDecision({
  projectId,
  stage,
  decision,
}: {
  projectId: string;
  stage: string;
  decision?: CommercialDecision | null;
}) {
  return decisionRevision({
    projectId,
    stage,
    decision: decisionFingerprint(decision),
  });
}

export function createDraft({
  projectId,
  stage,
  revision,
}: {
  projectId: string;
  stage: string;
  revision: string;
}): IntentDraft {
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

export function selectOption(draft: IntentDraft, decisionKey: string, option: DecisionOption): IntentDraft {
  const optionId = String(option.id ?? option.option_id ?? "");
  const selection = {
    decision_key: decisionKey,
    option_id: optionId,
    label_zh: String(option.label_zh ?? option.label ?? optionId),
  };
  const existingIndex = draft.selections.findIndex((item) => item.decision_key === decisionKey);
  const selections = [...draft.selections];
  if (existingIndex === -1) selections.push(selection);
  else selections[existingIndex] = selection;
  return { ...draft, selections, updated_at: updatedAt() };
}

export function setDraftNote(draft: IntentDraft, note: string): IntentDraft {
  return { ...draft, note: String(note ?? ""), updated_at: updatedAt() };
}

export function summarizeDraft(draft: IntentDraft) {
  const lines = ["【Backlot待确认】", `项目：${draft.project_id}`, `阶段：${draft.stage}`, "待确认选择："];
  if (draft.selections.length === 0) {
    lines.push("（尚未选择）");
  } else {
    draft.selections.forEach((selection, index) => {
      lines.push(`${index + 1}. ${selection.label_zh || selection.option_id}`);
    });
  }
  const note = draft.note.trim();
  if (note) lines.push(`备注：${note}`);
  const current = selectedOptionId(draft, `${draft.stage}::current`);
  const clickLabel =
    current === "generate"
      ? "开始生成补图"
      : draft.stage === "assets_gate"
        ? "开始出片"
        : "进入下一步";
  lines.push(`点「${clickLabel}」后请留在本页。`, "以上选择仍在等待确认，尚未正式执行。");
  return lines.join("\n");
}

export function selectedOptionId(draft: IntentDraft | null | undefined, decisionKey: string) {
  const hit = (draft?.selections || []).find((item) => item.decision_key === decisionKey);
  return hit?.option_id || "";
}

export function gapPlanReady(draft: IntentDraft, gapPlan?: GapPlan | null) {
  const currentChoice = (draft?.selections || []).find((item) =>
    String(item.decision_key || "").endsWith("::current"),
  );
  if (!currentChoice) return false;
  if (currentChoice.option_id !== "continue") return true;
  const gaps = Array.isArray(gapPlan?.gaps) ? gapPlan.gaps : [];
  if (!gaps.length) return true;
  for (const gap of gaps) {
    const beatId = gap.beat_id;
    const choice = selectedOptionId(draft, `gap::${beatId}`);
    if (!choice) return false;
    if (choice === "i2i" && !gapPlan?.image_key_present) return false;
    if (choice === "reuse" && !selectedOptionId(draft, `gap_reuse::${beatId}`)) return false;
  }
  const needsI2i = gaps.some((gap) => selectedOptionId(draft, `gap::${gap.beat_id}`) === "i2i");
  if (needsI2i && !selectedOptionId(draft, "image_model::project")) {
    const legacy = gaps.some((gap) => selectedOptionId(draft, `gap_model::${gap.beat_id}`));
    if (!legacy) return false;
  }
  return true;
}

export function saveDraft(storage: DraftStorage, draft: IntentDraft) {
  try {
    storage.setItem(storageKey(draft.project_id, draft.stage), JSON.stringify(draft));
  } catch {
    // Session-scoped persistence is best-effort.
  }
}

export function readStoredDraft(
  storage: DraftStorage,
  { projectId, stage }: { projectId: string; stage: string },
): IntentDraft | null {
  let raw: string | null;
  try {
    raw = storage.getItem(storageKey(projectId, stage));
  } catch {
    return null;
  }
  if (raw === null) return null;
  try {
    const draft = JSON.parse(raw) as IntentDraft;
    if (
      !draft ||
      typeof draft !== "object" ||
      draft.version !== DRAFT_VERSION ||
      draft.project_id !== projectId ||
      draft.stage !== stage
    ) {
      return null;
    }
    return draft;
  } catch {
    return null;
  }
}

export function adoptDraftRevision(draft: IntentDraft, revision: string): IntentDraft {
  if (draft.revision === revision) return draft;
  return { ...draft, revision, updated_at: updatedAt() };
}

export function inspectStoredDraft(
  storage: DraftStorage,
  { projectId, stage, revision }: { projectId: string; stage: string; revision: string },
) {
  const draft = readStoredDraft(storage, { projectId, stage });
  if (!draft) {
    let raw: string | null = null;
    try {
      raw = storage.getItem(storageKey(projectId, stage));
    } catch {
      return { status: "missing" as const, draft: null };
    }
    if (raw === null) return { status: "missing" as const, draft: null };
    return { status: "corrupt" as const, draft: null };
  }
  if (draft.revision !== revision) {
    // Same stage card with a newer fingerprint — keep selections, retarget revision.
    return { status: "adopted" as const, draft: adoptDraftRevision(draft, revision) };
  }
  return { status: "current" as const, draft };
}

export function clearDraft(storage: DraftStorage, { projectId, stage }: { projectId: string; stage: string }) {
  try {
    storage.removeItem(storageKey(projectId, stage));
  } catch {
    // Session-scoped persistence is best-effort.
  }
}

export function primarySubmitLabel(
  stage: string,
  draft?: IntentDraft | null,
  options?: DecisionOption[],
) {
  const current = selectedOptionId(draft, `${stage}::current`);
  const hit = (options || []).find(
    (item) => String(item.id ?? item.option_id ?? "") === current,
  );
  if (hit?.label_zh) return String(hit.label_zh);
  return stage === "assets_gate" ? "开始出片" : "进入下一步";
}

export function submittedFeedback(stage: string, draft?: IntentDraft | null, options?: DecisionOption[]) {
  if (stage === "assets_gate") {
    const label = primarySubmitLabel(stage, draft, options);
    return `已点${label}，请留在本页等待本机处理。`;
  }
  return "已进入下一步，请留在本页等待本机处理。";
}
