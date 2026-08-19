import { el } from "./lib.js";

export const RUNNER_GONE_ZH = "本机 runner 未绑定本项目。请回库页点「继续这个项目」。";

export function runnerBoundToProject(s) {
  if (s?.commercial?.completed) return true;
  const bind = s?.commercial?.runner_bind;
  if (bind && typeof bind === "object") return Boolean(bind.bound);
  return Boolean(s?.commercial?.runner_status?.runner_alive);
}

export async function stopBacklotRuntime({ interrupt = false } = {}) {
  const response = await fetch("/api/runtime/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true, interrupt }),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) {
    const detail = payload.detail;
    const message = (detail && (detail.friendly_zh || detail.detail))
      || payload.friendly_zh
      || "无法退出看板。";
    return { ok: false, status: response.status, friendly_zh: message };
  }
  return {
    ok: true,
    friendly_zh: payload.friendly_zh || "看板即将退出。",
  };
}

export function isProduceBusy(s) {
  const phase = s?.commercial?.runner_status?.phase;
  return phase === "producing" || phase === "queued" || phase === "applying";
}

export function renderQuitButton(s) {
  const feedbackId = s?.project_id
    ? `quit-feedback:${s.project_id}`
    : "quit-feedback:library";
  const busy = Boolean(s && isProduceBusy(s));
  const button = el("button", {
    type: "button",
    class: "edit-tab-btn quit-tab-btn",
    disabled: busy ? "" : null,
    title: busy
      ? "正在出片，不能退出看板，以免中断生成。"
      : "关掉本机网页服务和 runner。不结束当前项目。",
  }, "退出看板");
  button.addEventListener("click", async () => {
    const slot = document.getElementById(feedbackId);
    button.disabled = true;
    try {
      const result = await stopBacklotRuntime();
      if (slot) slot.textContent = result.friendly_zh;
      if (result.ok) {
        window.setTimeout(() => {
          document.body.replaceChildren(
            el("div", { class: "wrap" },
              el("div", { class: "notice" }, result.friendly_zh || "看板已退出。")),
          );
        }, 600);
      }
    } catch {
      if (slot) slot.textContent = "退出失败。请留在本页重试。";
    } finally {
      button.disabled = busy ? true : false;
    }
  });
  return el("span", { class: "export-tab-wrap" },
    button,
    el("span", { id: feedbackId, class: "export-tab-feedback", role: "status" }));
}
