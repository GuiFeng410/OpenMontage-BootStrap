import { useEffect, useMemo, useState } from "react";
import { mediaURL } from "./format";
import { commercialContentView } from "./model";
import { PersistentVideo } from "./PersistentVideo";
import type { BoardState, ContentView, DraftSegment, StageEvidenceItem } from "./types";

type Props = { state: BoardState; selectedStage: string | null };

type StagePlayer = { label: string; path: string };

function canonicalPath(item?: StageEvidenceItem | null) {
  if (item?.path && item.exists === true) return item.path;
  return "";
}

function playableSegmentPath(row: {
  path?: string | null;
  exists?: boolean;
  missing_path?: string | null;
  reason_code?: string | null;
  conflict_with?: string | null;
}) {
  if (row.path && row.exists === true) return row.path;
  // Legacy servers blanked the first segment when draft.path reused it.
  if (
    row.reason_code === "canonical_path_conflict" &&
    row.conflict_with === "draft" &&
    row.missing_path
  ) {
    return row.missing_path;
  }
  return "";
}

function draftSegments(state: BoardState): DraftSegment[] {
  const rows = state.commercial?.stage_evidence?.draft?.segments;
  if (Array.isArray(rows) && rows.length > 0) {
    return rows.map((row) => {
      const path = playableSegmentPath(row);
      return {
        ...row,
        path: path || row.path,
        exists: Boolean(path),
      };
    });
  }
  const fallback = state.commercial?.stage_evidence?.segment;
  if (!Array.isArray(fallback)) return [];
  return fallback
    .map((row) => {
      const beat = String(row.beat || "").trim();
      if (!beat) return null;
      const path = playableSegmentPath(row);
      return {
        beat,
        path: path || undefined,
        exists: Boolean(path),
        label_zh: `第 ${beat} 段`,
        status: row.status,
        missing_reason_zh: path ? undefined : row.missing_reason_zh,
        missing_path: row.missing_path,
        reason_code: row.reason_code,
        conflict_with: row.conflict_with,
      } satisfies DraftSegment;
    })
    .filter((row): row is DraftSegment => Boolean(row));
}

function stagePlayerFor(view: ContentView, state: BoardState): StagePlayer | null {
  const evidence = state.commercial?.stage_evidence || {};
  if (view === "sample") {
    const path = canonicalPath(evidence.sample);
    return path ? { label: "试片", path } : null;
  }
  if (view === "draft") {
    const segments = draftSegments(state).filter((row) => row.path && row.exists === true);
    if (segments[0]?.path) {
      return { label: segments[0].label_zh || `第 ${segments[0].beat || ""} 段`, path: segments[0].path };
    }
    const path = canonicalPath(evidence.draft);
    return path ? { label: "初稿", path } : null;
  }
  if (view === "compose") {
    const path = evidence.compose?.path && evidence.compose.exists === true ? evidence.compose.path : "";
    return path ? { label: "终稿候选", path } : null;
  }
  if (view === "delivery") {
    const path = evidence.delivery?.path && evidence.delivery.exists === true ? evidence.delivery.path : "";
    return path ? { label: "终稿", path } : null;
  }
  return null;
}

export function CommercialPlayer({ state, selectedStage }: Props) {
  const view = commercialContentView(state, selectedStage);
  const segments = useMemo(
    () => (view === "draft" ? draftSegments(state).filter((row) => Boolean(row.beat)) : []),
    [state, view],
  );
  const playable = useMemo(
    () => segments.filter((row) => row.path && row.exists === true),
    [segments],
  );
  const [selectedBeat, setSelectedBeat] = useState<string>("");

  useEffect(() => {
    if (view !== "draft") return;
    if (selectedBeat && playable.some((row) => row.beat === selectedBeat)) return;
    setSelectedBeat(playable[0]?.beat || segments[0]?.beat || "");
  }, [view, playable, segments, selectedBeat]);

  if (view === "plan" || view === "assets" || view === "segment") return null;

  const selected =
    view === "draft"
      ? playable.find((row) => row.beat === selectedBeat) || playable[0] || null
      : null;
  const current =
    view === "draft" && selected?.path
      ? { label: selected.label_zh || `第 ${selected.beat} 段`, path: selected.path }
      : stagePlayerFor(view, state);
  if (!current && view !== "draft") return null;
  if (view === "draft" && !current && segments.length === 0) return null;

  const src = current ? mediaURL(state.project_id, current.path) : "";
  const fileName = current?.path.split("/").pop() || current?.path || "";
  const showDownload =
    (view === "delivery" || view === "compose") && Boolean(state.commercial?.final_video?.exists);
  const downloadHref = state.commercial?.final_video?.path
    ? mediaURL(state.project_id, state.commercial.final_video.path)
    : src;
  const title = view === "draft" ? "初稿预览" : "成片预览";
  const hint =
    view === "draft"
      ? "点分段切换预览。确认后可点「通过初稿」；拒绝原因可选，拒绝后须按建议确认才能继续。"
      : view === "delivery"
        ? "确认成片后点顶栏「结束并导出项目」。成片未齐时请留在本页等待合成。"
        : "用播放条控制进度。确认后点顶栏「结束并导出项目」。";

  return (
    <div>
      <div className="section-title">
        {title}
        {fileName ? <span className="meta">{fileName}</span> : null}
      </div>
      <div className="hint">{hint}</div>
      {view === "draft" && segments.length > 0 ? (
        <div className="draft-segment-list" role="list">
          {segments.map((row) => {
            const ready = Boolean(row.path && row.exists === true);
            const active = row.beat === selectedBeat;
            return (
              <button
                key={row.beat}
                type="button"
                role="listitem"
                className={`draft-segment-chip${active ? " active" : ""}${ready ? "" : " missing"}`}
                disabled={!ready}
                onClick={() => ready && setSelectedBeat(String(row.beat))}
              >
                {row.label_zh || `第 ${row.beat} 段`}
                {!ready ? " · 缺失" : ""}
              </button>
            );
          })}
        </div>
      ) : null}
      {src ? (
        <div className="render-hero">
          <PersistentVideo src={src} />
        </div>
      ) : (
        <div className="hint">当前分段视频尚未就绪，请先等待各段齐套。</div>
      )}
      <div className="render-meta">
        <span className="v active">{current?.label || "初稿"}</span>
      </div>
      {showDownload ? (
        <a className="commercial-final-download" href={downloadHref} download="final.mp4">
          下载终稿
        </a>
      ) : null}
    </div>
  );
}
