import { useCallback, useEffect, useState } from "react";
import { getJSON } from "../library/api";
import { BeatFilmstrip } from "./Beats";
import { CommercialPlayer } from "./CommercialPlayer";
import { EditTab } from "./EditTab";
import { EvidencePanels, ReviewFold } from "./Evidence";
import { GenericBoard } from "./GenericBoard";
import { HeaderSlate } from "./HeaderSlate";
import { IntentStatus } from "./IntentStatus";
import { BoardNotices } from "./Notices";
import { ProductionTierPanel } from "./ProductionTierPanel";
import { maybeRedirectAfterExport } from "./ExportButton";
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
  const [editOpen, setEditOpen] = useState(false);

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

  const refresh = useCallback(() => {
    void load().catch(console.error);
  }, [load]);

  const onToggleStage = (name: string) => {
    setSelectedStage((curr) => (curr === name ? null : name));
  };

  if (error && !state) {
    return (
      <div className="wrap" data-backlot-spa="board">
        <div className="empty" style={{ marginTop: 80 }}>
          <div className="big">PROJECT NOT FOUND</div>
          <div>{error}</div>
        </div>
      </div>
    );
  }
  if (!state) {
    return (
      <div className="wrap" data-backlot-spa="board">
        <p className="hint">正在加载看板…</p>
      </div>
    );
  }

  if (maybeRedirectAfterExport(state)) {
    return (
      <div className="wrap" data-backlot-spa="board">
        <p className="hint">正在返回项目库…</p>
      </div>
    );
  }

  if (!isCommercial(state)) {
    return (
      <div className="wrap" data-backlot-spa="board">
        <HeaderSlate
          state={state}
          editOpen={editOpen}
          onToggleEdit={() => setEditOpen((open) => !open)}
        />
        <StageRail state={state} selectedStage={selectedStage} onToggleStage={onToggleStage} />
        <StageDrawer state={state} selectedStage={selectedStage} onToggleStage={onToggleStage} />
        {editOpen ? <EditTab state={state} /> : <GenericBoard state={state} />}
      </div>
    );
  }

  const hideAssetPanels = shouldHideMinimalAssetPanels(state);
  return (
      <div className="wrap" data-backlot-spa="board">
      <HeaderSlate
        state={state}
        editOpen={editOpen}
        onToggleEdit={() => setEditOpen((open) => !open)}
      />
      <StageRail state={state} selectedStage={selectedStage} onToggleStage={onToggleStage} />
      <StageDrawer state={state} selectedStage={selectedStage} onToggleStage={onToggleStage} />
      <ProductionTierPanel state={state} onRefresh={refresh} />
      <BoardNotices state={state} sseStatus={sseStatus} onRefresh={refresh} />
      {editOpen ? (
        <EditTab state={state} />
      ) : (
        <div className="board commercial-board">
          <div className="main-col">
            <StageStatusCard state={state} selectedStage={selectedStage} />
            {hideAssetPanels ? null : <EvidencePanels state={state} selectedStage={selectedStage} />}
            <CommercialPlayer state={state} selectedStage={selectedStage} />
            <BeatFilmstrip state={state} selectedStage={selectedStage} />
            <StageEvidence state={state} selectedStage={selectedStage} />
            <ReviewFold state={state} selectedStage={selectedStage} />
            <IntentStatus intents={state.commercial?.interaction_intents} />
          </div>
        </div>
      )}
    </div>
  );
}
