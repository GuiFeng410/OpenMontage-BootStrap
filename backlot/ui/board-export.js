import { el } from "./lib.js";
import {
  buildExportIntent,
  submitDecisionIntent,
} from "./board-intent-submit.js";

export const EXPORT_REDIRECT_KEY = "backlot.exportRedirect";

export function renderExportButton(s) {
  if (s?.pipeline?.pipeline_type !== "bootstrap-commercial") return null;
  const completed = Boolean(s.commercial?.completed);
  const ready = Boolean(s.commercial?.final_video?.exists);
  const feedbackId = `export-feedback:${s.project_id}`;
  const button = el("button", {
    type: "button",
    class: "edit-tab-btn export-tab-btn" + (completed ? " done" : ""),
    disabled: completed || !ready ? "" : null,
    title: completed
      ? "这个项目已经结束并导出"
      : ready
        ? "把成片拷到本项目 exports/，标记完成，然后回到库页。"
        : "成片出现后即可在本页导出。没有成片不会标记完成。",
  }, completed ? "已结束并导出" : "结束并导出项目");

  if (!completed && ready) {
    button.addEventListener("click", async () => {
      button.disabled = true;
      const slot = document.getElementById(feedbackId);
      try {
        const intent = await buildExportIntent({ projectId: s.project_id });
        const result = await submitDecisionIntent({ intent });
        if (result.ok) {
          try {
            window.sessionStorage.setItem(EXPORT_REDIRECT_KEY, s.project_id);
          } catch {
            /* ignore */
          }
        }
        if (slot) {
          slot.textContent = result.ok
            ? "已提交结束导出。完成后会回到库页。"
            : "提交失败。请留在本页刷新后重试。";
        }
      } catch {
        if (slot) slot.textContent = "提交失败。请留在本页刷新后重试。";
      } finally {
        button.disabled = false;
      }
    });
  }

  return el("span", { class: "export-tab-wrap" },
    button,
    el("span", { id: feedbackId, class: "export-tab-feedback", role: "status" }));
}

export function maybeRedirectAfterExport(s) {
  if (!s?.commercial?.completed) return false;
  let pending = "";
  try {
    pending = window.sessionStorage.getItem(EXPORT_REDIRECT_KEY) || "";
  } catch {
    pending = "";
  }
  if (pending !== s.project_id) return false;
  try {
    window.sessionStorage.removeItem(EXPORT_REDIRECT_KEY);
  } catch {
    /* ignore */
  }
  window.location.href = "/";
  return true;
}
