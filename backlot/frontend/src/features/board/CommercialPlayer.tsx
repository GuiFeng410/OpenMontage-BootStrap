import { mediaURL } from "./format";
import { commercialContentView } from "./model";
import { PersistentVideo } from "./PersistentVideo";
import type { BoardState, ContentView, StageEvidenceItem } from "./types";

type Props = { state: BoardState; selectedStage: string | null };

type StagePlayer = { label: string; path: string };

function canonicalPath(item?: StageEvidenceItem | null) {
  if (item?.path && item.exists === true) return item.path;
  return "";
}

function stagePlayerFor(view: ContentView, state: BoardState): StagePlayer | null {
  const evidence = state.commercial?.stage_evidence || {};
  if (view === "sample") {
    const path = canonicalPath(evidence.sample);
    return path ? { label: "试片", path } : null;
  }
  if (view === "draft") {
    const path = canonicalPath(evidence.draft);
    return path ? { label: "完整初稿", path } : null;
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
  if (view === "plan" || view === "assets" || view === "segment") return null;
  const current = stagePlayerFor(view, state);
  if (!current) return null;
  const src = mediaURL(state.project_id, current.path);
  const fileName = current.path.split("/").pop() || current.path;
  const showDownload =
    (view === "delivery" || view === "compose") && Boolean(state.commercial?.final_video?.exists);
  const downloadHref = state.commercial?.final_video?.path
    ? mediaURL(state.project_id, state.commercial.final_video.path)
    : src;
  return (
    <div>
      <div className="section-title">
        成片预览
        <span className="meta">{fileName}</span>
      </div>
      <div className="hint">用播放条控制进度。确认后点顶栏「结束并导出项目」。</div>
      <div className="render-hero">
        <PersistentVideo src={src} />
      </div>
      <div className="render-meta">
        <span className="v active">{current.label}</span>
      </div>
      {showDownload ? (
        <a className="commercial-final-download" href={downloadHref} download="final.mp4">
          下载终稿
        </a>
      ) : null}
    </div>
  );
}
