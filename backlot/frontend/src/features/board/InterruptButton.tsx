import { useState } from "react";
import { friendlyFromPayload } from "../library/api";
import { isCommercial, isProduceBusy } from "./model";
import type { BoardState } from "./types";

async function releaseLibraryRunner({ interrupt = false } = {}) {
  const response = await fetch("/api/library/release-runner", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true, interrupt: Boolean(interrupt) }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    return { ok: false, friendly_zh: friendlyFromPayload(payload, "无法中断当前项目。") };
  }
  return { ok: true, friendly_zh: payload.friendly_zh || "已中断。网页服务还在。" };
}

export function InterruptButton({ state }: { state: BoardState }) {
  const [feedback, setFeedback] = useState("");
  const [busyClick, setBusyClick] = useState(false);
  if (!isCommercial(state) || state.commercial?.completed) return null;
  const busy = isProduceBusy(state);
  const feedbackId = `interrupt-feedback:${state.project_id}`;
  return (
    <span className="export-tab-wrap">
      <button
        type="button"
        className="edit-tab-btn interrupt-tab-btn"
        disabled={busyClick}
        title={
          busy
            ? "停下当前生成，标为已中断，回到库页。网页服务还在。"
            : "停下 runner，标为已中断，回到库页。网页服务还在。"
        }
        onClick={async () => {
          if (busy && !window.confirm("正在生成。确认中断？项目会标为已中断，不会结束导出。")) {
            return;
          }
          setBusyClick(true);
          try {
            const result = await releaseLibraryRunner({ interrupt: busy });
            setFeedback(result.friendly_zh);
            if (result.ok) window.location.href = "/";
          } catch {
            setFeedback("中断失败。请留在本页重试。");
          } finally {
            setBusyClick(false);
          }
        }}
      >
        中断
      </button>
      <span id={feedbackId} className="export-tab-feedback" role="status">
        {feedback}
      </span>
    </span>
  );
}
