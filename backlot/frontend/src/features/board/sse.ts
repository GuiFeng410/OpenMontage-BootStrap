import type { SseStatus } from "./types";

export type SseHandle = { close: () => void };

export function subscribeBoard(
  url: string,
  onChange: () => void,
  onStatus?: (status: SseStatus) => void,
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

  onStatus?.("connecting");
  try {
    source = new EventSource(url);
  } catch {
    onStatus?.("disconnected");
    startPolling();
  }
  if (source) {
    source.onopen = () => {
      stopPolling();
      onStatus?.("live");
    };
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
    source.onerror = () => {
      onStatus?.("disconnected");
      startPolling();
    };
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
