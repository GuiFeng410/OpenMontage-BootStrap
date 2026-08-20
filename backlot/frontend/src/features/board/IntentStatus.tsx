import type { InteractionIntent } from "./types";

const INTENT_STATUS_ZH: Record<string, string> = {
  pending: "待确认",
  planned: "已汇总",
  approved: "聊天已确认",
  applied: "已执行",
  superseded: "已作废",
  rejected: "已拒绝",
  failed: "失败",
};

export function IntentStatus({ intents }: { intents?: InteractionIntent[] }) {
  if (!Array.isArray(intents) || !intents.length) return null;
  const latestByStage = new Map<string, InteractionIntent>();
  for (const item of intents) {
    if (!item || item.status === "superseded") continue;
    latestByStage.set(String(item.stage || "unknown"), item);
  }
  const rows = Array.from(latestByStage.values());
  if (!rows.length) return null;
  return (
    <details className="notice commercial-intent-status commercial-fold">
      <summary>{`面板选择记录（${rows.length}）`}</summary>
      <div className="commercial-intent-status-list">
        {rows.map((item) => (
          <div className="commercial-intent-status-row" key={`${item.stage}-${item.revision}`}>
            {`${INTENT_STATUS_ZH[item.status || ""] || ""} · ${item.summary || ""}`}
          </div>
        ))}
      </div>
    </details>
  );
}
