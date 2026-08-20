import { useState } from "react";
import { friendlyFromPayload } from "./api";

async function stopBacklotRuntime({ interrupt = false } = {}) {
  const response = await fetch("/api/runtime/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true, interrupt }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    return { ok: false, friendly_zh: friendlyFromPayload(payload, "无法退出看板。") };
  }
  return { ok: true, friendly_zh: payload.friendly_zh || "看板即将退出。" };
}

export function QuitButton() {
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <span className="export-tab-wrap">
      <button
        type="button"
        className="edit-tab-btn quit-tab-btn"
        title="关掉本机网页服务和 runner。当前项目标为已中断，不是结束导出。"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const result = await stopBacklotRuntime();
            setFeedback(result.friendly_zh);
            if (result.ok) {
              window.setTimeout(() => {
                document.body.replaceChildren();
                const wrap = document.createElement("div");
                wrap.className = "wrap";
                const notice = document.createElement("div");
                notice.className = "notice";
                notice.textContent = result.friendly_zh || "看板已退出。";
                wrap.append(notice);
                document.body.append(wrap);
              }, 600);
            }
          } catch {
            setFeedback("退出失败。请留在本页重试。");
          } finally {
            setBusy(false);
          }
        }}
      >
        退出看板
      </button>
      <span id="quit-feedback:library" className="export-tab-feedback" role="status">
        {feedback}
      </span>
    </span>
  );
}
