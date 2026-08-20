import { thumbURL } from "./format";
import {
  CONTENT_VIEW_LABEL,
  beatOrdinalZh,
  commercialAssignmentReason,
  commercialAssignmentStatusZh,
  commercialContentView,
  commercialFocusStage,
  formatCommercialMethod,
} from "./model";
import type { BoardState, CommercialBeat, ContentView, LedgerItem, PlannedEntry } from "./types";

type Props = { state: BoardState; selectedStage: string | null };

export function BeatFilmstrip({ state, selectedStage }: Props) {
  const allBeats = state.commercial?.beats || [];
  if (!allBeats.length) return null;
  const view = commercialContentView(state, selectedStage);
  if (view === "compose" || view === "delivery") return null;
  const sampleBeatIds = Array.isArray(state.commercial?.stage_evidence?.sample?.beat_ids)
    ? state.commercial.stage_evidence.sample.beat_ids
    : [];
  const beats = view === "sample" ? allBeats.filter((beat) => sampleBeatIds.includes(beat.beat || "")) : allBeats;
  if (!beats.length) return null;
  const focus = commercialFocusStage(state, selectedStage);
  const focusLabel = (state.stages.find((x) => x.name === focus) || {}).label_zh || focus;
  const batches = state.commercial?.batches || [];
  return (
    <div className="commercial-film-block">
      <div className="section-title">
        Beat 胶片条 / 时间线
        <span className="meta">
          {` · ${CONTENT_VIEW_LABEL[view] || view}`}
          {selectedStage ? ` · 已选：${focusLabel}` : ""}
          {batches.length && state.commercial?.review_mode === "pro" ? ` · ${batches.length} 批` : ""}
        </span>
      </div>
      <div className="content-view-hint">
        证据按阶段递进：方案确认看文案 → 素材检查看用户图与扩展安排 → 试片/分段看入片视频 → 初稿看问题与修改 → 终稿看技术检查 → 交付看签收。
        <b> 点击顶栏阶段</b> 可切换该阶段视图。本刀不播放视频。
      </div>
      <Timeline state={state} />
      <div className="beat-card-grid">
        {beats.map((beat, i) => (
          <BeatCard key={beat.beat || i} state={state} beat={beat} index={i} view={view} />
        ))}
      </div>
    </div>
  );
}

function Timeline({ state }: { state: BoardState }) {
  const tl = state.commercial?.timeline;
  const dur = Number(tl?.duration_seconds) || 0;
  if (!tl || dur <= 0) return null;
  const bySec = new Map<number, { seconds: number; kind?: string; label?: string; beat?: string }>();
  const put = (m: { seconds?: number; kind?: string; label?: string; beat?: string }) => {
    const sec = Number(m.seconds);
    if (!Number.isFinite(sec)) return;
    const prev = bySec.get(sec);
    if (!prev) {
      bySec.set(sec, { ...m, seconds: sec });
      return;
    }
    if (m.kind === "batch") {
      bySec.set(sec, { ...m, seconds: sec, beat: prev.beat || m.beat });
    } else if (prev.kind !== "batch" && m.kind === "end") {
      bySec.set(sec, { ...m, seconds: sec });
    }
  };
  const endLabel = Number.isInteger(dur) ? `${dur}s` : `${dur.toFixed(1)}s`;
  put({ seconds: 0, kind: "end", label: "0s" });
  for (const m of tl.beat_marks || []) put(m);
  for (const m of tl.batch_marks || []) put(m);
  put({ seconds: dur, kind: "end", label: endLabel });
  const marks = [...bySec.values()].sort((a, b) => a.seconds - b.seconds);
  return (
    <div className="commercial-timeline">
      <div className="tl-legend">
        <span className="lg-beat">细刻度 · beat 界</span>
        {state.commercial?.review_mode === "pro" ? <span className="lg-batch">粗刻度 · 批次界</span> : null}
      </div>
      <div className="tl-track">
        {marks.map((m) => {
          const pct = Math.max(0, Math.min(100, (m.seconds / dur) * 100));
          const isBatch = m.kind === "batch";
          return (
            <button
              key={`${m.kind}-${m.seconds}-${m.label}`}
              type="button"
              className={`tl-mark ${m.kind || ""}${isBatch ? " bold" : ""}`}
              style={{ left: `${pct}%` }}
              title={isBatch ? `批次界 ${m.label}` : `切分 ${m.label}`}
              onClick={() => {
                if (!m.beat) return;
                document
                  .querySelector(`.commercial-beat-card[data-beat="${m.beat}"]`)
                  ?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
              }}
            >
              <span className="tl-tick" />
              <span className="tl-label">{m.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function BeatCard({
  state,
  beat,
  index,
  view,
}: {
  state: BoardState;
  beat: CommercialBeat;
  index: number;
  view: ContentView;
}) {
  const assignmentStatus = beat.assignment_status || "missing";
  const assignmentLabel = commercialAssignmentStatusZh(beat);
  const statusClass = ["user_asset", "reuse_approved", "approved"].includes(assignmentStatus)
    ? "ok"
    : ["missing", "reuse_pending", "failed", "review_pending", "assignment_conflict"].includes(assignmentStatus)
      ? "warn"
      : "";
  return (
    <div
      className={`commercial-beat-card mode-${view}`}
      data-beat={beat.beat || ""}
      data-assignment-status={assignmentStatus}
    >
      <div className="cbc-head">
        <div className="cbc-title">{beatOrdinalZh(beat.beat, index)}</div>
        <span className={`status-chip ${statusClass}`}>{assignmentLabel}</span>
      </div>
      <div className="cbc-time">{`时间段：${beat.time || "未填写"}`}</div>
      <MediaStack state={state} beat={beat} view={view} />
      <PlannedEntries state={state} beat={beat} view={view} />
      <div className="cbc-body">
        <div className="commercial-assignment-summary">
          <div className="beat-field">
            <b>素材安排</b>
            <div>{beat.asset_plan_zh || "尚未写入具体素材安排"}</div>
          </div>
          <div className="beat-field assignment-counts">
            <b>所需 / 现有</b>
            <div>{`${beat.required_count ?? beat.need_count ?? 1} 张 / ${beat.available_count ?? beat.have_count ?? 0} 张`}</div>
          </div>
          <div className="beat-field">
            <b>状态</b>
            <div>{assignmentLabel}</div>
          </div>
          <div className="beat-field assignment-reason">
            <b>原因</b>
            <div>{commercialAssignmentReason(beat)}</div>
          </div>
        </div>
        {(beat.assignment_warnings || [])
          .concat(beat.assignment_warning && !(beat.assignment_warnings || []).includes(beat.assignment_warning)
            ? [beat.assignment_warning]
            : [])
          .filter(Boolean)
          .map((warning) => (
            <div className="commercial-assignment-warning" key={warning}>
              {warning}
            </div>
          ))}
        {view === "plan" ? (
          <>
            <div className="beat-field">
              <b>文案规划</b>
              <div>{beat.copy_plan_zh || "—"}</div>
            </div>
            <div className="beat-field">
              <b>镜头规划</b>
              <div>{beat.shot_plan_zh || "—"}</div>
            </div>
          </>
        ) : view === "assets" ? (
          <>
            {beat.need_detail_zh ? (
              <div className="beat-field warn-text">
                <b>I2I 扩展/缺口</b>
                <div>{beat.need_detail_zh}</div>
              </div>
            ) : null}
            {beat.copy_plan_zh || beat.shot_plan_zh ? (
              <details className="beat-plan-fold">
                <summary>回顾：该段文案/镜头（方案确认）</summary>
                {beat.copy_plan_zh ? <div>{beat.copy_plan_zh}</div> : null}
                {beat.shot_plan_zh ? <div>{beat.shot_plan_zh}</div> : null}
              </details>
            ) : null}
          </>
        ) : (
          <>
            <div className="cbc-method">{formatCommercialMethod(beat)}</div>
            {beat.angle_use ? <div className="cbc-sub">{beat.angle_use}</div> : null}
            {beat.ref ? <div className="cbc-sub">{`参考 · ${beat.ref}`}</div> : null}
            {["sample", "segment", "draft"].includes(view) ? <GenerationDetails beat={beat} /> : null}
          </>
        )}
      </div>
      <LedgerStrip beat={beat} view={view} />
    </div>
  );
}

function MediaStack({
  state,
  beat,
  view,
}: {
  state: BoardState;
  beat: CommercialBeat;
  view: ContentView;
}) {
  const ledger = beat.ledger || [];
  const images = ledger.filter((x) => x.kind === "image" && x.path);
  if (view === "plan") return null;
  if (view === "assets") {
    if (!images.length) {
      return <div className="beat-media-stack"><div className="beat-media empty">该 Beat 尚无用户图片</div></div>;
    }
    return (
      <div className="beat-media-stack">
        {images.map((img) => (
          <div className={`beat-media image${img.selected ? " selected" : ""}`} key={img.path}>
            {img.exists === false ? (
              <span className="media-cap">缺失</span>
            ) : (
              <img src={thumbURL(state.project_id, img.path || "", 480)} loading="lazy" alt={img.file || ""} />
            )}
            <span className="media-cap">{img.label_zh || "图片"}</span>
          </div>
        ))}
      </div>
    );
  }
  const videoPath = beat.asset_path;
  return (
    <div className="beat-media-stack">
      {images
        .filter((i) => i.selected || images.length === 1)
        .map((img) => (
          <div className={`beat-media image${img.selected ? " selected" : ""}`} key={img.path}>
            {img.path && img.exists !== false ? (
              <img src={thumbURL(state.project_id, img.path, 480)} loading="lazy" alt={img.file || ""} />
            ) : null}
            <span className="media-cap">{img.label_zh || "图片"}</span>
          </div>
        ))}
      {videoPath ? (
        <div className="beat-media empty">
          <span className="media-cap">{`分段视频（本刀不播放）· ${videoPath}`}</span>
        </div>
      ) : (
        <div className="beat-media empty">该 Beat 尚无已挂接分段视频</div>
      )}
    </div>
  );
}

function PlannedEntries({
  state,
  beat,
  view,
}: {
  state: BoardState;
  beat: CommercialBeat;
  view: ContentView;
}) {
  const entries = (beat.planned_entries || []).filter((item) => item?.kind === "image");
  if (!entries.length || view !== "assets") return null;
  return (
    <div className="asset-label-strip planned-entry-strip" style={{ gap: 8 }}>
      {entries.map((item, i) => (
        <PlannedCard key={`${item.path || item.prompt_zh || i}`} state={state} item={item} />
      ))}
    </div>
  );
}

function PlannedCard({ state, item }: { state: BoardState; item: PlannedEntry }) {
  const statusLabels: Record<string, string> = {
    planned: "待生成",
    i2i_planned: "待生成",
    generating: "生成中",
    generated: "候选/待审",
    review_pending: "候选/待审",
    i2i_review_pending: "候选/待审",
    ready: "候选/待审",
    approved: "已批准",
    failed: "生成失败",
    rejected: "生成失败",
  };
  const reportedStatus = item.status || "planned";
  const unavailableReady =
    ["ready", "approved", "review_pending", "generated"].includes(reportedStatus) &&
    (!item.path || item.exists === false);
  const status = unavailableReady
    ? "failed"
    : item.preview_kind === "candidate"
      ? "review_pending"
      : reportedStatus;
  return (
    <div className={`beat-field planned-entry-card status-${status}`} data-status={status} style={{ display: "grid", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
        <b>{item.label_zh || "计划图片"}</b>
        <span className={`status-chip ${status === "approved" ? "ok" : ["failed", "review_pending"].includes(status) ? "warn" : ""}`}>
          {statusLabels[status] || status}
        </span>
      </div>
      {["review_pending", "generated", "approved"].includes(status) && item.path && item.exists !== false ? (
        <img
          src={thumbURL(state.project_id, item.path, 480)}
          loading="lazy"
          alt={item.label_zh || item.prompt_zh || ""}
          style={{ width: "100%", maxHeight: 160, objectFit: "contain", borderRadius: 6, background: "var(--media-bg)" }}
        />
      ) : null}
      {item.prompt_zh ? <div>{item.prompt_zh}</div> : null}
    </div>
  );
}

function LedgerStrip({ beat, view }: { beat: CommercialBeat; view: ContentView }) {
  const ledger = beat.ledger || [];
  if (!ledger.length || view === "plan" || view === "sample" || view === "segment" || view === "draft") return null;
  const items = view === "assets" ? ledger.filter((x) => x.kind === "image") : ledger;
  if (!items.length) return null;
  return (
    <div className="asset-label-strip">
      {items.map((item: LedgerItem) => (
        <span
          className={`asset-label${item.selected ? " selected" : ""}${item.exists === false ? " missing" : ""}`}
          key={item.path || item.file}
        >
          {`${item.label_zh || item.label || (item.kind === "image" ? "用户素材" : "素材")}${item.selected ? " · 已选" : ""}`}
          {item.file ? <i>{` · ${item.file}`}</i> : null}
        </span>
      ))}
    </div>
  );
}

function GenerationDetails({ beat }: { beat: CommercialBeat }) {
  const rows = [
    ["文案", beat.copy_plan_zh],
    ["镜头", beat.shot_plan_zh],
    ["生成说明", beat.generation_prompt_zh],
    ["制作方式", formatCommercialMethod(beat)],
    ["Provider", beat.provider],
    ["Model", beat.model],
  ];
  return (
    <details className="beat-plan-fold">
      <summary>文案、镜头与生成说明</summary>
      <div className="beat-generation-grid">
        {rows.map(([label, value]) => (
          <div className="beat-generation-row" key={label}>
            <b>{label}</b>
            <span>{value || "—"}</span>
          </div>
        ))}
      </div>
    </details>
  );
}
