import { STAGE_ICONS, el, fmtClock } from "./lib.js";

function isCommercial(s) {
  return s?.pipeline?.pipeline_type === "bootstrap-commercial";
}

export function stageLabel(st) {
  return st.label_zh || st.name;
}

export function stageNeedsDecision(st) {
  return st?.status === "awaiting_human"
    || (st?.status === "in_progress" && st?.metadata?.needs_user_decision === true);
}

function stageWasCompletedBefore(st) {
  return (st?.history_entries || []).some((entry) => entry?.status === "completed");
}

function stageSubZh(st) {
  if (st.status === "awaiting_human") return "等你聊天确认\n在聊天里回复继续";
  if (st.status === "in_progress" && stageWasCompletedBefore(st)) {
    return st.stalled
      ? `重试中·此前已通过\n可能卡住 · ${st.stalled_minutes} 分钟无活动`
      : "重试中·此前已通过";
  }
  if (st.status === "in_progress" && st.stalled) {
    return `可能卡住 · ${st.stalled_minutes} 分钟无活动\n可询问 Agent 状态`;
  }
  if (st.status === "in_progress" && st.partial_progress) {
    const done = st.partial_progress.beats_done || st.partial_progress.completed_scene_ids;
    if (Array.isArray(done)) return `已完成 ${done.length} 段`;
    return "制作中";
  }
  if (st.status === "in_progress") return "制作中";
  if (st.status === "failed") return st.error ? String(st.error).slice(0, 60) : "失败";
  if (st.status === "completed") return st.gated && st.human_approved ? "已通过" : "已完成";
  if (st.timestamp) return fmtClock(st.timestamp);
  return "待开始";
}

function stageStatusZh(status) {
  return {
    pending: "待开始",
    in_progress: "制作中",
    awaiting_human: "等待确认",
    completed: "已完成",
    failed: "失败",
  }[status] || status;
}

function stageSub(st) {
  if (st.status === "awaiting_human") return "awaiting your approval\nreply in chat to continue";
  if (st.status === "in_progress" && st.stalled) {
    return `stalled? no activity for ${st.stalled_minutes}m\nask the agent for status`;
  }
  if (st.status === "in_progress" && st.partial_progress) {
    const done = st.partial_progress.completed_scene_ids;
    if (Array.isArray(done)) return `${done.length} scene${done.length === 1 ? "" : "s"} done`;
    return "in progress";
  }
  if (st.status === "in_progress") return "in progress";
  if (st.status === "failed") return st.error ? String(st.error).slice(0, 60) : "failed";
  if (st.timestamp) {
    const approved = st.gated && st.human_approved ? " · approved" : "";
    return fmtClock(st.timestamp) + approved;
  }
  return "";
}

export function renderStageRail(s, {
  selectedStage,
  focusStageName,
  onToggleStage,
}) {
  const rail = el("nav", { class: "rail" });
  const commercial = isCommercial(s);
  let pendingIndex = 1;
  for (const st of s.stages) {
    const cls = st.status === "completed" ? "done"
      : st.status === "in_progress" ? (st.stalled ? "active stalled" : "active")
      : st.status === "awaiting_human" ? "await"
      : st.status === "failed" ? "failed" : "";
    const icon = STAGE_ICONS[st.status] || String(pendingIndex);
    if (!STAGE_ICONS[st.status]) pendingIndex += 1;
    const sub = commercial ? stageSubZh(st) : stageSub(st);
    const isFocus = focusStageName && st.name === focusStageName;
    const node = el("div", {
      class: `stage ${cls}${selectedStage === st.name ? " selected" : ""}${isFocus ? " focus" : ""}${st.undeclared ? " undeclared" : ""}`,
      title: st.undeclared ? `"${st.name}" ran but isn't declared by this pipeline's manifest` : null,
      onclick: () => onToggleStage(st.name),
    },
      el("span", { class: "line" }),
      el("span", { class: "node" }, icon),
      el("span", { class: "name" }, stageLabel(st)),
      el("span", { class: "sub", style: "white-space:pre-line" },
        st.undeclared ? `${sub}\n未列入管线`.trim() : sub),
    );
    rail.append(node);
  }
  return rail;
}

const STAGE_ARTIFACTS = {
  research: ["research_brief"],
  proposal: ["proposal_packet"],
  idea: ["brief"],
  script: ["script"],
  scene_plan: ["scene_plan"],
  assets: ["asset_manifest"],
  edit: ["edit_decisions"],
  compose: ["render_report", "final_review"],
  publish: ["publish_log"],
};

const COMMERCIAL_STAGE_ARTIFACTS = {
  brief_locked: ["brief", "video_plan"],
  assets_gate: ["brief", "asset_precheck", "asset_ledger", "segment_cards"],
  sample_review: ["sample_reel"],
  segment_build: ["review_overview", "batch01_review", "batch02_review"],
  draft_review: ["full_draft_pro"],
  delivery_signoff: ["cost_log"],
};

export function renderStageDrawer(s, {
  selectedStage,
  onToggleStage,
}) {
  if (!selectedStage) return null;
  const st = s.stages.find((x) => x.name === selectedStage);
  if (!st) return null;

  const body = el("div", { class: "drawer-body" });

  if (isCommercial(s)) {
    body.append(el("div", { class: "hint", style: "margin-bottom:12px;line-height:1.6" },
      "商品片阶段详情已在下方「方案摘要 / Beat 胶片条 / 成片预览」展示。",
      el("br"),
      "原始 JSON 见 ", el("code", {}, "artifacts/"), " 目录；审批请在聊天进行。"));
    const meta = st.metadata || {};
    if (stageNeedsDecision(st) && meta.decision_prompt_zh) {
      body.append(el("div", { class: "commercial-decision-hint" },
        el("b", {}, "若本阶段等待你："),
        el("div", {}, meta.decision_prompt_zh)));
    }
    if (meta.approval_note) {
      body.append(el("div", { class: "hint" }, `已记录批准：${meta.approval_note}`));
    }
    return el("div", { class: "drawer commercial-drawer" },
      el("div", { class: "drawer-head" },
        el("h3", {}, `${stageLabel(st)} — ${stageStatusZh(st.status)}`),
        st.timestamp ? el("span", { class: "meta", style: "font-family:var(--mono);font-size:calc(10.5px * var(--fs-scale));color:var(--text-3)" }, st.timestamp) : null,
        el("span", { class: "close", onclick: () => onToggleStage(st.name) }, "关闭 ✕"),
      ),
      body);
  }

  if (st.review) {
    body.append(el("div", { class: "findings", style: "margin-bottom:12px" },
      el("span", { class: `f ${st.review.critical ? "crit" : ""}` }, `${st.review.critical ?? 0} critical`),
      el("span", { class: `f ${st.review.suggestions ? "sugg" : ""}` }, `${st.review.suggestions ?? 0} suggestions`),
      el("span", { class: "f" }, `${st.review.nitpicks ?? 0} nitpicks`),
      typeof st.review.summary === "string" ? el("span", { style: "font-size:calc(11.5px * var(--fs-scale));color:var(--text-2);margin-left:8px" }, st.review.summary) : null,
    ));
  }

  const names = (isCommercial(s) ? COMMERCIAL_STAGE_ARTIFACTS : STAGE_ARTIFACTS)[st.name] || [];
  let shown = false;
  for (const name of names) {
    const artifact = s.artifacts[name];
    if (!artifact) continue;
    shown = true;
    body.append(
      el("div", { class: "d-cat", style: "font-family:var(--mono);font-size:calc(9.5px * var(--fs-scale));color:var(--text-3);letter-spacing:.1em;text-transform:uppercase;margin:6px 0 4px" }, name),
      el("pre", {}, JSON.stringify(artifact, null, 2)),
    );
  }
  if (!shown) {
    body.append(el("div", { class: "hint" },
      st.status === "pending" ? "This stage hasn't run yet." : "No canonical artifact found on disk for this stage."));
  }

  return el("div", { class: "drawer" },
    el("div", { class: "drawer-head" },
      el("h3", {}, `${stageLabel(st)} — ${st.status}`),
      st.gate_skipped ? el("span", { class: "gate-chip" }, "⚑ GATE SKIPPED") : null,
      st.versions > 1 ? el("span", { class: "ver-chip" }, `v${st.versions}`) : null,
      st.timestamp ? el("span", { class: "meta", style: "font-family:var(--mono);font-size:calc(10.5px * var(--fs-scale));color:var(--text-3)" }, st.timestamp) : null,
      el("span", { class: "close", onclick: () => onToggleStage(st.name) }, "CLOSE ✕"),
    ),
    body,
  );
}
