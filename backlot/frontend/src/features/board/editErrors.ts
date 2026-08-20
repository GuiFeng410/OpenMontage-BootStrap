export function submitErrorMessage(status: number, detail: unknown) {
  const rec = detail && typeof detail === "object" ? (detail as Record<string, unknown>) : null;
  if (status === 409 && rec?.kind === "editing_gate") {
    const codes = Array.isArray(rec.reason_codes) ? `（${rec.reason_codes.join(", ")}）` : "";
    return `${typeof rec.friendly_zh === "string" && rec.friendly_zh ? rec.friendly_zh : "当前不可提交剪辑要求。"}${codes}`;
  }
  if (status === 409) {
    return "这组改动之前已经提交过了，无需重复提交。";
  }
  if (status === 404) {
    return "项目找不到了，请刷新后重试。";
  }
  const fallback =
    typeof detail === "string"
      ? detail
      : typeof rec?.friendly_zh === "string"
        ? rec.friendly_zh
        : "";
  return `提交失败（${status}）：${fallback || "请稍后重试"}`;
}
