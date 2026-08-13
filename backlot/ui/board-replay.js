import { el } from "./lib.js";

// Python writers emit tz-aware UTC isoformat, but treat tz-naive strings as
// UTC too — mixing local-parsed and UTC-parsed timestamps would skew replay
// ordering by the user's UTC offset.
const ts = (iso) => {
  if (!iso) return null;
  let s = String(iso);
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(s)) s += "Z";
  const t = Date.parse(s);
  return Number.isFinite(t) ? t : null;
};

function replayBounds(s) {
  const moments = [];
  for (const st of s.stages) {
    for (const h of st.history_entries || []) {
      const t = ts(h.timestamp);
      if (t) moments.push(t);
    }
  }
  for (const ev of s.events || []) {
    const t = ts(ev.ts);
    if (t) moments.push(t);
  }
  if (moments.length < 2) return null;
  return { t0: Math.min(...moments), t1: Math.max(...moments) };
}

function stateAt(s, T) {
  const view = structuredClone(s);
  for (const st of view.stages) {
    const past = (st.history_entries || []).filter((h) => ts(h.timestamp) != null && ts(h.timestamp) <= T);
    if (!past.length) {
      st.status = "pending"; st.review = null; st.timestamp = null;
      st.gate_skipped = false; st.partial_progress = null;
    } else {
      const cur = past[past.length - 1];
      st.status = cur.status || "pending";
      st.timestamp = cur.timestamp;
    }
  }
  view.events = (view.events || []).filter((ev) => ts(ev.ts) != null && ts(ev.ts) <= T);

  // Storyboard: visuals appear as their scene finishes (events) or when the
  // assets stage has completed as of T (legacy runs without events).
  if (view.storyboard) {
    const assetsStage = view.stages.find((x) => x.name === "assets");
    const assetsDone = assetsStage && assetsStage.status === "completed";
    const finished = new Set();
    const startedNow = new Map();
    for (const ev of view.events) {
      if (!ev.scene_id) continue;
      if (ev.event === "finish") { finished.add(ev.scene_id); startedNow.delete(ev.scene_id); }
      else if (ev.event === "start") startedNow.set(ev.scene_id, ev);
      else if (ev.event === "error") startedNow.delete(ev.scene_id);
    }
    const scenePlanStage = view.stages.find((x) => x.name === "scene_plan");
    const scenePlanDone = scenePlanStage && ["completed", "awaiting_human"].includes(scenePlanStage.status);
    if (!scenePlanDone) {
      view.storyboard = null;
    } else {
      for (const card of view.storyboard.scenes) {
        const visible = assetsDone || finished.has(card.id);
        if (!visible) { card.visual = null; card.takes = []; card.audio = []; }
        card.generating = startedNow.has(card.id);
        card.generating_tool = (startedNow.get(card.id) || {}).tool;
      }
    }
  }
  // Final artifacts hide until their stage happened — for every project
  // shape, storyboard or not (a degraded run must not show the finished
  // movie before its stages ran).
  const scriptStage = view.stages.find((x) => x.name === "script");
  if (!(scriptStage && ["completed", "awaiting_human"].includes(scriptStage.status))) {
    delete view.artifacts.script;
  }
  const composeStage = view.stages.find((x) => x.name === "compose");
  if (!(composeStage && composeStage.status === "completed")) {
    view.media.renders = [];
  }
  return view;
}

export function createReplayController({ rerender }) {
  let replay = null;          // {t0, t1, t, playing} — replay mode when non-null
  let replayTimer = null;

  function scheduleTick() {
    // Single pending tick, ever — rapid pause/play must not stack chains.
    clearTimeout(replayTimer);
    replayTimer = setTimeout(tickReplay, 100);
  }

  function tickReplay() {
    if (!replay || !replay.playing) return;
    // A full run replays in ~20 seconds regardless of real duration
    // (10 renders/second — full re-render per tick, keep it modest).
    const step = (replay.t1 - replay.t0) / 200;
    replay.t = Math.min(replay.t1, replay.t + step);
    if (replay.t >= replay.t1) replay.playing = false;
    rerender();
    if (replay.playing) scheduleTick();
  }

  function startReplay(state) {
    const bounds = replayBounds(state);
    if (!bounds) return;
    replay = { ...bounds, t: bounds.t0, playing: true };
    document.body.classList.add("replaying");
    scheduleTick();
    rerender();
  }

  function reset() {
    replay = null;
    clearTimeout(replayTimer);
    replayTimer = null;
    document.body.classList.remove("replaying");
  }

  function stopReplay() {
    reset();
    rerender();
  }

  function toggleReplayPlay() {
    if (!replay) return;
    replay.playing = !replay.playing;
    if (replay.playing) scheduleTick();
    rerender();
  }

  function viewFor(state, editOpen) {
    return replay && !editOpen ? stateAt(state, replay.t) : state;
  }

  function renderBar(state) {
    const bounds = replayBounds(state);
    if (!bounds) return null;
    if (!replay) {
      // collapsed: just the entry button
      return el("div", { class: "replay-bar", style: "justify-content:flex-end" },
        el("span", { class: "rp-time" }, "scrub the whole run"),
        el("span", { class: "rp-btn", onclick: () => startReplay(state) }, "▶ REPLAY RUN"));
    }
    const pos = (replay.t - replay.t0) / Math.max(1, replay.t1 - replay.t0);
    const timeLabel = el("span", { class: "rp-time" },
      new Date(replay.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    const setT = (value) => {
      replay.t = replay.t0 + (Number(value) / 1000) * (replay.t1 - replay.t0);
      timeLabel.textContent = new Date(replay.t)
        .toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    };
    return el("div", { class: "replay-bar" },
      el("span", { class: "rp-btn", onclick: toggleReplayPlay }, replay.playing ? "❚❚" : "▶"),
      el("input", {
        type: "range", min: "0", max: "1000", value: String(Math.round(pos * 1000)),
        // A full rerender would destroy this slider mid-drag: while dragging,
        // only pause + track the time label; re-render the board on release.
        onpointerdown: () => { replay.playing = false; },
        oninput: (e) => setT(e.target.value),
        onchange: (e) => { setT(e.target.value); rerender(); },
      }),
      timeLabel,
      el("span", { class: "rp-btn", onclick: stopReplay }, "✕ LIVE"),
    );
  }

  function isActive() {
    return replay !== null;
  }

  return { viewFor, renderBar, reset, isActive };
}
