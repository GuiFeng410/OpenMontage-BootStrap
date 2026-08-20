import { useState } from "react";
import { friendlyFromPayload, type Occupant } from "./api";

async function releaseLibraryRunner({ interrupt = false } = {}) {
  const response = await fetch("/api/library/release-runner", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true, interrupt: Boolean(interrupt) }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
      friendly_zh: friendlyFromPayload(payload, "无法中断当前项目。"),
    };
  }
  return {
    ok: true,
    status: response.status,
    friendly_zh: payload.friendly_zh || "已中断。网页服务还在。",
  };
}

export function OccupantBar({
  occupant,
  onReleased,
}: {
  occupant: Occupant;
  onReleased: () => Promise<void> | void;
}) {
  const [feedback, setFeedback] = useState("");
  const [releasing, setReleasing] = useState(false);
  const visible = Boolean(occupant.project_id);

  return (
    <section
      className="library-occupant"
      id="runner-occupant"
      hidden={!visible}
      aria-live="polite"
    >
      <p className="library-occupant-title">
        {visible ? `本机正在做：${occupant.title}` : ""}
      </p>
      <p className="library-occupant-hint">
        中断只停 runner，不结束项目，网页还在。要关掉网页请点「退出看板」。结束导出需要成片。
      </p>
      <div className="library-occupant-actions">
        <button
          type="button"
          className="library-occupant-release"
          disabled={releasing}
          onClick={async () => {
            if (releasing) return;
            setReleasing(true);
            setFeedback("正在中断…");
            try {
              let result = await releaseLibraryRunner();
              if (!result.ok && result.status === 409) {
                const ok = window.confirm(
                  "正在生成。确认中断？项目会标为已中断，不会结束导出。",
                );
                if (!ok) {
                  setFeedback("已取消。生成仍在继续。");
                  return;
                }
                result = await releaseLibraryRunner({ interrupt: true });
              }
              setFeedback(result.friendly_zh);
              if (result.ok) await onReleased();
            } catch {
              setFeedback("中断失败。请留在本页重试。");
            } finally {
              setReleasing(false);
            }
          }}
        >
          中断并做别的
        </button>
        <span className="library-occupant-feedback" role="status">
          {feedback}
        </span>
      </div>
    </section>
  );
}
