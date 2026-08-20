import { useReducer, type PointerEvent as ReactPointerEvent } from "react";
import { mediaURL } from "./format";
import { PersistentVideo } from "./PersistentVideo";
import { submitErrorMessage } from "./editErrors";
import type { BoardState, EditCut, EditingGate } from "./types";

type DraftCut = { cut_id: string; source: string; in: number; out: number };
type Feedback = { text: string; ok: boolean };

const UNDO_LIMIT = 20;

let strip: DraftCut[] = [];
let baseCuts: DraftCut[] = [];
let baseSig = "";
let baseRender: string | null = null;
let draftProjectId = "";
let userNote = "";
let lastFeedback: Feedback | null = null;
let playerSrc: string | null = null;
let selectedCut: string | null = null;
let undoStack: DraftCut[][] = [];
let editingEnabled = false;
let editingGateMessage = "当前项目没有可消费的剪辑门禁状态。";

function digest(str: string) {
  let hash = 5381;
  for (let i = 0; i < str.length; i += 1) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) | 0;
  }
  return `h${(hash >>> 0).toString(36)}`;
}

const round1 = (n: number) => Math.round(n * 10) / 10;

function cutsSig(cuts: EditCut[]) {
  return digest(JSON.stringify(cuts.map((c) => [c.id, c.source, c.in_seconds, c.out_seconds])));
}

function asCuts(raw: unknown): EditCut[] {
  if (!raw || typeof raw !== "object") return [];
  const cuts = (raw as { cuts?: unknown }).cuts;
  if (!Array.isArray(cuts)) return [];
  return cuts.filter((item): item is EditCut => Boolean(item && typeof item === "object"));
}

function editingGateOf(state: BoardState): EditingGate | null {
  return state.editing_gate || state.commercial?.editing_gate || null;
}

function resetDraft(projectId: string, cuts: EditCut[], latestPath: string | null) {
  draftProjectId = projectId;
  baseCuts = cuts.map((c) => ({
    cut_id: String(c.id || ""),
    source: String(c.source || ""),
    in: Number(c.in_seconds) || 0,
    out: Number(c.out_seconds) || 0,
  }));
  baseSig = cutsSig(cuts);
  strip = baseCuts.map((c) => ({ ...c }));
  baseRender = latestPath;
  userNote = "";
  lastFeedback = null;
  playerSrc = null;
  selectedCut = null;
  undoStack = [];
}

function pushUndo() {
  undoStack.push(strip.map((c) => ({ ...c })));
  if (undoStack.length > UNDO_LIMIT) undoStack.shift();
}

function collectChanges() {
  const origById = new Map(baseCuts.map((c) => [c.cut_id, c]));
  const actions: Record<string, unknown>[] = [];
  const lines: string[] = [];
  strip.forEach((c, i) => {
    const orig = origById.get(c.cut_id);
    if (orig && (Math.abs(orig.in - c.in) > 0.001 || Math.abs(orig.out - c.out) > 0.001)) {
      actions.push({
        type: "trim",
        cut_id: c.cut_id,
        in_seconds: round1(c.in),
        out_seconds: round1(c.out),
      });
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

type Props = { state: BoardState };

export function EditTab({ state }: Props) {
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const cuts = asCuts(state.artifacts?.edit_decisions);
  const gate = editingGateOf(state);
  const latestPath = gate?.latest_render?.path || null;
  editingEnabled = gate?.enabled === true;
  editingGateMessage = gate?.friendly_zh || "当前项目没有可消费的剪辑门禁状态。";
  const sig = cutsSig(cuts);
  if (draftProjectId !== state.project_id || baseRender !== latestPath || baseSig !== sig) {
    resetDraft(state.project_id, cuts, latestPath);
  }

  return (
    <div className="edit-tab">
      <div className="edit-header">
        <h2>剪辑（轻量标记）</h2>
        <span className="edit-sub">
          {latestPath
            ? `基于成片 ${latestPath.split("/").pop()} 标记；Agent 在聊天确认后出片。`
            : "尚无成片可剪辑 — 请先完成出片。"}
        </span>
      </div>
      {editingEnabled ? (
        <>
          <div className="edit-ops-hint">
            操作：点击片段 = 预览该段 · 拖左右边缘 = 改时长 · 拖 ⠿ 手柄 = 排序 · ✕ = 删除 · 提交后 Agent 聊天确认出片
          </div>
          <EditPlayer projectId={state.project_id} latestPath={latestPath} />
          <div className="edit-strip-wrap">
            <EditStrip onChange={rerender} />
          </div>
          <EditNote onChange={rerender} />
          <EditSummary />
          <EditActions projectId={state.project_id} onChange={rerender} />
        </>
      ) : (
        <div className="hint edit-gate-locked">{editingGateMessage}</div>
      )}
    </div>
  );
}

function EditPlayer({ projectId, latestPath }: { projectId: string; latestPath: string | null }) {
  const srcPath = playerSrc || latestPath;
  if (!srcPath) return null;
  const fileName = srcPath.split("/").pop() || "成片";
  return (
    <div className="edit-player">
      <PersistentVideo className="edit-player-video" src={mediaURL(projectId, srcPath)} />
      <div className="edit-player-meta">
        <span>{fileName}</span>
        {playerSrc ? (
          <span className="chip-ghost">片段预览 · 点击其他片段可切换</span>
        ) : (
          <span className="muted">最新成片 · 片段按出现顺序排列</span>
        )}
      </div>
    </div>
  );
}

function EditStrip({ onChange }: { onChange: () => void }) {
  return (
    <div className="edit-strip">
      {strip.map((cut, i) => (
        <EditClip key={cut.cut_id} cut={cut} index={i} onChange={onChange} />
      ))}
    </div>
  );
}

function EditClip({
  cut,
  index,
  onChange,
}: {
  cut: DraftCut;
  index: number;
  onChange: () => void;
}) {
  const dur = Math.max(0.1, cut.out - cut.in);
  const selected = selectedCut === cut.cut_id;
  return (
    <div
      className={`edit-clip${selected ? " active" : ""}`}
      style={{ flex: `${dur} 1 0` }}
      data-index={String(index)}
      title={cut.source || cut.cut_id}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
      }}
      onDrop={(e) => {
        e.preventDefault();
        const from = Number(e.dataTransfer.getData("text/plain"));
        const to = index;
        if (Number.isFinite(from) && Number.isFinite(to) && from !== to) {
          pushUndo();
          const [moved] = strip.splice(from, 1);
          strip.splice(to, 0, moved);
          lastFeedback = null;
          onChange();
        }
      }}
    >
      <div
        className="edit-clip-handle-grip"
        draggable
        title="按住拖动排序"
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
        onDragStart={(e) => {
          e.dataTransfer.setData("text/plain", String(index));
          e.dataTransfer.effectAllowed = "move";
          e.currentTarget.closest(".edit-clip")?.classList.add("drag");
        }}
        onDragEnd={(e) => {
          e.currentTarget.closest(".edit-clip")?.classList.remove("drag");
        }}
      >
        ⠿
      </div>
      <div
        className="edit-clip-handle left"
        title="拖动改开始时间"
        onPointerDown={(e) => startTrim(e, index, "in", onChange)}
        onClick={(e) => e.stopPropagation()}
      />
      <div
        className="edit-clip-body"
        onClick={() => {
          selectedCut = cut.cut_id;
          playerSrc = cut.source;
          onChange();
        }}
      >
        <div className="edit-clip-no">{`第 ${index + 1} 段`}</div>
        <div className="edit-clip-name">{(cut.source || cut.cut_id || "").split("/").pop()}</div>
        <div className="edit-clip-time">{`${cut.in.toFixed(1)}–${cut.out.toFixed(1)}s · ${dur.toFixed(1)}s`}</div>
      </div>
      {strip.length > 1 ? (
        <div
          className="edit-clip-del"
          title="删除此片段"
          onClick={(e) => {
            e.stopPropagation();
            pushUndo();
            strip.splice(index, 1);
            lastFeedback = null;
            selectedCut = null;
            onChange();
          }}
        >
          ✕
        </div>
      ) : null}
      <div
        className="edit-clip-handle right"
        title="拖动改结束时间"
        onPointerDown={(e) => startTrim(e, index, "out", onChange)}
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}

type TrimDrag = {
  index: number;
  edge: "in" | "out";
  node: HTMLElement;
  startX: number;
  startVal: number;
  pxPerSec: number;
};

let trimDrag: TrimDrag | null = null;

function startTrim(
  e: ReactPointerEvent<HTMLDivElement>,
  index: number,
  edge: "in" | "out",
  onChange: () => void,
) {
  e.preventDefault();
  e.stopPropagation();
  lastFeedback = null;
  pushUndo();
  const node = e.currentTarget.closest(".edit-clip") as HTMLElement | null;
  if (!node) return;
  const rect = node.getBoundingClientRect();
  const cut = strip[index];
  const dur = Math.max(0.1, cut.out - cut.in);
  trimDrag = {
    index,
    edge,
    node,
    startX: e.clientX,
    startVal: edge === "in" ? cut.in : cut.out,
    pxPerSec: rect.width / dur,
  };
  node.classList.add("trimming");
  const move = (ev: PointerEvent) => {
    if (!trimDrag) return;
    const dt = (ev.clientX - trimDrag.startX) / trimDrag.pxPerSec;
    applyTrim(trimDrag, trimDrag.startVal + dt);
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    trimDrag?.node.classList.remove("trimming");
    trimDrag = null;
    onChange();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

function applyTrim(drag: TrimDrag, val: number) {
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

function EditNote({ onChange }: { onChange: () => void }) {
  return (
    <div className="edit-note">
      <label htmlFor="edit-note-input">备注（可选；无改动时也可仅提交备注）</label>
      <input
        id="edit-note-input"
        type="text"
        value={userNote}
        placeholder="例如：开场太慢，中间那段去掉；或仅备注：字幕换中文"
        onChange={(e) => {
          userNote = e.currentTarget.value;
          lastFeedback = null;
          onChange();
        }}
      />
    </div>
  );
}

function EditSummary() {
  const { lines } = collectChanges();
  const title = lines.length
    ? `改动清单（${lines.length} 项，提交后 Agent 确认出片）`
    : "改动清单（暂无改动）";
  return (
    <div className={`edit-summary${lines.length ? " has-changes" : ""}`}>
      <div className="edit-summary-title">{title}</div>
      {lines.length ? (
        <ul className="edit-summary-list">
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : (
        <div className="edit-summary-empty">
          暂无改动。操作：点击片段预览 · 拖 ⠿ 手柄排序 · 拖左右边缘改时长 · ✕ 删除
        </div>
      )}
    </div>
  );
}

function EditActions({ projectId, onChange }: { projectId: string; onChange: () => void }) {
  const hasChangesNow = collectChanges().actions.length > 0;
  return (
    <div className="edit-actions">
      <button className="btn" type="button" onClick={() => void submit(projectId, onChange)}>
        提交剪辑要求
      </button>
      <button
        className="btn ghost"
        type="button"
        title="撤销最近一次操作（可连续撤销）"
        disabled={!undoStack.length}
        onClick={() => {
          const prev = undoStack.pop();
          if (prev) {
            strip = prev;
            selectedCut = null;
            lastFeedback = null;
            onChange();
          }
        }}
      >
        ↩ 撤销上一步
      </button>
      <button
        className="btn ghost"
        type="button"
        title="放弃所有未提交改动，恢复为服务端版本"
        disabled={!hasChangesNow && !userNote.trim()}
        onClick={() => {
          strip = baseCuts.map((c) => ({ ...c }));
          undoStack = [];
          selectedCut = null;
          lastFeedback = null;
          onChange();
        }}
      >
        ⟲ 重置为服务端版本
      </button>
      <span className="edit-actions-hint">提交后 Agent 会在聊天里复述计划，确认后才出片。</span>
      <div className={`edit-feedback${lastFeedback?.ok ? " ok" : ""}`}>
        {lastFeedback?.text || ""}
      </div>
    </div>
  );
}

async function submit(projectId: string, onChange: () => void) {
  const btn = document.querySelector(".edit-actions .btn") as HTMLButtonElement | null;
  if (!editingEnabled) {
    lastFeedback = {
      text: editingGateMessage || "当前不可提交剪辑要求，请刷新项目状态。",
      ok: false,
    };
    onChange();
    return;
  }
  if (!baseRender) {
    lastFeedback = { text: "当前 canonical 成片路径无效，请刷新项目状态后重试。", ok: false };
    onChange();
    return;
  }
  const { actions, lines } = collectChanges();
  const note = userNote.trim();
  if (!actions.length && !note) {
    lastFeedback = { text: "没有需要提交的改动（可拖动片段或填写备注后再提交）。", ok: false };
    onChange();
    return;
  }
  if (btn) btn.disabled = true;
  const intent: Record<string, unknown> = {
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
    const resp = await fetch("/intents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(intent),
    });
    let detail: unknown = null;
    try {
      detail = ((await resp.json()) as { detail?: unknown }).detail ?? null;
    } catch {
      /* keep empty */
    }
    if (resp.ok) {
      const summary = lines.length ? lines.join("；") : note ? `备注：${note}` : "无改动";
      lastFeedback = { text: `已提交：${summary}`, ok: true };
      strip = baseCuts.map((c) => ({ ...c }));
      undoStack = [];
      userNote = "";
      onChange();
      return;
    }
    lastFeedback = { text: submitErrorMessage(resp.status, detail), ok: false };
    onChange();
  } catch (err) {
    lastFeedback = { text: `提交失败：${err}`, ok: false };
    onChange();
  } finally {
    if (btn) btn.disabled = false;
  }
}
