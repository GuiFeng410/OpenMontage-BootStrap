import { el } from "./lib.js";
import {
  buildExportIntent,
  EXPORT_PHRASE,
  submitDecisionIntent,
} from "./board-intent-submit.js";

export function renderExportButton(s) {
  if (s?.pipeline?.pipeline_type !== "bootstrap-commercial") return null;
  const completed = Boolean(s.commercial?.completed);
  const feedbackId = `export-feedback:${s.project_id}`;
  const button = el("button", {
    type: "button",
    class: "edit-tab-btn export-tab-btn" + (completed ? " done" : ""),
    disabled: completed ? "" : null,
    title: completed
      ? "这个项目已经结束并导出"
      : "把成片拷到本项目 exports/，并标记完成。没成片不会静默当完成。",
  }, completed ? "已结束并导出" : "结束并导出项目");

  if (!completed) {
    button.addEventListener("click", async () => {
      button.disabled = true;
      const slot = document.getElementById(feedbackId);
      try {
        const intent = await buildExportIntent({ projectId: s.project_id });
        const result = await submitDecisionIntent({ intent });
        if (slot) {
          slot.textContent = result.ok
            ? "已提交结束导出。请留在本页等待本机处理。"
            : `提交失败。请回聊天发送：${EXPORT_PHRASE}`;
        }
      } catch {
        if (slot) slot.textContent = `提交失败。请回聊天发送：${EXPORT_PHRASE}`;
      } finally {
        button.disabled = false;
      }
    });
  }

  return el("span", { class: "export-tab-wrap" },
    button,
    el("span", { id: feedbackId, class: "export-tab-feedback", role: "status" }));
}
