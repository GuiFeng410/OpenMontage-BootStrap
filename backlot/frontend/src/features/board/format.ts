export function fmtAgo(epochSeconds?: number) {
  if (!epochSeconds) return "";
  const diff = Date.now() / 1000 - epochSeconds;
  if (diff < 90) return "刚刚";
  if (diff < 3600) return `${Math.round(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.round(diff / 3600)} 小时前`;
  return `${Math.round(diff / 86400)} 天前`;
}

export function fmtClock(iso?: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

export function fmtMoney(value: unknown) {
  const n = Number(value);
  if (value == null || !Number.isFinite(n)) return "—";
  return `$${n.toFixed(2)}`;
}

export function fmtMoneyCny(value: unknown) {
  const n = Number(value);
  if (value == null || !Number.isFinite(n)) return "—";
  return `¥${n.toFixed(2)}`;
}

export function thumbURL(projectId: string, relPath: string, w = 640) {
  return `/thumb/${encodeURIComponent(projectId)}/${relPath
    .split("/")
    .map(encodeURIComponent)
    .join("/")}?w=${w}`;
}

export function mediaURL(projectId: string, relPath: string) {
  return `/media/${encodeURIComponent(projectId)}/${relPath
    .split("/")
    .map(encodeURIComponent)
    .join("/")}`;
}

export function fmtDuration(seconds?: number | null) {
  if (seconds == null || !Number.isFinite(Number(seconds))) return "";
  const n = Math.max(0, Number(seconds));
  const m = Math.floor(n / 60);
  const s = Math.round(n % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function libraryHref() {
  const suffix = new URLSearchParams(window.location.search).has("static")
    ? "?static=1"
    : "";
  return `/${suffix}`;
}

export function vanillaBoardHref(projectId: string) {
  const suffix = new URLSearchParams(window.location.search).has("static")
    ? "?static=1"
    : "";
  return `/p/${encodeURIComponent(projectId)}${suffix}`;
}
