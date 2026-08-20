import { DecisionPanel } from "./DecisionPanel";
import {
  RUNNER_GONE_ZH,
  isCommercial,
  isProducePaused,
  runnerBoundToProject,
  stageNeedsDecision,
} from "./model";
import type { BoardState, SseStatus } from "./types";

type Props = {
  state: BoardState;
  sseStatus: SseStatus;
  onRefresh: () => void;
};

const RUNNER_LABEL: Record<string, string> = {
  queued: "排队",
  applying: "进行中",
  producing: "进行中",
  paused: "暂停，要你选",
  ready: "已出片",
  exported: "已导出",
  needs_chat: "请在本页刷新或补 Key 后继续",
  idle: "本机空闲",
};

export function BoardNotices({ state, sseStatus, onRefresh }: Props) {
  if (!isCommercial(state)) return null;
  return (
    <>
      <RunnerStatus state={state} />
      <FastTrackPause state={state} />
      <SseBanner sseStatus={sseStatus} onRefresh={onRefresh} />
      <LegacyNotice state={state} />
      <DoneNotice state={state} />
      <AwaitingNotice state={state} />
    </>
  );
}

function RunnerStatus({ state }: { state: BoardState }) {
  const status = state.commercial?.runner_status;
  if (!status || typeof status !== "object") return null;
  const bound = runnerBoundToProject(state);
  const phase = status.phase || "idle";
  return (
    <div className="notice commercial-runner-status">
      <div className="commercial-runner-phase">{bound ? RUNNER_LABEL[phase] || phase : "已冻结"}</div>
      {status.friendly_zh ? <div className="commercial-runner-copy">{status.friendly_zh}</div> : null}
      {bound ? null : <div className="commercial-runner-copy">{RUNNER_GONE_ZH}</div>}
      {status.current_question ? (
        <div className="commercial-pause-question">{status.current_question}</div>
      ) : null}
    </div>
  );
}

function FastTrackPause({ state }: { state: BoardState }) {
  const pause = state.commercial?.fast_track_pause;
  if (!pause || typeof pause !== "object") return null;
  return (
    <div className="notice commercial-fast-track-pause">
      <div className="commercial-pause-friendly">{pause.friendly_zh || ""}</div>
      {pause.current_question ? (
        <div className="commercial-pause-question">{pause.current_question}</div>
      ) : null}
      <div className="commercial-chat-only">暂停原因写在本页；可在看板继续选。</div>
    </div>
  );
}

function SseBanner({
  sseStatus,
  onRefresh,
}: {
  sseStatus: SseStatus;
  onRefresh: () => void;
}) {
  if (sseStatus === "live") return null;
  const text =
    sseStatus === "disconnected"
      ? "看板实时连接已断开，已启用低频自动轮询；SSE 恢复后会自动停止轮询。"
      : "正在连接看板实时更新…";
  return (
    <div className={`notice sse-banner ${sseStatus}`}>
      <span>⟳</span>
      <span>{text}</span>
      <button className="sse-refresh-btn" type="button" onClick={onRefresh}>
        刷新
      </button>
    </div>
  );
}

function LegacyNotice({ state }: { state: BoardState }) {
  const records = state.commercial?.legacy_checkpoints || [];
  if (!records.length) return null;
  return (
    <div className="notice commercial-legacy-notice">
      <span>⚠</span>
      <span>
        发现历史 checkpoint：
        <b>{records.map((item) => item.stage).join("、")}</b>
        。它们不属于商品片七阶段，已从主进度栏隔离，且没有改写项目磁盘。
      </span>
    </div>
  );
}

function DoneNotice({ state }: { state: BoardState }) {
  const known = state.stages.filter((x) => !x.undeclared);
  if (!known.length || !known.every((x) => x.status === "completed")) return null;
  return (
    <div className="notice commercial-done-notice">
      <span>✓</span>
      <span>七阶段已完成。点顶栏阶段可回看该阶段证据。确认后请到默认站点「结束并导出项目」。</span>
    </div>
  );
}

function AwaitingNotice({ state }: { state: BoardState }) {
  if (!state.commercial?.completed && !runnerBoundToProject(state)) {
    return pausedOrWait("已冻结", RUNNER_GONE_ZH);
  }
  const awaiting =
    state.stages.find((x) => x.status === "awaiting_human") ||
    state.stages.find(stageNeedsDecision);
  const dec = state.commercial?.decision;
  if (dec?.producing_wait) {
    return pausedOrWait(
      "制作中",
      dec.prompt_zh || "成片尚未就绪，请留在本页等待制作。大约需要几分钟。",
    );
  }
  const options = Array.isArray(dec?.options) ? dec.options : [];
  if (options.length && dec) {
    return (
      <DecisionPanel
        projectId={state.project_id}
        projectTitle={state.title}
        stage={dec.stage || awaiting?.name || "brief_locked"}
        decision={dec}
        interactionIntents={state.commercial?.interaction_intents}
        runnerBound={runnerBoundToProject(state)}
      />
    );
  }
  if (isProducePaused(state)) {
    const runner = state.commercial?.runner_status || {};
    return pausedOrWait(
      "已暂停",
      runner.friendly_zh ||
        dec?.prompt_zh ||
        "制作已暂停。请看本页原因；当前没有在调用视频模型。",
    );
  }
  if (!awaiting) {
    const producing =
      state.commercial?.decision?.producing_wait || state.commercial?.board_stop?.producing_wait;
    if (producing) {
      return pausedOrWait(
        "制作中",
        dec?.prompt_zh || "成片尚未就绪，请留在本页等待制作。大约需要几分钟。",
      );
    }
    return null;
  }
  const prompt = dec?.prompt_zh || "请在本页确认后进入下一步。";
  if (state.commercial?.final_video?.exists) {
    return (
      <div className="notice commercial-notice">
        <span style={{ fontSize: "calc(16px * var(--fs-scale))" }}>✓</span>
        <div className="commercial-decision-body">
          <b>交付确认</b>
          <div className="commercial-decision-prompt" style={{ whiteSpace: "pre-line" }}>
            {prompt || "成片已就绪。播放与导出请打开默认站看板。"}
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="notice commercial-notice">
      <span style={{ fontSize: "calc(16px * var(--fs-scale))" }}>◈</span>
      <div className="commercial-decision-body">
        <b>{`【需要你决定】${dec?.title_zh || dec?.stage_label_zh || (awaiting.label_zh || awaiting.name)}`}</b>
        {dec?.context_zh ? <div className="commercial-decision-context">{dec.context_zh}</div> : null}
        <div className="commercial-decision-prompt" style={{ whiteSpace: "pre-line" }}>
          {prompt}
        </div>
        {dec?.examples_zh ? (
          <div className="commercial-decision-example">{`回复示例：${dec.examples_zh}`}</div>
        ) : null}
        <div className="commercial-chat-only">请留在本页确认。本机不会静默付费生视频。</div>
      </div>
    </div>
  );
}

function pausedOrWait(title: string, prompt: string) {
  return (
    <div className="notice commercial-notice">
      <span style={{ fontSize: "calc(16px * var(--fs-scale))" }}>◈</span>
      <div className="commercial-decision-body">
        <b>{title}</b>
        <div className="commercial-decision-prompt" style={{ whiteSpace: "pre-line" }}>
          {prompt}
        </div>
      </div>
    </div>
  );
}
