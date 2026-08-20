import { useState } from "react";
import { fmtClock, fmtDuration, fmtMoney, mediaURL, thumbURL } from "./format";
import { PersistentVideo } from "./PersistentVideo";
import type { BoardEvent, BoardState } from "./types";

type ScriptSection = {
  id?: string;
  label?: string;
  text?: string;
  speaker_directions?: string;
  start_seconds?: number;
  end_seconds?: number;
  enhancement_cues?: { type?: string; description?: string }[];
};

type ScriptArtifact = {
  title?: string;
  total_duration_seconds?: number;
  sections?: ScriptSection[];
};

type StoryVisual = {
  exists?: boolean;
  path?: string;
  type?: string;
  model?: string;
  source_tool?: string;
};

type StoryScene = {
  id?: string;
  duration_seconds?: number;
  description?: string;
  narration?: string;
  shot_intent?: string;
  framing?: string;
  movement?: string;
  type?: string;
  visual?: StoryVisual | null;
  generating?: boolean;
};

type MediaItem = { path?: string; size?: number; at_root?: boolean };

export function GenericBoard({ state }: { state: BoardState }) {
  const script = (state.artifacts?.script || null) as ScriptArtifact | null;
  const storyboard = state.storyboard as { scenes?: StoryScene[]; total_duration_seconds?: number } | null;
  const renders = (Array.isArray(state.media.renders) ? state.media.renders : []) as MediaItem[];
  const snapshots = (Array.isArray(state.media.snapshots) ? state.media.snapshots : []) as MediaItem[];
  const hasDecisions = Boolean(
    Array.isArray((state.artifacts?.decision_log as { decisions?: unknown[] } | undefined)?.decisions) &&
      ((state.artifacts?.decision_log as { decisions?: unknown[] }).decisions || []).length,
  );
  const hasActivity = Boolean((state.events || []).length);
  const scriptCard = script ? <ScriptCard state={state} script={script} /> : null;
  const story = storyboard?.scenes?.length ? <StoryboardStrip state={state} board={storyboard} /> : null;
  const found = !storyboard && snapshots.length ? <FoundMedia state={state} snapshots={snapshots} /> : null;
  const renderBlock = renders.length ? <RendersBlock state={state} renders={renders} /> : null;
  const hasChrome = Boolean(scriptCard || hasDecisions || hasActivity);
  const mediaBlocks = (
    <>
      {story}
      {found}
      {renderBlock}
    </>
  );
  return (
    <>
      <NoStateNotice state={state} />
      {hasChrome ? (
        <div className="board">
          <div className="main-col">
            {scriptCard}
            {mediaBlocks}
          </div>
          <aside>
            <DecisionsPanel state={state} />
            <ActivityPanel state={state} />
          </aside>
        </div>
      ) : (
        mediaBlocks
      )}
    </>
  );
}

function NoStateNotice({ state }: { state: BoardState }) {
  if (state.has_pipeline_state) return null;
  return (
    <div className="notice" style={{ borderColor: "#2b2b33", background: "var(--surface-2)", color: "var(--text-3)" }}>
      <span style={{ fontSize: "calc(15px * var(--fs-scale))" }}>◌</span>
      <span>
        <b style={{ color: "var(--text-2)" }}>No pipeline state. </b>
        This project has no checkpoints — Backlot is showing what it found on disk. Runs that follow the checkpoint
        protocol get the full board.
      </span>
    </div>
  );
}

function ScriptCard({ state, script }: { state: BoardState; script: ScriptArtifact }) {
  const [open, setOpen] = useState(false);
  const sections = script.sections || [];
  const shown = open ? sections : sections.slice(0, 4);
  const scriptStage = state.stages.find((x) => x.name === "script");
  const approved = scriptStage?.status === "completed";
  return (
    <div className="script-card script-preview" title="Click to expand full script" onClick={() => setOpen((v) => !v)}>
      {approved ? <span className="script-approved">APPROVED</span> : null}
      <div className="sp-title">{script.title || state.title}</div>
      <div className="sp-meta">{`script · ${fmtDuration(script.total_duration_seconds)} · ${sections.length} sections`}</div>
      {shown.map((sec, i) => (
        <ScriptSectionView key={sec.id || i} sec={sec} />
      ))}
      {!open && sections.length > 4 ? (
        <div className="sp-fade">{`… ${sections.length - 4} more sections`}</div>
      ) : null}
      <span className="sp-expand">{open ? "END" : "⤢ EXPAND SCRIPT"}</span>
    </div>
  );
}

function ScriptSectionView({ sec }: { sec: ScriptSection }) {
  const cues = sec.enhancement_cues || [];
  return (
    <>
      <div className="sp-slug">
        {`${(sec.id || "").toUpperCase()} — ${sec.label || "Section"} `}
        <span className="tc">{`${fmtDuration(sec.start_seconds)} – ${fmtDuration(sec.end_seconds)}`}</span>
      </div>
      {sec.text ? <div className="sp-action">{sec.text}</div> : null}
      {sec.speaker_directions ? <div className="sp-paren">{`(${sec.speaker_directions})`}</div> : null}
      {cues.length ? (
        <div style={{ marginLeft: 42 }}>
          {cues.map((cue, i) => (
            <span key={i} className="sp-cue">
              {`▸ ${cue.type} · ${String(cue.description || "").slice(0, 60)}`}
            </span>
          ))}
        </div>
      ) : null}
    </>
  );
}

function DecisionsPanel({ state }: { state: BoardState }) {
  const log = state.artifacts?.decision_log as { decisions?: Record<string, unknown>[] } | undefined;
  const decisions = Array.isArray(log?.decisions) ? log.decisions : [];
  if (!decisions.length) return null;
  const current = new Map<string, { d: Record<string, unknown>; order: number; revised: number }>();
  decisions.forEach((d, i) => {
    const key = `${d.category || "decision"}::${d.subject || ""}`;
    const prev = current.get(key);
    current.set(key, { d, order: i, revised: prev ? prev.revised + 1 : 0 });
  });
  const shown = [...current.values()].sort((a, b) => b.order - a.order).slice(0, 8);
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Decisions</h2>
        <span className="meta">decision_log.json</span>
      </div>
      <div className="panel-body">
        {shown.map(({ d, revised }, i) => {
          const selected = String(d.selected || "");
          const opts = Array.isArray(d.options_considered) ? d.options_considered : [];
          const opt = opts.find((o) => {
            const rec = o as { option_id?: string; label?: string };
            return (rec.option_id ?? rec.label) === selected;
          }) as { label?: string } | undefined;
          const selLabel = opt?.label || selected;
          return (
            <div className="decision" key={i}>
              <div className="d-cat">
                {`${d.category || "decision"}${d.confidence ? ` · ${d.confidence}` : ""}`}
                {revised ? <span className="d-revised"> · revised</span> : null}
              </div>
              <div className="d-pick">
                {`${d.subject || ""} `}
                <span className="arrow">→</span>
                {` ${selLabel}`}
              </div>
              {d.reason ? <div className="d-why">{String(d.reason)}</div> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ActivityPanel({ state }: { state: BoardState }) {
  const events = state.events || [];
  if (!events.length) return null;
  const open = new Map<string, { count: number; ev: BoardEvent }>();
  const rows: BoardEvent[] = [];
  for (const ev of events) {
    const key = `${ev.tool}:${ev.scene_id || ""}`;
    if (ev.event === "start") {
      const slot = open.get(key) || { count: 0, ev };
      slot.count += 1;
      slot.ev = ev;
      open.set(key, slot);
    } else {
      const slot = open.get(key);
      if (slot) {
        slot.count -= 1;
        if (slot.count <= 0) open.delete(key);
      }
      rows.push(ev);
    }
  }
  for (const slot of open.values()) rows.push(slot.ev);
  rows.sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Activity</h2>
        <span className="meta">events.jsonl</span>
      </div>
      <div className="panel-body">
        {rows.slice(-10).reverse().map((ev, i) => (
          <div className="act-row" key={`${ev.ts}-${i}`}>
            <span className="t">{fmtClock(ev.ts)}</span>
            <span className="tool">{ev.tool || ""}</span>
            <span className="target">{ev.scene_id || ""}</span>
            <ActivityStatus ev={ev} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ActivityStatus({ ev }: { ev: BoardEvent }) {
  if (ev.event === "finish") {
    return (
      <span className={`status ${ev.success === false ? "err" : "ok"}`}>
        {`${ev.success === false ? "✕" : "✓"}${ev.duration_s != null ? ` ${Number(ev.duration_s).toFixed(1)}s` : ""}${ev.cost_usd ? ` ${fmtMoney(ev.cost_usd)}` : ""}`}
      </span>
    );
  }
  if (ev.event === "error") return <span className="status err">✕</span>;
  return <span className="status run">● running</span>;
}

function sceneLabel(id: string) {
  const m = String(id).match(/(\d+)\s*$/);
  if (m) return `SC ${m[1].padStart(2, "0")}`;
  return String(id).toUpperCase().slice(0, 10);
}

function StoryboardStrip({
  state,
  board,
}: {
  state: BoardState;
  board: { scenes?: StoryScene[]; total_duration_seconds?: number };
}) {
  const scenes = board.scenes || [];
  return (
    <div>
      <div className="section-title">
        Storyboard
        <span className="meta">
          {`${scenes.length} scenes${board.total_duration_seconds ? ` · ${fmtDuration(board.total_duration_seconds)}` : ""} · card width ∝ duration`}
        </span>
      </div>
      <div className="strip-outer">
        <div className="filmstrip">
          {scenes.map((card) => (
            <SceneCard key={card.id} state={state} card={card} />
          ))}
        </div>
      </div>
    </div>
  );
}

function SceneCard({ state, card }: { state: BoardState; card: StoryScene }) {
  const dur = card.duration_seconds;
  const width = Math.max(132, Math.min(300, 70 + (dur || 3) * 26));
  const visual = card.visual;
  return (
    <div className="scene-card" style={{ width }}>
      <div className="sc-slate">
        <span className="num">{sceneLabel(card.id || "")}</span>
        <span className="dur">{fmtDuration(dur)}</span>
      </div>
      <SceneThumb state={state} card={card} visual={visual} />
      {card.narration ? <div className="narr">{card.narration}</div> : null}
    </div>
  );
}

function SceneThumb({
  state,
  card,
  visual,
}: {
  state: BoardState;
  card: StoryScene;
  visual?: StoryVisual | null;
}) {
  if (card.generating) {
    return (
      <div className="thumb generating">
        <div className="shimmer" />
        <div className="gen-label">
          <span>◉ GENERATING</span>
        </div>
      </div>
    );
  }
  if (visual?.exists && visual.path) {
    if (visual.type === "video") {
      return (
        <div className="thumb approved">
          <PersistentVideo src={mediaURL(state.project_id, visual.path)} muted controls={false} />
          <span className="play">▶</span>
        </div>
      );
    }
    return (
      <div className="thumb approved">
        <img src={thumbURL(state.project_id, visual.path, 640)} loading="lazy" alt="" />
      </div>
    );
  }
  if (visual && !visual.exists) {
    return (
      <div className="thumb missing">
        <div className="spec-in">
          <span className="warn-ic">⚑</span>
          <div className="spec-desc">asset in manifest, file missing</div>
          <div className="spec-shot">{visual.path || ""}</div>
        </div>
      </div>
    );
  }
  if (card.type === "text_card") {
    return (
      <div className="thumb textcard">
        <div className="tc-copy">{(card.narration || card.description || "").slice(0, 48)}</div>
      </div>
    );
  }
  return (
    <div className="thumb spec">
      <div className="spec-in">
        <div className="spec-desc">{card.description || ""}</div>
        <div className="spec-shot">{[card.framing, card.movement].filter(Boolean).join(" · ").slice(0, 70)}</div>
      </div>
    </div>
  );
}

function FoundMedia({ state, snapshots }: { state: BoardState; snapshots: MediaItem[] }) {
  return (
    <div>
      <div className="section-title">
        What the watcher found
        <span className="meta">snapshots / verification frames</span>
      </div>
      <div className="found-grid">
        {snapshots.slice(0, 12).map((snap) =>
          snap.path ? (
            <div className="thumb" key={snap.path}>
              <img src={thumbURL(state.project_id, snap.path, 640)} loading="lazy" alt="" />
            </div>
          ) : null,
        )}
      </div>
    </div>
  );
}

function RendersBlock({ state, renders }: { state: BoardState; renders: MediaItem[] }) {
  const [active, setActive] = useState(0);
  const current = renders[Math.min(active, renders.length - 1)];
  if (!current?.path) return null;
  const src = mediaURL(state.project_id, current.path);
  return (
    <div>
      <div className="section-title">
        Renders
        <span className="meta">{`${renders.length} version${renders.length === 1 ? "" : "s"}`}</span>
      </div>
      <div className="render-hero">
        <PersistentVideo src={src} />
      </div>
      <div className="render-meta">
        {renders.map((item, i) => (
          <span
            key={item.path || i}
            className={`v${i === active ? " active" : ""}`}
            onClick={() => setActive(i)}
          >
            {`${(item.path || "").split("/").pop()}${item.at_root ? " · root" : ""}`}
          </span>
        ))}
        {current.size != null ? (
          <span style={{ marginLeft: "auto" }}>{`${(current.size / 1048576).toFixed(1)} MB`}</span>
        ) : null}
      </div>
    </div>
  );
}
