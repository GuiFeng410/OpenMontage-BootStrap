import { fmtClock } from "./format";
import {
  STAGE_ICONS,
  commercialFocusStage,
  isCommercial,
  stageLabel,
  stageNeedsDecision,
  stageStatusZh,
  stageWasCompletedBefore,
  visibleStages,
} from "./model";
import type { BoardState, StageState } from "./types";

type Props = {
  state: BoardState;
  selectedStage: string | null;
  onToggleStage: (name: string) => void;
};

export function StageRail({ state, selectedStage, onToggleStage }: Props) {
  const commercial = isCommercial(state);
  const stages = visibleStages(state);
  const focusStageName = commercial ? commercialFocusStage(state, selectedStage) : null;
  let pendingIndex = 1;
  return (
    <nav className="rail">
      {stages.map((st) => {
        const cls =
          st.status === "completed"
            ? "done"
            : st.status === "in_progress"
              ? st.stalled
                ? "active stalled"
                : "active"
              : st.status === "awaiting_human"
                ? "await"
                : st.status === "failed"
                  ? "failed"
                  : "";
        const icon = STAGE_ICONS[st.status] || String(pendingIndex);
        if (!STAGE_ICONS[st.status]) pendingIndex += 1;
        const sub = commercial ? stageSubZh(st, state) : stageSub(st);
        const isFocus = Boolean(focusStageName && st.name === focusStageName);
        return (
          <div
            key={st.name}
            className={`stage ${cls}${selectedStage === st.name ? " selected" : ""}${isFocus ? " focus" : ""}${st.undeclared ? " undeclared" : ""}`}
            title={
              st.undeclared
                ? `"${st.name}" ran but isn't declared by this pipeline's manifest`
                : undefined
            }
            onClick={() => onToggleStage(st.name)}
          >
            <span className="line" />
            <span className="node">{icon}</span>
            <span className="name">{stageLabel(st)}</span>
            <span className="sub" style={{ whiteSpace: "pre-line" }}>
              {st.undeclared ? `${sub}\n未列入管线`.trim() : sub}
            </span>
          </div>
        );
      })}
    </nav>
  );
}

export function StageDrawer({ state, selectedStage, onToggleStage }: Props) {
  if (!selectedStage) return null;
  const st = state.stages.find((x) => x.name === selectedStage);
  if (!st) return null;
  if (!isCommercial(state)) {
    return (
      <div className="drawer">
        <div className="drawer-head">
          <h3>{`${stageLabel(st)} — ${st.status}`}</h3>
          <span className="close" onClick={() => onToggleStage(st.name)}>
            CLOSE ✕
          </span>
        </div>
        <div className="drawer-body">
          <div className="hint">非商品片看板仍请用默认站查看完整证据。</div>
        </div>
      </div>
    );
  }
  const meta = st.metadata || {};
  const options = Array.isArray(meta.decision_options) ? meta.decision_options : [];
  const prompt = typeof meta.decision_prompt_zh === "string" ? meta.decision_prompt_zh : "";
  const heading = options.length ? "请在本页确认：" : "当前已暂停：";
  return (
    <div className="drawer commercial-drawer">
      <div className="drawer-head">
        <h3>{`${stageLabel(st)} — ${stageStatusZh(st.status)}`}</h3>
        {st.timestamp ? (
          <span
            className="meta"
            style={{
              fontFamily: "var(--mono)",
              fontSize: "calc(10.5px * var(--fs-scale))",
              color: "var(--text-3)",
            }}
          >
            {st.timestamp}
          </span>
        ) : null}
        <span className="close" onClick={() => onToggleStage(st.name)}>
          关闭 ✕
        </span>
      </div>
      <div className="drawer-body">
        <div className="hint" style={{ marginBottom: 12, lineHeight: 1.6 }}>
          商品片阶段详情已在下方「方案摘要 / Beat 胶片条 / 成片预览」展示。
          <br />
          原始 JSON 见 <code>artifacts/</code> 目录；点选确认请留在本页。
        </div>
        {stageNeedsDecision(st) && prompt ? (
          <div className="commercial-decision-hint">
            <b>{heading}</b>
            <div>{prompt}</div>
          </div>
        ) : null}
        {typeof meta.approval_note === "string" ? (
          <div className="hint">{`已记录批准：${meta.approval_note}`}</div>
        ) : null}
      </div>
    </div>
  );
}

function stageSubZh(st: StageState, s: BoardState) {
  const phase = s.commercial?.runner_status?.phase;
  const pausedStage = s.commercial?.board_stop?.stage;
  if (phase === "paused" && st.name === pausedStage) {
    return "已暂停\n看本页原因，未在调模型";
  }
  if (st.metadata?.producing_wait) return "制作中\n请留在本页等待成片";
  if (st.name === "delivery_signoff" && st.status !== "completed") {
    if (s.commercial?.final_video) {
      return "成片已就绪\n本页预览后点结束并导出";
    }
    return st.status === "in_progress" ? "等待成片\n完成后可在本页预览" : "待开始";
  }
  const nextHint = st.name === "assets_gate" ? "点开始出片继续" : "点进入下一步继续";
  if (st.status === "awaiting_human") return `等你在本页确认\n${nextHint}`;
  if (stageNeedsDecision(st)) return `等你在本页确认\n${nextHint}`;
  if (st.status === "in_progress" && stageWasCompletedBefore(st)) {
    return st.stalled
      ? `重试中·此前已通过\n可能卡住 · ${st.stalled_minutes} 分钟无活动`
      : "重试中·此前已通过";
  }
  if (st.status === "in_progress" && st.stalled) {
    return `可能卡住 · ${st.stalled_minutes} 分钟无活动\n可询问 Agent 状态`;
  }
  if (st.status === "in_progress" && st.partial_progress) {
    const done = st.partial_progress.beats_done || st.partial_progress.completed_scene_ids;
    if (Array.isArray(done)) return `已完成 ${done.length} 段`;
    return "制作中";
  }
  if (st.status === "in_progress") return "制作中";
  if (st.status === "failed") return st.error ? String(st.error).slice(0, 60) : "失败";
  if (st.status === "completed") return st.gated && st.human_approved ? "已通过" : "已完成";
  if (st.timestamp) return fmtClock(st.timestamp);
  return "待开始";
}

function stageSub(st: StageState) {
  if (st.status === "awaiting_human") return "awaiting your approval\nreply in chat to continue";
  if (st.status === "in_progress" && st.stalled) {
    return `stalled? no activity for ${st.stalled_minutes}m\nask the agent for status`;
  }
  if (st.status === "in_progress") return "in progress";
  if (st.status === "failed") return st.error ? String(st.error).slice(0, 60) : "failed";
  if (st.timestamp) return fmtClock(st.timestamp);
  return "";
}
