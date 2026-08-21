import { CONTENT_VIEW_LABEL, commercialContentView, commercialFocusStage, stageConclusionZh } from "./model";
import type { BoardState } from "./types";

type Props = { state: BoardState; selectedStage: string | null };

export function StageStatusCard({ state, selectedStage }: Props) {
  const view = commercialContentView(state, selectedStage);
  const focus = commercialFocusStage(state, selectedStage);
  const st = (state.stages || []).find((x) => x.name === focus) || { name: focus, status: "" };
  const label = st.label_zh || CONTENT_VIEW_LABEL[view] || focus;
  const rows = stageStatusRows(state, view).filter(([, value]) => value);
  return (
    <div className="notice commercial-stage-status">
      <span>◈</span>
      <div className="commercial-stage-status-body commercial-summary">
        <div className="commercial-stage-status-kicker">
          <b>{label}</b>
          <span className="status-chip">{stageConclusionZh(st.status)}</span>
        </div>
        {rows.map(([key, value]) => (
          <div className="kv-row" key={key}>
            <span className="kv-k">{key}</span>
            <span className="kv-v">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function stageStatusRows(s: BoardState, view: string): [string, string | null | undefined][] {
  const b = s.commercial?.brief_summary || {};
  const evidence = s.commercial?.stage_evidence || {};
  if (view === "plan") {
    return [
      ["主题", b.theme],
      ["时长", b.duration_seconds ? `${b.duration_seconds}s` : null],
      ["制作档", b.production_tier],
      ["视频渠道", b.video_channel || b.video_model_zh],
    ];
  }
  if (view === "assets") {
    const beats = s.commercial?.beats || [];
    const unused = s.commercial?.unused_assets || [];
    const selected = (s.commercial?.assets || []).filter((item) => item.selected !== false);
    const missing = beats.filter(
      (beat) => beat.assignment_status === "missing" || beat.assignment_status === "assignment_conflict",
    );
    const conclusion = !beats.length ? "待检查" : missing.length ? `有缺口 ${missing.length} 段` : "已齐";
    return [
      ["素材结论", conclusion],
      ["选用", `${selected.length} 张`],
      ["未分配", unused.length ? `${unused.length} 张` : "无"],
    ];
  }
  if (view === "sample") {
    const sample = evidence.sample || {};
    return [
      ["试片", sample.status || "待生成"],
      ["时长", sample.duration_seconds != null ? `${sample.duration_seconds}s` : null],
    ];
  }
  if (view === "segment") {
    const beats = s.commercial?.beats || [];
    const segs = Array.isArray(evidence.segment) ? evidence.segment : [];
    const total = beats.length || segs.length;
    const done =
      segs.filter((item) => item.exists).length || beats.filter((beat) => beat.asset_path).length;
    const job = s.commercial?.produce_job || {};
    const current =
      Array.isArray(job.beat_ids) && job.beat_ids.length
        ? `当前 ${job.beat_ids.filter(Boolean).join("、")}`
        : job.friendly_zh || job.batch_id || null;
    return [
      ["进度", total ? `${done}/${total} 段` : "待开始"],
      ["当前", current],
    ];
  }
  if (view === "draft") {
    const draft = evidence.draft || {};
    const issues = draft.issue_segments || [];
    return [["初稿", issues.length ? `有问题 ${issues.length} 条` : draft.path ? "通过" : "待审查"]];
  }
  if (view === "compose") {
    const compose = evidence.compose || {};
    const probe = compose.technical_probe || {};
    const issues = [...(probe.issues || []), ...(compose.issues_found || [])];
    return [
      ["技术检查", issues.length ? `${issues.length} 个问题` : compose.status || "待检查"],
      ["时长", probe.duration_seconds != null ? `${probe.duration_seconds}s` : null],
    ];
  }
  if (view === "delivery") {
    const delivery = evidence.delivery || {};
    const ready = Boolean(s.commercial?.final_video?.exists);
    return [
      ["成片", ready ? "已就绪，可预览导出" : "合成中，请留在本页"],
      ["质量", delivery.quality_status && delivery.quality_status !== "待技术检查" ? delivery.quality_status : null],
    ];
  }
  return [];
}
