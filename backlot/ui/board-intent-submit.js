export const CONFIRM_PHRASE = "确认面板选择";
export const EXPORT_PHRASE = "结束导出";

async function browserDigestSha256(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function createIntentId() {
  const randomId = globalThis.crypto?.randomUUID?.();
  return randomId
    ? `decision-${randomId}`
    : `decision-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export async function buildDecisionIntent({
  projectId,
  stage,
  draft,
  summary,
  now = new Date(),
  intentId = createIntentId(),
  digestSha256 = browserDigestSha256,
}) {
  const createdAt = now instanceof Date ? now : new Date(now);
  const expiresAt = new Date(createdAt.getTime() + 24 * 60 * 60 * 1000);
  const summarySha256 = await digestSha256(summary);

  return {
    version: "1.0",
    intent_type: "decision",
    intent_id: intentId,
    project_id: projectId,
    stage,
    revision: draft.revision,
    summary,
    summary_sha256: summarySha256,
    payload: {
      selections: draft.selections,
      note: draft.note,
    },
    expires_at: expiresAt.toISOString(),
    created_at: createdAt.toISOString(),
    status: "pending",
  };
}

export async function buildExportIntent({
  projectId,
  stage = "delivery_signoff",
  now = new Date(),
  intentId,
  digestSha256 = browserDigestSha256,
}) {
  const createdAt = now instanceof Date ? now : new Date(now);
  const expiresAt = new Date(createdAt.getTime() + 24 * 60 * 60 * 1000);
  const summary = "结束并导出项目";
  const summarySha256 = await digestSha256(summary);
  const id = intentId
    || (globalThis.crypto?.randomUUID
      ? `export-${globalThis.crypto.randomUUID()}`
      : `export-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  return {
    version: "1.0",
    intent_type: "project_export",
    intent_id: id,
    project_id: projectId,
    stage,
    revision: "export-v1",
    summary,
    summary_sha256: summarySha256,
    payload: { action: "end_and_export" },
    expires_at: expiresAt.toISOString(),
    created_at: createdAt.toISOString(),
    status: "pending",
  };
}

export async function submitDecisionIntent({ fetchImpl = fetch, intent }) {
  try {
    const response = await fetchImpl("/intents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(intent),
    });
    const ok = response.status === 200 || response.status === 201;
    return {
      ok,
      status: response.status,
      fallback: !ok,
      intent,
    };
  } catch {
    return {
      ok: false,
      status: null,
      fallback: true,
      intent,
    };
  }
}
