import { useCallback, useEffect, useState } from "react";
import { getJSON } from "../library/api";
import { BeatFilmstrip } from "./Beats";
import { EvidencePanels, ReviewFold } from "./Evidence";
import { HeaderSlate } from "./HeaderSlate";
import { IntentStatus } from "./IntentStatus";
import { BoardNotices } from "./Notices";
import { vanillaBoardHref } from "./format";
import {
  isCommercial,
  normalizeBoardState,
  projectIdFromPath,
  shouldHideMinimalAssetPanels,
} from "./model";
import { subscribeBoard } from "./sse";
import { StageDrawer, StageRail } from "./StageRail";
import { StageEvidence } from "./StageEvidence";
import { StageStatusCard } from "./StageStatusCard";
import type { BoardState, SseStatus } from "./types";

export function BoardPage() {
  const projectId = projectIdFromPath();
  const [state, setState] = useState<BoardState | null>(null);
  const [error, setError] = useState("");
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [sseStatus, setSseStatus] = useState<SseStatus>("connecting");

  const load = useCallback(async () => {
    const raw = await getJSON<unknown>(`/api/project/${encodeURIComponent(projectId)}/state`);
    const next = normalizeBoardState(raw);
    setState(next);
    setError("");
    document.title = `Backlot — ${next.title}`;
    if (isCommercial(next)) document.documentElement.lang = "zh-CN";
  }, [projectId]);

  useEffect(() => {
    void load().catch((err) => {
      setError(String(err));
      setState(null);
    });
    if (new URLSearchParams(window.location.search).has("static")) {
      setSseStatus("live");
      return;
    }
    const sub = subscribeBoard(
      `/api/project/${encodeURIComponent(projectId)}/events`,
      () => {
        void load().catch(console.error);
      },
      setSseStatus,
    );
    return () => sub.close();
  }, [load, projectId]);

  const onToggleStage = (name: string) => {
    setSelectedStage((curr) => (curr === name ? null : name));
  };

  if (error && !state) {
    return (
      <div className="wrap" data-backlot-next="board">
        <div className="empty" style={{ marginTop: 80 }}>
          <div className="big">PROJECT NOT FOUND</div>
          <div>{error}</div>
        </div>
      </div>
    );
  }
  if (!state) {
    return (
      <div className="wrap" data-backlot-next="board">
        <p className="hint">正在加载看板…</p>
      </div>
    );
  }

  if (!isCommercial(state)) {
    return (
      <div className="wrap" data-backlot-next="board">
        <HeaderSlate state={state} />
        <StageRail state={state} selectedStage={selectedStage} onToggleStage={onToggleStage} />
        <div className="hint" style={{ padding: 24 }}>
          非商品片看板尚未迁入 React。请使用
          <a href={vanillaBoardHref(state.project_id)}> 默认站 </a>。
        </div>
      </div>
    );
  }

  const hideAssetPanels = shouldHideMinimalAssetPanels(state);
  return (
    <div className="wrap" data-backlot-next="board">
      <HeaderSlate state={state} />
      <StageRail state={state} selectedStage={selectedStage} onToggleStage={onToggleStage} />
      <StageDrawer state={state} selectedStage={selectedStage} onToggleStage={onToggleStage} />
      <BoardNotices state={state} sseStatus={sseStatus} onRefresh={() => void load().catch(console.error)} />
      <div className="board commercial-board">
        <div className="main-col">
          <IntentStatus intents={state.commercial?.interaction_intents} />
          <StageStatusCard state={state} selectedStage={selectedStage} />
          {hideAssetPanels ? null : <EvidencePanels state={state} selectedStage={selectedStage} />}
          <BeatFilmstrip state={state} selectedStage={selectedStage} />
          <StageEvidence state={state} selectedStage={selectedStage} />
          <ReviewFold state={state} selectedStage={selectedStage} />
        </div>
      </div>
    </div>
  );
}
