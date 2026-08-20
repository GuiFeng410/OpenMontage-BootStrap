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

export function vanillaBoardHref(projectId: string) {
  const suffix = new URLSearchParams(window.location.search).has("static")
    ? "?static=1"
    : "";
  return `/p/${encodeURIComponent(projectId)}${suffix}`;
}
