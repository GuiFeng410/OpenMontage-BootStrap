import { fmtClock, fmtMoney, fmtMoneyCny, thumbURL } from "./format";
import { commercialContentView, isCommercial } from "./model";
import type { BoardEvent, BoardState } from "./types";

type Props = { state: BoardState; selectedStage: string | null };

export function EvidencePanels({ state, selectedStage }: Props) {
  const view = commercialContentView(state, selectedStage);
  return (
    <>
      {view === "plan" || view === "assets" ? <AssetPrecheck state={state} selectedStage={selectedStage} /> : null}
      {view === "assets" ? <AssetPool state={state} /> : null}
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

function AssetPrecheck({ state, selectedStage }: Props) {
  const view = commercialContentView(state, selectedStage);
  const precheck = state.commercial?.asset_precheck || {};
  const summary = precheck.summary || {};
  const entries = Array.isArray(precheck.entries) ? precheck.entries : [];
  if (!summary.total_images && !summary.needs_user_attention && !entries.length) return null;
  const rows: [string, string | null | undefined][] = [
    ["已扫描图片", summary.total_images != null ? `${summary.total_images} 张` : null],
    ["低分辨率", summary.low_resolution_count ? `${summary.low_resolution_count} 张` : "无"],
    ["重复文件", summary.duplicate_group_count ? `${summary.duplicate_group_count} 组` : "无"],
    [
      "分类方式",
      summary.vision_enriched
        ? `识图模型${summary.vision_model ? ` · ${summary.vision_model}` : ""}`
        : "仅文件扫描（未调用识图模型）",
    ],
  ];
  return (
    <div className="panel commercial-precheck-panel">
      <div className="panel-head">
        <h2>{view === "assets" ? "素材检查 · 预检" : "素材预检"}</h2>
        <span className="meta">{view === "assets" ? "文件扫描 · 分辨率/重复检测" : "方案确认前置"}</span>
      </div>
      <div className="panel-body commercial-summary">
        {rows
          .filter(([, value]) => value != null)
          .map(([label, value]) => (
            <div className="kv-row" key={label}>
              <span className="kv-k">{label}</span>
              <span className="kv-v">{value}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

function AssetPool({ state }: { state: BoardState }) {
  const assets = state.commercial?.assets || [];
  if (!assets.length) return null;
  const roleCounts = new Map<string, number>();
  for (const img of assets) {
    const role = img.role_zh || "素材";
    roleCounts.set(role, (roleCounts.get(role) || 0) + 1);
  }
  return (
    <div className="panel commercial-assets-panel">
      <div className="panel-head">
        <h2>素材检查</h2>
        <span className="meta">身份与角度</span>
      </div>
      <div className="panel-body commercial-summary">
        <div className="kv-row">
          <span className="kv-k">素材总数</span>
          <span className="kv-v">{`共 ${assets.length} 张`}</span>
        </div>
        <div className="kv-row">
          <span className="kv-k">用途</span>
          <span className="kv-v">
            {[...roleCounts.entries()].map(([role, count]) => `${role}×${count}`).join(" · ")}
          </span>
        </div>
        <details className="tech-details commercial-assets-details">
          <summary>展开图片清单</summary>
          <div className="asset-grid">
            {assets.map((img) => (
              <div className={`asset-card${img.exists ? "" : " missing"}`} key={img.path || img.file}>
                {img.exists && img.path ? (
                  <img src={thumbURL(state.project_id, img.path, 320)} loading="lazy" alt={img.file || ""} />
                ) : (
                  <div className="asset-missing">缺失</div>
                )}
                <div className="asset-meta">
                  <b>{img.role_zh}</b>
                  <span>{img.file}</span>
                  {img.hero_only_motion ? <span className="asset-hint">仅运镜，不作 I2V 锚点</span> : null}
                </div>
              </div>
            ))}
          </div>
        </details>
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
