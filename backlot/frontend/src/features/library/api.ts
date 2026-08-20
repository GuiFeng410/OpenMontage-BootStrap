export const LABELS = {
  "NO MEDIA YET": "暂无媒体",
  "AWAITING YOU": "等待确认",
  LIVE: "进行中",
  IDLE: "空闲",
  projects: "个项目",
  scenes: "个场景",
  renders: "个成片",
  unknown: "未识别管线",
};

export type Occupant = { project_id: string; title: string };

export type Health = {
  projects_dir?: string;
  runner_alive?: boolean;
  active_project_id?: string;
  runner_occupant?: { project_id?: string; title?: string };
};

export type StageState = { name: string; status: string };

export type ProjectSummary = {
  project_id: string;
  title?: string;
  poster?: string | null;
  live?: boolean;
  awaiting_human?: boolean;
  active_stage?: string;
  completed?: boolean;
  lifecycle_status?: string;
  user_stage_zh?: string;
  pipeline_type?: string;
  review_mode_zh?: string;
  production_tier_zh?: string;
  imported_asset_count?: number;
  scene_count?: number;
  render_count?: number;
  last_activity?: number;
  stage_states?: StageState[];
  export_path?: string;
};

export function occupantFromHealth(health: Health | null | undefined): Occupant {
  if (!health?.runner_alive) return { project_id: "", title: "" };
  const occ = health.runner_occupant || {};
  const id = String(occ.project_id || health.active_project_id || "").trim();
  if (!id) return { project_id: "", title: "" };
  return { project_id: id, title: String(occ.title || id) };
}

export function friendlyFromPayload(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;
  const rec = data as Record<string, unknown>;
  const detail = rec.detail;
  if (detail && typeof detail === "object" && detail !== null && "friendly_zh" in detail) {
    return String((detail as { friendly_zh: unknown }).friendly_zh || fallback);
  }
  if (typeof detail === "string" && detail) return detail;
  if (typeof rec.friendly_zh === "string" && rec.friendly_zh) return rec.friendly_zh;
  return fallback;
}

export async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json() as Promise<T>;
}

export function fmtAgo(epochSeconds?: number) {
  if (!epochSeconds) return "";
  const diff = Date.now() / 1000 - epochSeconds;
  if (diff < 90) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

export function thumbURL(projectId: string, relPath: string, w = 640) {
  return `/thumb/${encodeURIComponent(projectId)}/${relPath.split("/").map(encodeURIComponent).join("/")}?w=${w}`;
}

export function mediaURL(projectId: string, relPath: string) {
  return `/media/${encodeURIComponent(projectId)}/${relPath.split("/").map(encodeURIComponent).join("/")}`;
}

export function boardSuffix() {
  return new URLSearchParams(window.location.search).has("static") ? "?static=1" : "";
}

export type SseHandle = { close: () => void };

export function subscribe(
  url: string,
  onChange: () => void,
  pollMs = 4000,
): SseHandle {
  let changeTimer: ReturnType<typeof setTimeout> | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let pollInFlight = false;
  let closed = false;
  let source: EventSource | null = null;

  const runPoll = () => {
    if (closed || pollInFlight) return;
    pollInFlight = true;
    Promise.resolve()
      .then(onChange)
      .catch((error) => console.error(error))
      .finally(() => {
        pollInFlight = false;
      });
  };
  const startPolling = () => {
    if (closed || pollTimer != null) return;
    pollTimer = setInterval(runPoll, pollMs);
  };
  const stopPolling = () => {
    if (pollTimer == null) return;
    clearInterval(pollTimer);
    pollTimer = null;
  };

  try {
    source = new EventSource(url);
  } catch {
    startPolling();
  }
  if (source) {
    source.onopen = () => stopPolling();
    source.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as { type?: string };
        if (data.type !== "change") return;
      } catch {
        return;
      }
      if (changeTimer) clearTimeout(changeTimer);
      changeTimer = setTimeout(onChange, 250);
    };
    source.onerror = () => startPolling();
  }

  return {
    close() {
      if (closed) return;
      closed = true;
      if (changeTimer) clearTimeout(changeTimer);
      stopPolling();
      source?.close();
    },
  };
}
