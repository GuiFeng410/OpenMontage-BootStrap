import type {
  BoardState,
  CommercialBeat,
  ContentView,
  StageState,
} from "./types";

export const RUNNER_GONE_ZH = "本机 runner 未绑定本项目。请回库页点「继续这个项目」。";

export const STAGE_ICONS: Record<string, string> = {
  completed: "✓",
  in_progress: "◉",
  awaiting_human: "◈",
  failed: "✕",
};

export const STAGE_CONTENT_VIEW: Record<string, ContentView> = {
  brief_locked: "plan",
  assets_gate: "assets",
  sample_review: "sample",
  segment_build: "segment",
  draft_review: "draft",
  final_compose: "compose",
  delivery_signoff: "delivery",
};

export const CONTENT_VIEW_LABEL: Record<ContentView, string> = {
  plan: "方案确认 · 仅文案规划",
  assets: "素材检查 · 用户素材与扩展安排",
  sample: "试片确认 · 仅入片视频",
  segment: "分段制作 · 入片视频",
  draft: "初稿审查 · 问题与修改清单",
  compose: "合成终稿 · 技术检查",
  delivery: "交付确认 · 终稿与签收",
};

const ASSIGNMENT_STATUS_ZH: Record<string, string> = {
  user_asset: "用户素材",
  reuse_pending: "复用待确认",
  reuse_approved: "复用已确认",
  missing: "缺少素材",
  i2i_planned: "I2I 待生成",
  generating: "I2I 生成中",
  review_pending: "I2I 待审",
  approved: "I2I 已批准",
  failed: "I2I 失败",
  assignment_conflict: "素材冲突",
};

export function isCommercial(state: BoardState | null | undefined) {
  return state?.pipeline?.pipeline_type === "bootstrap-commercial";
}

export function normalizeBoardState(raw: unknown): BoardState {
  const state = (raw && typeof raw === "object" ? raw : {}) as Partial<BoardState>;
  const pipeline = state.pipeline || { pipeline_type: "unknown" };
  const media = state.media || { renders: [], snapshots: [], music: [] };
  return {
    project_id: String(state.project_id || ""),
    title: String(state.title || state.project_id || "未命名项目"),
    live: Boolean(state.live),
    last_activity: state.last_activity,
    locale: state.locale || "en",
    has_pipeline_state: state.has_pipeline_state,
    pipeline: {
      pipeline_type: pipeline.pipeline_type || "unknown",
      stages: pipeline.stages || [],
      known: pipeline.known,
    },
    stages: Array.isArray(state.stages) ? state.stages : [],
    artifacts: state.artifacts || {},
    media: {
      renders: Array.isArray(media.renders) ? media.renders : [],
      snapshots: Array.isArray(media.snapshots) ? media.snapshots : [],
      music: Array.isArray(media.music) ? media.music : [],
    },
    events: Array.isArray(state.events) ? state.events : [],
    storyboard: state.storyboard ?? null,
    cost: state.cost,
    editing_gate: state.editing_gate || null,
    commercial: state.commercial || null,
  };
}

export function runnerBoundToProject(s: BoardState) {
  if (s.commercial?.completed) return true;
  const bind = s.commercial?.runner_bind;
  if (bind && typeof bind === "object") return Boolean(bind.bound);
  return Boolean(s.commercial?.runner_status?.runner_alive);
}

export function isProduceBusy(s: BoardState) {
  const phase = s.commercial?.runner_status?.phase;
  return phase === "producing" || phase === "queued" || phase === "applying";
}

export function isProducePaused(s: BoardState) {
  const runner = s.commercial?.runner_status || {};
  const dec = s.commercial?.decision || {};
  const stop = s.commercial?.board_stop || {};
  return runner.phase === "paused" || dec.paused === true || stop.paused === true;
}

export function stageNeedsDecision(st: StageState) {
  if (st?.status === "awaiting_human") return true;
  if (st?.status === "completed") return false;
  return st?.metadata?.needs_user_decision === true;
}

export function visibleStages(s: BoardState) {
  if (!isCommercial(s)) return s.stages || [];
  const ids = s.commercial?.confirm_stop_ids;
  if (!Array.isArray(ids) || !ids.length) return s.stages || [];
  const allowed = new Set(ids);
  return (s.stages || []).filter((st) => allowed.has(st.name));
}

export function commercialFocusStage(s: BoardState, selectedStage: string | null = null) {
  const allowed =
    Array.isArray(s.commercial?.confirm_stop_ids) && s.commercial.confirm_stop_ids.length
      ? new Set(s.commercial.confirm_stop_ids)
      : null;
  const stages = allowed
    ? (s.stages || []).filter((x) => allowed.has(x.name))
    : s.stages || [];
  if (selectedStage && (!allowed || allowed.has(selectedStage))) return selectedStage;
  const overlayStage = s.commercial?.board_stop?.stage;
  if (overlayStage && (!allowed || allowed.has(overlayStage))) {
    const stop = s.commercial?.board_stop || {};
    if (stop.paused || stop.producing_wait || stop.needs_user_decision) return overlayStage;
  }
  const awaiting = stages.find((x) => x.status === "awaiting_human");
  if (awaiting) return awaiting.name;
  const active = stages.find((x) => x.status === "in_progress");
  if (active) return active.name;
  const known = stages.filter((x) => !x.undeclared);
  if (known.length && known.every((x) => x.status === "completed")) {
    return allowed ? "delivery_signoff" : "segment_build";
  }
  for (const name of Object.keys(STAGE_CONTENT_VIEW)) {
    if (allowed && !allowed.has(name)) continue;
    const st = stages.find((x) => x.name === name);
    if (st && ["pending", "in_progress", "failed"].includes(st.status)) return name;
  }
  return "brief_locked";
}

export function commercialContentView(s: BoardState, selectedStage: string | null = null): ContentView {
  const stage = commercialFocusStage(s, selectedStage);
  return STAGE_CONTENT_VIEW[stage] || "plan";
}

export function stageLabel(st: StageState) {
  return st.label_zh || st.name;
}

export function stageStatusZh(status: string) {
  return (
    {
      pending: "待开始",
      in_progress: "制作中",
      awaiting_human: "等待确认",
      completed: "已完成",
      failed: "失败",
    }[status] || status
  );
}

export function stageConclusionZh(status?: string) {
  if (status === "completed") return "已确认";
  if (status === "awaiting_human") return "待你确认";
  if (status === "in_progress") return "进行中";
  if (status === "failed") return "失败";
  if (status === "pending") return "未开始";
  return status || "—";
}

export function commercialAssignmentStatusZh(beat: CommercialBeat) {
  return (
    beat.assignment_status_zh ||
    ASSIGNMENT_STATUS_ZH[beat.assignment_status || ""] ||
    "缺少素材"
  );
}

export function commercialAssignmentReason(beat: CommercialBeat) {
  return beat.assignment_reason || "没有可核对的闭环素材，请补齐账本分配或生成计划。";
}

export function beatOrdinalZh(beatId: string | undefined, index: number) {
  const nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
  const n = nums[index] || String(index + 1);
  return `第${n}段（${beatId || `beat_${index + 1}`}）`;
}

export function formatCommercialMethod(beat: CommercialBeat) {
  const raw = beat.method || "";
  if (/Remotion|图片缩放|图片转场|静图/.test(raw)) {
    if (/转场/.test(raw)) return "图片转场-非AI生成（Remotion）";
    return "图片缩放-非AI生成（Remotion）";
  }
  const engine = [beat.provider, beat.model].filter(Boolean).join(" / ");
  if (/AI|视频生成|Agnes/i.test(raw) || engine) {
    const detail = engine ? `（${engine}）` : "";
    const qualifier = raw && !/^视频生成$/i.test(raw) ? ` · ${raw}` : "";
    return `视频生成-AI${detail}${qualifier}`;
  }
  return raw || "—";
}

export function shouldHideMinimalAssetPanels(s: BoardState) {
  const preset =
    s.commercial?.review_mode_preset ||
    s.commercial?.brief_summary?.review_mode_preset ||
    s.commercial?.brief_summary?.review_mode;
  if (preset !== "minimal") return false;
  const assetsGate = (s.stages || []).find((x) => x.name === "assets_gate");
  return assetsGate?.status === "completed";
}

export function stageWasCompletedBefore(st: StageState) {
  return (st.history_entries || []).some((entry) => entry?.status === "completed");
}

export function projectIdFromPath() {
  const raw = window.location.pathname.replace(/^\/next\/p\//, "").replace(/^\/p\//, "");
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}
