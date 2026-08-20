import { useState } from "react";
import { isCommercial } from "./model";
import { buildExportIntent, submitDecisionIntent } from "./intentSubmit";
import type { BoardState } from "./types";

export const EXPORT_REDIRECT_KEY = "backlot.exportRedirect";

export function ExportButton({ state }: { state: BoardState }) {
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  if (!isCommercial(state)) return null;
  const completed = Boolean(state.commercial?.completed);
  const ready = Boolean(state.commercial?.final_video?.exists);
  const feedbackId = `export-feedback:${state.project_id}`;
  return (
    <span className="export-tab-wrap">
      <button
        type="button"
        className={`edit-tab-btn export-tab-btn${completed ? " done" : ""}`}
        disabled={completed || !ready || busy}
        title={
          completed
            ? "这个项目已经结束并导出"
            : ready
              ? "把成片拷到本项目 exports/，标记完成，然后回到库页。"
              : "还没有成片，不能结束导出。要去做别的请点「中断」。"
        }
        onClick={async () => {
          if (completed || !ready || busy) return;
          setBusy(true);
          try {
            const intent = await buildExportIntent({ projectId: state.project_id });
            const result = await submitDecisionIntent({ intent });
            if (result.ok) {
              try {
                window.sessionStorage.setItem(EXPORT_REDIRECT_KEY, state.project_id);
              } catch {
                /* ignore */
              }
            }
            setFeedback(
              result.ok ? "已提交结束导出。完成后会回到库页。" : "提交失败。请留在本页刷新后重试。",
            );
          } catch {
            setFeedback("提交失败。请留在本页刷新后重试。");
          } finally {
            setBusy(false);
          }
        }}
      >
        {completed ? "已结束并导出" : "结束并导出项目"}
      </button>
      <span id={feedbackId} className="export-tab-feedback" role="status">
        {feedback || (!completed && !ready ? "还没有成片，不能结束导出。" : "")}
      </span>
    </span>
  );
}

export function maybeRedirectAfterExport(state: BoardState) {
  if (!state.commercial?.completed) return false;
  let pending = "";
  try {
    pending = window.sessionStorage.getItem(EXPORT_REDIRECT_KEY) || "";
  } catch {
    pending = "";
  }
  if (pending !== state.project_id) return false;
  try {
    window.sessionStorage.removeItem(EXPORT_REDIRECT_KEY);
  } catch {
    /* ignore */
  }
  window.location.href = "/";
  return true;
}
