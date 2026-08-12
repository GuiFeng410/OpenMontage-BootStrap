// Backlot 剪辑标签 — 自绘轻量片段条带（POC，零外部依赖）。
// 数据：state.artifacts.edit_decisions.cuts + state.media.renders。
// 操作约定（v2）：
//   点击片段 = 播放器预览该片段（源文件缺失给出提示，不阻塞）
//   拖左右边缘 = trim（改时长）
//   拖 ⠿ 手柄 = reorder（排序）
//   点 ✕ = delete（删除）
//   提交 = POST /intents（只写 intents/ 意图层，不碰 checkpoint/artifacts 真相）

import { el, mediaURL } from "/ui/lib.js";

const EDIT_INTENTS_URL = "/intents";

// ---- 草稿状态（模块级，跨渲染保留） -----------------------------------
let strip = [];        // [{ cut_id, source, in, out }]  in/out = 源时间秒
let baseCuts = [];     // 服务端当前 cuts（差异基准）
let baseSig = "";      // 服务端 cuts 内容摘要（版本信号）
let baseRender = null; // 最新渲染相对路径
let userNote = "";
let lastFeedback = null; // { text, ok } 提交后的提示（跨渲染保留）
let playerSrc = null;    // 当前播放器路径（null = 播放最新成片）
let selectedCut = null;  // 当前选中的片段 id
let undoStack = [];      // 操作历史快照（undo 用），最长为 UNDO_LIMIT
let rerender = () => {};

const UNDO_LIMIT = 20;

export function bindRerender(fn) {
  rerender = typeof fn === "function" ? fn : () => {};
}

// 快照当前 strip（deep copy），用于撤销。
function pushUndo() {
  undoStack.push(strip.map((c) => ({ ...c })));
  if (undoStack.length > UNDO_LIMIT) undoStack.shift();
}

// 简单内容摘要（djb2）——用作 cuts_revision 版本信号。
function digest(str) {
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) | 0;
  return "h" + (h >>> 0).toString(36);
}

const round1 = (n) => Math.round(n * 10) / 10;
// 摘要基于服务端 cuts 的原始字段（id/source/in_seconds/out_seconds）。
const cutsSig = (cuts) => digest(
  JSON.stringify(cuts.map((c) => [c.id, c.source, c.in_seconds, c.out_seconds])),
);

function resetDraft(cuts, latest) {
  baseCuts = cuts.map((c) => ({ cut_id: c.id, source: c.source, in: c.in_seconds, out: c.out_seconds }));
  baseSig = cutsSig(cuts);
  strip = baseCuts.map((c) => ({ ...c }));
  baseRender = latest ? latest.path : null;
  userNote = "";
  lastFeedback = null;
  playerSrc = null;
  selectedCut = null;
  undoStack = [];
}

// ---- 主渲染 -------------------------------------------------------------

export function renderEditTab(s) {
  const cuts = ((s.artifacts || {}).edit_decisions || {}).cuts || [];
  const renders = (s.media || {}).renders || [];
  const latest = renders[0] || null;
  const sig = cutsSig(cuts);
  // 仅当服务端成片版本变化时重置草稿（保留用户未提交的标记）。
  if (baseRender !== (latest ? latest.path : null) || baseSig !== sig) {
    resetDraft(cuts, latest);
  }

  const root = el("div", { class: "edit-tab" });
  root.append(el("div", { class: "edit-header" },
    el("h2", {}, "剪辑（轻量标记）"),
    el("span", { class: "edit-sub" },
      latest
        ? `基于成片 ${latest.path.split("/").pop()} 标记；Agent 在聊天确认后出片。`
        : "尚无成片可剪辑 — 请先完成出片。")));

  if (!cuts.length || !latest) {
    root.append(el("div", { class: "hint" },
      "尚无成片可剪辑。先走完 04-produce 出片，再来这里标记。"));
    return root;
  }

  root.append(el("div", { class: "edit-ops-hint" },
    "操作：点击片段 = 预览该段 · 拖左右边缘 = 改时长 · 拖 ⠿ 手柄 = 排序 · ✕ = 删除 · 提交后 Agent 聊天确认出片"));
  root.append(renderPlayer(latest, s.project_id));
  root.append(el("div", { class: "edit-strip-wrap" }, renderStripEl()));
  root.append(renderNoteEl());
  root.append(renderSummaryEl());
  root.append(renderActionsEl(s.project_id));
  return root;
}

// ---- 播放器（默认成片；点击片段切换预览） -------------------------------

function renderPlayer(latest, projectId) {
  const video = el("video", { class: "edit-player-video", controls: "", preload: "metadata" });
  const meta = el("div", { class: "edit-player-meta" });
  const src = playerSrc || latest.path;
  video.src = mediaURL(projectId, src);
  const fileName = (src || "").split("/").pop() || "成片";
  meta.append(el("span", {}, fileName));
  if (playerSrc) {
    meta.append(el("span", { class: "chip-ghost" }, "片段预览 · 点击其他片段可切换"));
  } else {
    meta.append(el("span", { class: "muted" }, "最新成片 · 片段按出现顺序排列"));
  }
  video.addEventListener("error", () => {
    const note = el("span", { class: "warn" }, "该片段源文件未找到，仍可按标记操作。");
    meta.append(note);
  });
  return el("div", { class: "edit-player" }, video, meta);
}

// ---- 片段条带 -----------------------------------------------------------

function renderStripEl() {
  const bar = el("div", { class: "edit-strip" });
  strip.forEach((cut, i) => bar.append(clipEl(cut, i)));
  return bar;
}

function clipEl(cut, i) {
  const dur = Math.max(0.1, cut.out - cut.in);
  const selected = selectedCut === cut.cut_id;
  const node = el("div", {
    class: "edit-clip" + (selected ? " active" : ""),
    style: `flex:${dur} 1 0`,
    "data-index": String(i),
    title: cut.source || cut.cut_id,
  },
    el("div", { class: "edit-clip-handle-grip", draggable: "true", title: "按住拖动排序",
      onclick: (e) => e.stopPropagation(),
      onpointerdown: (e) => e.stopPropagation() }, "⠿"),
    el("div", { class: "edit-clip-handle left", title: "拖动改开始时间",
      onpointerdown: (e) => startTrim(e, i, "in"), onclick: (e) => e.stopPropagation() }),
    el("div", { class: "edit-clip-body",
      onclick: () => { selectedCut = cut.cut_id; playerSrc = cut.source; rerender(); } },
      el("div", { class: "edit-clip-no" }, `第 ${i + 1} 段`),
      el("div", { class: "edit-clip-name" }, (cut.source || cut.cut_id || "").split("/").pop()),
      el("div", { class: "edit-clip-time" }, `${cut.in.toFixed(1)}–${cut.out.toFixed(1)}s · ${dur.toFixed(1)}s`)),
    el("div", { class: "edit-clip-del", title: "删除此片段",
      onclick: (e) => { e.stopPropagation(); pushUndo(); strip.splice(i, 1); lastFeedback = null; selectedCut = null; rerender(); } }, "✕"),
    el("div", { class: "edit-clip-handle right", title: "拖动改结束时间",
      onpointerdown: (e) => startTrim(e, i, "out"), onclick: (e) => e.stopPropagation() }));

  // 拖拽排序：仅 ⠿ 手柄可拖（预先约定的明确手势，避免与点击/trim 打架）。
  const grip = node.querySelector(".edit-clip-handle-grip");
  grip.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", String(i));
    e.dataTransfer.effectAllowed = "move";
    node.classList.add("drag");
  });
  grip.addEventListener("dragend", () => node.classList.remove("drag"));
  node.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; });
  node.addEventListener("drop", (e) => {
    e.preventDefault();
    const from = Number(e.dataTransfer.getData("text/plain"));
    const to = Number(node.dataset.index);
    if (Number.isFinite(from) && Number.isFinite(to) && from !== to) {
      pushUndo();
      const [moved] = strip.splice(from, 1);
      strip.splice(to, 0, moved);
      lastFeedback = null;
      rerender();
    }
  });
  return node;
}

// ---- trim 拖动（pointer events，拖动中实时反馈） -------------------------

let trimDrag = null; // { index, edge, node, startX, startVal, pxPerSec }

function startTrim(e, i, edge) {
  e.preventDefault();
  e.stopPropagation();
  lastFeedback = null;
  pushUndo();
  const node = e.currentTarget.closest(".edit-clip");
  const rect = node.getBoundingClientRect();
  const cut = strip[i];
  const dur = Math.max(0.1, cut.out - cut.in);
  trimDrag = {
    index: i, edge, node,
    startX: e.clientX,
    startVal: edge === "in" ? cut.in : cut.out,
    pxPerSec: rect.width / dur,
  };
  node.classList.add("trimming");
  const move = (ev) => {
    const dt = (ev.clientX - trimDrag.startX) / trimDrag.pxPerSec;
    applyTrim(trimDrag, trimDrag.startVal + dt);
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    trimDrag.node.classList.remove("trimming");
    trimDrag = null;
    rerender();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

function applyTrim(drag, val) {
  const cut = strip[drag.index];
  if (drag.edge === "in") {
    cut.in = Math.max(0, Math.min(val, cut.out - 0.1));
  } else {
    cut.out = Math.max(cut.in + 0.1, val);
  }
  const dur = Math.max(0.1, cut.out - cut.in);
  drag.node.style.flex = `${dur} 1 0`;
  const timeEl = drag.node.querySelector(".edit-clip-time");
  if (timeEl) timeEl.textContent = `${cut.in.toFixed(1)}–${cut.out.toFixed(1)}s · ${dur.toFixed(1)}s`;
}

// ---- 备注 / 变更摘要（常驻） / 提交 --------------------------------------

function renderNoteEl() {
  return el("div", { class: "edit-note" },
    el("label", { for: "edit-note-input" }, "备注（可选；无改动时也可仅提交备注）"),
    el("input", {
      id: "edit-note-input",
      type: "text",
      value: userNote,
      placeholder: "例如：开场太慢，中间那段去掉；或仅备注：字幕换中文",
      oninput: (e) => { userNote = e.target.value; lastFeedback = null; },
    }));
}

function collectChanges() {
  const origById = new Map(baseCuts.map((c) => [c.cut_id, c]));
  const actions = [];
  const lines = [];
  strip.forEach((c, i) => {
    const orig = origById.get(c.cut_id);
    if (orig && (Math.abs(orig.in - c.in) > 0.001 || Math.abs(orig.out - c.out) > 0.001)) {
      actions.push({ type: "trim", cut_id: c.cut_id, in_seconds: round1(c.in), out_seconds: round1(c.out) });
      lines.push(`第 ${i + 1} 段时长改为 ${round1(c.in)}–${round1(c.out)} 秒`);
    }
  });
  baseCuts.forEach((c, i) => {
    if (!strip.some((x) => x.cut_id === c.cut_id)) {
      actions.push({ type: "delete", cut_id: c.cut_id });
      lines.push(`删除原第 ${i + 1} 段（${(c.source || c.cut_id).split("/").pop()}）`);
    }
  });
  const cur = strip.map((c) => c.cut_id);
  const base = baseCuts.map((c) => c.cut_id);
  if (cur.join("|") !== base.join("|")) {
    actions.push({ type: "reorder", order: cur });
    lines.push("调整片段顺序");
  }
  return { actions, lines };
}

function renderSummaryEl() {
  const { lines } = collectChanges();
  const title = lines.length
    ? `改动清单（${lines.length} 项，提交后 Agent 确认出片）`
    : "改动清单（暂无改动）";
  return el("div", { class: "edit-summary" + (lines.length ? " has-changes" : "") },
    el("div", { class: "edit-summary-title" }, title),
    lines.length
      ? el("ul", { class: "edit-summary-list" }, lines.map((l) => el("li", {}, l)))
      : el("div", { class: "edit-summary-empty" }, "暂无改动。操作：点击片段预览 · 拖 ⠿ 手柄排序 · 拖左右边缘改时长 · ✕ 删除"));
}

function renderActionsEl(projectId) {
  const feedback = el("div", { class: "edit-feedback" + (lastFeedback?.ok ? " ok" : "") });
  if (lastFeedback) feedback.textContent = lastFeedback.text;
  const btn = el("button", { class: "btn", onclick: () => submit(projectId, feedback, btn) }, "提交剪辑要求");
  const hasChangesNow = collectChanges().actions.length > 0;
  const undoBtn = el("button", {
    class: "btn ghost",
    title: "撤销最近一次操作（可连续撤销）",
    onclick: undo,
  }, "↩ 撤销上一步");
  // disabled 是布尔 DOM 属性：必须用 property 赋值，不能用 setAttribute("disabled","false")
  //（属性存在即禁用）。el() 走 setAttribute，故这里手动控制。
  undoBtn.disabled = !undoStack.length;
  const resetBtn = el("button", {
    class: "btn ghost",
    title: "放弃所有未提交改动，恢复为服务端版本",
    onclick: resetDraftUI,
  }, "⟲ 重置为服务端版本");
  resetBtn.disabled = !hasChangesNow && !userNote.trim();
  return el("div", { class: "edit-actions" },
    btn, undoBtn, resetBtn,
    el("span", { class: "edit-actions-hint" }, "提交后 Agent 会在聊天里复述计划，确认后才出片。"),
    feedback);
}

function undo() {
  const prev = undoStack.pop();
  if (prev) {
    strip = prev;
    selectedCut = null;
    lastFeedback = null;
    rerender();
  }
}

function resetDraftUI() {
  strip = baseCuts.map((c) => ({ ...c }));
  undoStack = [];
  selectedCut = null;
  lastFeedback = null;
  rerender();
}

async function submit(projectId, feedback, btn) {
  const { actions, lines } = collectChanges();
  const note = userNote.trim();
  if (!actions.length && !note) {
    feedback.textContent = "没有需要提交的改动（可拖动片段或填写备注后再提交）。";
    return;
  }
  btn.disabled = true;
  const intent = {
    version: "1.0",
    intent_id: `intent-${Date.now()}`,
    project_id: projectId,
    created_at: new Date().toISOString(),
    status: "pending",
    base: {
      artifact: "edit_decisions",
      cuts_revision: baseSig,
      source_render: baseRender,
    },
    actions,
  };
  if (note) intent.note = note;
  try {
    const resp = await fetch(EDIT_INTENTS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(intent),
    });
    let detail = "";
    try { detail = (await resp.json()).detail || ""; } catch (_) { /* keep empty */ }
    if (resp.ok) {
      // 提交回执：让用户明确看到"已提交了什么"，避免重复误提交。
      const summary = lines.length
        ? lines.join("；")
        : (note ? `备注：${note}` : "无改动");
      lastFeedback = { text: `已提交：${summary}`, ok: true };
      strip = baseCuts.map((c) => ({ ...c }));
      undoStack = [];
      userNote = "";
      rerender();
      return;
    }
    if (resp.status === 409) feedback.textContent = "这组改动之前已经提交过了，无需重复提交。";
    else if (resp.status === 404) feedback.textContent = "项目找不到了，请刷新后重试。";
    else feedback.textContent = `提交失败（${resp.status}）：${detail || "请稍后重试"}`;
  } catch (err) {
    feedback.textContent = `提交失败：${err}`;
  } finally {
    btn.disabled = false;
  }
}
