import { useState } from "react";
import {
  assetNoteKey,
  loadAssetNotes,
  preferDecisionOption,
  saveAssetNotes,
  upsertAssetNote,
  type AssetNoteAction,
  type AssetNoteItem,
  type AssetNoteStore,
} from "./assetNotes";
import { fmtClock, fmtMoney, fmtMoneyCny, thumbURL } from "./format";
import { commercialAssignmentStatusZh, commercialContentView, isCommercial } from "./model";
import type { BoardEvent, BoardState, CommercialAsset, CommercialBeat } from "./types";

type Props = { state: BoardState; selectedStage: string | null };

export function EvidencePanels({ state, selectedStage }: Props) {
  const view = commercialContentView(state, selectedStage);
  return (
    <>
      {view === "plan" ? <AssetPrecheck state={state} selectedStage={selectedStage} /> : null}
      {view === "assets" ? <AssetInspection state={state} /> : null}
      {view === "assets" ? <UnusedAssets state={state} /> : null}
    </>
  );
}

export function ReviewFold({ state, selectedStage }: Props) {
  return (
    <details className="commercial-review-fold">
      <summary>回顾</summary>
      <div className="commercial-review-body">
        <BriefSummary state={state} />
        <PlanArchive state={state} selectedStage={selectedStage} />
        <Decisions state={state} />
        <Activity state={state} />
      </div>
    </details>
  );
}

function BriefSummary({ state }: { state: BoardState }) {
  const c = state.commercial;
  if (!c) return null;
  const b = c.brief_summary || {};
  const rows = [
    ["主题", b.theme],
    ["时长", b.duration_seconds ? `${b.duration_seconds}s` : null],
    ["制作档位", b.production_tier],
    ["视频渠道", b.video_channel],
    ["视频模型", b.video_model_zh],
    ["评审模式", b.review_mode_zh],
    ["画面构成", b.motion_mix_zh],
    ["整单上限", b.budget_cny != null ? fmtMoneyCny(b.budget_cny) : null],
    ["候选策略", b.candidate_mode_zh],
    ["风格", b.style_label_zh],
  ].filter(([, v]) => v) as [string, string][];
  if (!rows.length) return null;
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>方案摘要</h2>
        <span className="meta">brief.json</span>
      </div>
      <div className="panel-body commercial-summary">
        {rows.map(([label, value]) => (
          <div className="kv-row" key={label}>
            <span className="kv-k">{label}</span>
            <span className="kv-v">{value}</span>
          </div>
        ))}
        <details className="tech-details">
          <summary>技术详情</summary>
          <div className="tech-body">
            {b.video_model ? <div>{`模型 · ${b.video_model}`}</div> : null}
            {c.cost_cny?.spent_usd != null ? <div>{`美元账本 · ${fmtMoney(c.cost_cny.spent_usd)}`}</div> : null}
            <div>{`管线 · ${state.pipeline.pipeline_type}`}</div>
          </div>
        </details>
      </div>
    </div>
  );
}

function PlanArchive({ state, selectedStage }: Props) {
  const archive = state.commercial?.plan_archive || {};
  const b = state.commercial?.brief_summary || {};
  const view = commercialContentView(state, selectedStage);
  if (view === "plan" && !archive.overall_prompt_zh && !archive.has_video_plan) return null;
  const flags = [
    archive.has_brief ? "brief✓" : "brief✗",
    archive.has_video_plan ? "video_plan✓" : "video_plan✗",
    archive.has_segment_cards ? `分段×${archive.segment_count || 0}` : "segment_cards✗",
  ].join(" · ");
  return (
    <div className="panel commercial-plan-archive">
      <div className="panel-head">
        <h2>已确认方案档案</h2>
        <span className="meta">跨阶段保留</span>
      </div>
      <div className="panel-body commercial-summary">
        <div className="kv-row">
          <span className="kv-k">封板状态</span>
          <span className="kv-v">{archive.sealed_zh || "—"}</span>
        </div>
        <div className="kv-row">
          <span className="kv-k">落盘检查</span>
          <span className="kv-v">{flags}</span>
        </div>
        {b.theme ? (
          <div className="kv-row">
            <span className="kv-k">主题</span>
            <span className="kv-v">{b.theme}</span>
          </div>
        ) : null}
        {archive.overall_prompt_zh ? (
          <details className="tech-details" open={view !== "plan"}>
            <summary>整体步骤方案</summary>
            <div className="tech-body" style={{ whiteSpace: "pre-line" }}>
              {archive.overall_prompt_zh}
            </div>
          </details>
        ) : view !== "plan" ? (
          <div className="hint">尚未写入整体方案文案（segment_cards.overall_prompt_zh）。</div>
        ) : null}
      </div>
    </div>
  );
}

function Decisions({ state }: { state: BoardState }) {
  const rows = state.commercial?.decisions || [];
  if (!rows.length) return null;
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>已确认决定</h2>
        <span className="meta">decision_log</span>
      </div>
      <div className="panel-body">
        {rows
          .slice()
          .reverse()
          .slice(0, 12)
          .map((d, i) => (
            <div className="decision commercial-decision" key={`${d.subject || ""}-${i}`}>
              <div className="d-cat">{d.category_zh || d.category || "决定"}</div>
              <div className="d-pick">
                {`${d.subject || ""} `}
                <span className="arrow">→</span>
                {` ${d.selected_label_zh || d.selected || ""}`}
              </div>
              {d.user_response_text ? (
                <div className="d-why">{`你的回复：${d.user_response_text}`}</div>
              ) : d.reason ? (
                <div className="d-why">{d.reason}</div>
              ) : null}
            </div>
          ))}
      </div>
    </div>
  );
}

function Activity({ state }: { state: BoardState }) {
  const events = state.events || [];
  if (!events.length) return null;
  const zh = isCommercial(state);
  const rows = closedActivityRows(events);
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>{zh ? "制作动态" : "Activity"}</h2>
        <span className="meta">events.jsonl</span>
      </div>
      <div className="panel-body">
        {rows.slice(-10).reverse().map((ev, i) => (
          <div className="act-row" key={`${ev.ts || ""}-${ev.tool || ""}-${i}`}>
            <span className="t">{fmtClock(ev.ts)}</span>
            <span className="tool">{ev.tool || ""}</span>
            <span className="target">{ev.scene_id || ""}</span>
            <ActivityStatus ev={ev} zh={zh} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ActivityStatus({ ev, zh }: { ev: BoardEvent; zh: boolean }) {
  if (ev.event === "finish") {
    const ok = ev.success !== false;
    return (
      <span className={`status ${ok ? "ok" : "err"}`}>
        {`${ok ? "✓" : "✕"}${ev.duration_s != null ? ` ${Number(ev.duration_s).toFixed(1)}s` : ""}${ev.cost_usd ? ` ${fmtMoney(ev.cost_usd)}` : ""}`}
      </span>
    );
  }
  if (ev.event === "error") return <span className="status err">✕</span>;
  return <span className="status run">{zh ? "● 运行中" : "● running"}</span>;
}

function closedActivityRows(events: BoardEvent[]) {
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
  return rows;
}

function precheckProblemRows(state: BoardState) {
  const precheck = state.commercial?.asset_precheck || {};
  const summary = precheck.summary || {};
  const entries = Array.isArray(precheck.entries) ? precheck.entries : [];
  const svgCount = entries.filter((entry) =>
    (entry.issues || []).some((issue) => /svg|unsafe/i.test(issue)),
  ).length;
  const rows: [string, string][] = [];
  if (summary.low_resolution_count) {
    rows.push(["低分辨率", `${summary.low_resolution_count} 张`]);
  }
  if (summary.duplicate_group_count) {
    rows.push(["重复文件", `${summary.duplicate_group_count} 组`]);
  }
  if (svgCount) rows.push(["危险 SVG", `${svgCount} 张`]);
  if (summary.vision_enriched) {
    rows.push(["识图", summary.vision_model ? `已调用 · ${summary.vision_model}` : "已调用"]);
  }
  return { summary, entries, rows };
}

function AssetPrecheck({ state }: Props) {
  const precheck = state.commercial?.asset_precheck || {};
  const summary = precheck.summary || {};
  const entries = Array.isArray(precheck.entries) ? precheck.entries : [];
  if (!summary.total_images && !summary.needs_user_attention && !entries.length) return null;
  const { rows } = precheckProblemRows(state);
  return (
    <div className="panel commercial-precheck-panel">
      <div className="panel-head">
        <h2>素材预检</h2>
        <span className="meta">方案确认前置</span>
      </div>
      <div className="panel-body commercial-summary">
        <div className="kv-row">
          <span className="kv-k">已扫描图片</span>
          <span className="kv-v">{`${summary.total_images || entries.length} 张`}</span>
        </div>
        {rows.map(([label, value]) => (
          <div className="kv-row" key={label}>
            <span className="kv-k">{label}</span>
            <span className="kv-v">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const AI_STATUSES = new Set(["i2i_planned", "generating", "review_pending", "approved", "failed"]);
const REUSE_FILLS = new Set(["none"]);
const SKIP_FILLS = new Set(["concept_only"]);

function beatUsesPath(beat: CommercialBeat, path?: string) {
  if (!path) return false;
  if (beat.reference_path === path || beat.asset_path === path || beat.ref === path) return true;
  const bags = [...(beat.ledger || []), ...(beat.planned_entries || [])];
  return bags.some((item) => item.path === path);
}

function beatUsageLabel(beat: CommercialBeat) {
  return [beat.beat, beat.need_detail_zh || beat.asset_plan_zh || commercialAssignmentStatusZh(beat)]
    .filter(Boolean)
    .join(" · ");
}

function isSkipBeat(beat: CommercialBeat) {
  return SKIP_FILLS.has(String(beat.gap_fill || "")) || /不补/.test(beat.asset_plan_zh || "");
}

function isReuseBeat(beat: CommercialBeat) {
  return (
    beat.assignment_status === "reuse_pending" ||
    beat.assignment_status === "reuse_approved" ||
    beat.reuse_status === "reuse_pending" ||
    beat.reuse_status === "reuse_approved" ||
    REUSE_FILLS.has(String(beat.gap_fill || ""))
  );
}

function isAiBeat(beat: CommercialBeat) {
  if (isSkipBeat(beat) || isReuseBeat(beat)) return false;
  return (
    AI_STATUSES.has(String(beat.assignment_status || "")) ||
    beat.gap_fill === "i2i" ||
    Boolean(beat.candidate_previews?.length)
  );
}

function AssetInspection({ state }: { state: BoardState }) {
  const assets = state.commercial?.assets || [];
  const beats = state.commercial?.beats || [];
  const aiBeats = beats.filter(isAiBeat);
  const reuseBeats = beats.filter((beat) => isReuseBeat(beat) && !isSkipBeat(beat));
  const skipBeats = beats.filter(isSkipBeat);
  const otherBeats = reuseBeats.length + skipBeats.length;
  const { rows: problemRows } = precheckProblemRows(state);
  const notes = useAssetNotes(state.project_id, "assets_gate");

  if (!assets.length && !aiBeats.length && !otherBeats && !problemRows.length) return null;

  return (
    <div className="panel commercial-assets-panel">
      <div className="panel-head">
        <h2>素材检查</h2>
        <span className="meta">用户原图 / AI / 复用与不补</span>
      </div>
      <div className="panel-body commercial-summary">
        <div className="kv-row">
          <span className="kv-k">分区</span>
          <span className="kv-v">
            {`用户原图 ${assets.length} · AI ${aiBeats.length} · 复用/不补 ${otherBeats}`}
          </span>
        </div>
        {problemRows.map(([label, value]) => (
          <div className="kv-row" key={label}>
            <span className="kv-k">{label}</span>
            <span className="kv-v">{value}</span>
          </div>
        ))}
        {assets.length ? (
          <AssetSection title={`用户原图 / 补传（${assets.length}）`} open>
            <div className="asset-grid commercial-assets-details">
              {assets.map((img) => (
                <UserAssetCard
                  key={img.path || img.file}
                  state={state}
                  img={img}
                  beats={beats.filter((beat) => beatUsesPath(beat, img.path))}
                  notes={notes}
                />
              ))}
            </div>
          </AssetSection>
        ) : null}
        {aiBeats.length ? (
          <AssetSection title={`AI 生成（${aiBeats.length}）`} open>
            <div className="asset-grid commercial-assets-details">
              {aiBeats.map((beat) => (
                <AiBeatCard key={beat.beat || beat.time} state={state} beat={beat} notes={notes} />
              ))}
            </div>
          </AssetSection>
        ) : null}
        {otherBeats ? (
          <AssetSection title={`复用与不补（${otherBeats}）`} open>
            <div className="asset-grid">
              {reuseBeats.map((beat) => (
                <ReuseSkipCard
                  key={`reuse-${beat.beat}`}
                  state={state}
                  beat={beat}
                  kind="reuse"
                  notes={notes}
                />
              ))}
              {skipBeats.map((beat) => (
                <ReuseSkipCard
                  key={`skip-${beat.beat}`}
                  state={state}
                  beat={beat}
                  kind="skip"
                  notes={notes}
                />
              ))}
            </div>
          </AssetSection>
        ) : null}
      </div>
    </div>
  );
}

function AssetSection({
  title,
  open,
  children,
}: {
  title: string;
  open?: boolean;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(Boolean(open));
  return (
    <details
      className="asset-inspect-section"
      open={expanded}
      onToggle={(event) => setExpanded((event.currentTarget as HTMLDetailsElement).open)}
    >
      <summary>{title}</summary>
      {children}
    </details>
  );
}

function useAssetNotes(projectId: string, stage: string) {
  const storage = typeof window === "undefined" ? undefined : window.sessionStorage;
  const [store, setStore] = useState<AssetNoteStore>(() =>
    storage
      ? loadAssetNotes(storage, projectId, stage)
      : { version: "1.0", project_id: projectId, stage, items: {} },
  );
  const apply = (next: AssetNoteStore) => {
    setStore(next);
    if (storage) saveAssetNotes(storage, next);
  };
  return { store, apply };
}

function noteFor(store: AssetNoteStore, key: string): AssetNoteItem | undefined {
  return store.items[key];
}

function UserAssetCard({
  state,
  img,
  beats,
  notes,
}: {
  state: BoardState;
  img: CommercialAsset;
  beats: CommercialBeat[];
  notes: ReturnType<typeof useAssetNotes>;
}) {
  const key = assetNoteKey("user", beats[0]?.beat, img.path);
  const item = noteFor(notes.store, key);
  const rejected = item?.action === "reject";
  const patch = (next: { action?: AssetNoteAction; text?: string }) =>
    notes.apply(
      upsertAssetNote(notes.store, key, {
        kind: "user",
        beat: beats[0]?.beat,
        path: img.path,
        label: img.file || "用户原图",
        action: next.action ?? item?.action ?? "",
        text: next.text ?? item?.text ?? "",
      }),
    );
  return (
    <div className={`asset-card${img.exists ? "" : " missing"}`}>
      {img.exists && img.path ? (
        <img src={thumbURL(state.project_id, img.path, 320)} loading="lazy" alt={img.file || ""} />
      ) : (
        <div className="asset-missing">缺失</div>
      )}
      <div className="asset-meta">
        <b>{img.role_zh || "用户原图"}</b>
        <span>{img.file}</span>
        {beats.length ? (
          <span className="asset-hint">{beats.map(beatUsageLabel).join("；")}</span>
        ) : (
          <span className="asset-hint">未分配到段落</span>
        )}
        {img.hero_only_motion ? <span className="asset-hint">仅运镜，不作 I2V 锚点</span> : null}
        <div className="asset-card-actions">
          <button
            type="button"
            className={`asset-chip${rejected ? " selected" : ""}`}
            aria-pressed={rejected}
            onClick={() => patch({ action: rejected ? "" : "reject" })}
          >
            这张不好
          </button>
        </div>
        <textarea
          className="asset-card-note"
          rows={2}
          placeholder="选填：这张哪里不好"
          aria-label="选填：这张哪里不好"
          value={item?.text || ""}
          onChange={(event) => patch({ text: event.currentTarget.value })}
        />
      </div>
    </div>
  );
}

function AiBeatCard({
  state,
  beat,
  notes,
}: {
  state: BoardState;
  beat: CommercialBeat;
  notes: ReturnType<typeof useAssetNotes>;
}) {
  const preview = (beat.candidate_previews || [])[0];
  const status = beat.assignment_status || "";
  const path = preview?.path;
  const key = assetNoteKey("ai", beat.beat, path);
  const item = noteFor(notes.store, key);
  const reviewing = status === "review_pending";
  const placeholder =
    status === "generating" ? "生成中" : status === "i2i_planned" || !path ? "待生成" : null;
  const patch = (next: { action?: AssetNoteAction; text?: string }) =>
    notes.apply(
      upsertAssetNote(notes.store, key, {
        kind: "ai",
        beat: beat.beat,
        path,
        label: `${beat.beat || "补图"} AI生成`,
        action: next.action ?? item?.action ?? "",
        text: next.text ?? item?.text ?? "",
      }),
    );
  return (
    <div className={`asset-card${path ? "" : " missing"}`}>
      {path ? (
        <img src={thumbURL(state.project_id, path, 320)} loading="lazy" alt={preview?.file || ""} />
      ) : (
        <div className="asset-missing asset-placeholder">{placeholder || "待生成"}</div>
      )}
      <div className="asset-meta">
        <b>
          {beatUsageLabel(beat)}
          <span className="asset-badge-ai">AI生成</span>
        </b>
        <span>{commercialAssignmentStatusZh(beat)}</span>
        {reviewing ? (
          <div className="asset-card-actions">
            <button
              type="button"
              className={`asset-chip${item?.action === "ok" ? " selected" : ""}`}
              aria-pressed={item?.action === "ok"}
              onClick={() => patch({ action: item?.action === "ok" ? "" : "ok" })}
            >
              通过
            </button>
            <button
              type="button"
              className={`asset-chip${item?.action === "redo" ? " selected" : ""}`}
              aria-pressed={item?.action === "redo"}
              onClick={() => {
                patch({ action: "redo" });
                preferDecisionOption("generate");
              }}
            >
              重做
            </button>
          </div>
        ) : null}
        <textarea
          className="asset-card-note"
          rows={2}
          placeholder={reviewing ? "选填：这张补图的意见" : "选填：这一段的意见"}
          aria-label="选填补图意见"
          value={item?.text || ""}
          onChange={(event) => patch({ text: event.currentTarget.value })}
        />
      </div>
    </div>
  );
}

function ReuseSkipCard({
  state,
  beat,
  kind,
  notes,
}: {
  state: BoardState;
  beat: CommercialBeat;
  kind: "reuse" | "skip";
  notes: ReturnType<typeof useAssetNotes>;
}) {
  const path = beat.reference_path || beat.asset_path;
  const key = assetNoteKey(kind, beat.beat, path);
  const item = noteFor(notes.store, key);
  const label = kind === "skip" ? `${beat.beat || ""} 明确不补` : `${beat.beat || ""} 复用`;
  return (
    <div className={`asset-card${path ? "" : " missing"}`}>
      {path ? (
        <img src={thumbURL(state.project_id, path, 320)} loading="lazy" alt={label} />
      ) : (
        <div className="asset-missing asset-placeholder">{kind === "skip" ? "不补图" : "复用待确认"}</div>
      )}
      <div className="asset-meta">
        <b>{label}</b>
        <span>{beat.asset_plan_zh || commercialAssignmentStatusZh(beat)}</span>
        <textarea
          className="asset-card-note"
          rows={2}
          placeholder="选填：这段的意见"
          aria-label="选填：这段的意见"
          value={item?.text || ""}
          onChange={(event) =>
            notes.apply(
              upsertAssetNote(notes.store, key, {
                kind,
                beat: beat.beat,
                path,
                label,
                action: "",
                text: event.currentTarget.value,
              }),
            )
          }
        />
      </div>
    </div>
  );
}

function UnusedAssets({ state }: { state: BoardState }) {
  const assets = Array.isArray(state.commercial?.unused_assets) ? state.commercial.unused_assets : [];
  if (!assets.length) return null;
  return (
    <details className="panel commercial-unused-assets">
      <summary>
        {`未使用素材（${assets.length}）`}
        <span className="meta"> · 展开核对</span>
      </summary>
      <div className="panel-body commercial-unused-assets-list">
        {assets.map((item) => (
          <div className="commercial-unused-asset" data-path={item.path || ""} key={item.path || item.file}>
            <b>{item.file || (item.path || "").split("/").pop() || "未命名素材"}</b>
            <span>{item.reason || "未分配到任何 canonical Beat"}</span>
            <code>{item.path || "项目内路径待补齐"}</code>
            <span className="status-chip">{item.status || "unassigned"}</span>
          </div>
        ))}
      </div>
    </details>
  );
}
