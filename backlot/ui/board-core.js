import { getJSON, subscribe } from "./lib.js";

export function createBoardContext({ projectId, app, modal, player }) {
  return {
    projectId,
    app,
    modal,
    player,
    state: null,
    selectedStage: null,
    activeRender: 0,
    firstPaint: true,
    sseStatus: "connecting",
    editOpen: false,
    renderPlaybackState: new Map(),
  };
}

// Defensive normalization: sparse and legacy payloads degrade without
// crashing the board.
export function normalizeBoardState(state) {
  state.pipeline = state.pipeline || { pipeline_type: "unknown", stages: [], known: false };
  state.stages = Array.isArray(state.stages) ? state.stages : [];
  state.artifacts = state.artifacts || {};
  state.media = state.media || {};
  state.media.renders = Array.isArray(state.media.renders) ? state.media.renders : [];
  state.media.snapshots = Array.isArray(state.media.snapshots) ? state.media.snapshots : [];
  state.media.music = Array.isArray(state.media.music) ? state.media.music : [];
  state.events = Array.isArray(state.events) ? state.events : [];
  state.commercial = state.commercial || null;
  state.locale = state.locale || "en";
  if (state.storyboard && Array.isArray(state.storyboard.scenes)) {
    for (const scene of state.storyboard.scenes) {
      scene.takes = Array.isArray(scene.takes) ? scene.takes : [];
      scene.audio = Array.isArray(scene.audio) ? scene.audio : [];
      scene.required_assets = Array.isArray(scene.required_assets) ? scene.required_assets : [];
    }
  } else {
    state.storyboard = null;
  }
  return state;
}

export async function refreshBoard(context, renderPage) {
  context.state = normalizeBoardState(
    await getJSON(`/api/project/${encodeURIComponent(context.projectId)}/state`),
  );
  renderPage();
}

export function startBoardLiveFeed(context, renderPage) {
  if (new URLSearchParams(location.search).has("static")) return null;

  return subscribe(
    `/api/project/${encodeURIComponent(context.projectId)}/events`,
    () => refreshBoard(context, renderPage).catch(console.error),
    (status) => {
      context.sseStatus = status;
      if (context.state) renderPage();
    },
  );
}
