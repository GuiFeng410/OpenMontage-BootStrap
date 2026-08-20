import type { IntentDraft } from "./intentState";

async function browserDigestSha256(value: string) {
  const bytes = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
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
}: {
  projectId: string;
  stage: string;
  draft: IntentDraft;
  summary: string;
  now?: Date | string;
  intentId?: string;
  digestSha256?: (value: string) => Promise<string>;
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

export async function submitDecisionIntent({
  fetchImpl = fetch,
  intent,
}: {
  fetchImpl?: typeof fetch;
  intent: Record<string, unknown>;
}) {
  try {
    const response = await fetchImpl("/intents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(intent),
    });
    const ok = response.status === 200 || response.status === 201;
    return { ok, status: response.status, fallback: !ok, intent };
  } catch {
    return { ok: false, status: null, fallback: true, intent };
  }
}
