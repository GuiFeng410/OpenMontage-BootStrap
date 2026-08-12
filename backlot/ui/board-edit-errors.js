export function submitErrorMessage(status, detail) {
  if (status === 409 && detail?.kind === "editing_gate") {
    const reasonCodes = Array.isArray(detail?.reason_codes)
      ? `（${detail.reason_codes.join(", ")}）`
      : "";
    return `${detail?.friendly_zh || "当前不可提交剪辑要求。"}${reasonCodes}`;
  }
  if (status === 409) {
    return "这组改动之前已经提交过了，无需重复提交。";
  }
  if (status === 404) {
    return "项目找不到了，请刷新后重试。";
  }
  const fallback = typeof detail === "string"
    ? detail
    : detail?.friendly_zh;
  return `提交失败（${status}）：${fallback || "请稍后重试"}`;
}
