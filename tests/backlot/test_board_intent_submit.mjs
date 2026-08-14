import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildDecisionIntent,
  CONFIRM_PHRASE,
  submitDecisionIntent,
} from "../../backlot/ui/board-intent-submit.js";

const SOURCE_URL = new URL(
  "../../backlot/ui/board-intent-submit.js",
  import.meta.url,
);

function draft() {
  return {
    revision: "revision-001",
    selections: [{
      decision_key: "brief_locked::current",
      option_id: "medium",
      label_zh: "中度",
    }],
    note: "保留片尾品牌标识",
  };
}

async function buildIntent(overrides = {}) {
  return buildDecisionIntent({
    projectId: "demo-pro",
    stage: "brief_locked",
    draft: draft(),
    summary: "采用中度档，等待聊天确认",
    now: new Date("2026-08-14T01:00:00.000Z"),
    intentId: "decision-001",
    digestSha256: async () => "a".repeat(64),
    ...overrides,
  });
}

test("decision envelope stays pending and contains only draft selections", async () => {
  const intent = await buildIntent();

  assert.equal(intent.version, "1.0");
  assert.equal(intent.intent_type, "decision");
  assert.equal(intent.intent_id, "decision-001");
  assert.equal(intent.project_id, "demo-pro");
  assert.equal(intent.stage, "brief_locked");
  assert.equal(intent.revision, "revision-001");
  assert.equal(intent.status, "pending");
  assert.equal(intent.created_at, "2026-08-14T01:00:00.000Z");
  assert.equal(intent.expires_at, "2026-08-15T01:00:00.000Z");
  assert.deepEqual(intent.payload, {
    selections: draft().selections,
    note: "保留片尾品牌标识",
  });
  assert.equal("risk_level" in intent, false);
  assert.equal("provider" in intent, false);
  assert.equal("model" in intent, false);
  assert.equal("runtime" in intent, false);
  assert.equal("cost_caps" in intent, false);
});

test("decision envelope hashes the exact summary", async () => {
  const seen = [];
  const intent = await buildIntent({
    summary: "逐字摘要",
    digestSha256: async (value) => {
      seen.push(value);
      return "b".repeat(64);
    },
  });

  assert.deepEqual(seen, ["逐字摘要"]);
  assert.equal(intent.summary, "逐字摘要");
  assert.equal(intent.summary_sha256, "b".repeat(64));
  assert.match(intent.summary_sha256, /^[0-9a-f]{64}$/);
});

test("helper copy never implies execution", async () => {
  const source = await readFile(SOURCE_URL, "utf8");

  assert.equal(CONFIRM_PHRASE, "确认面板选择");
  assert.doesNotMatch(source, /批准|已生效|开始生成|立即创建/);
});

test("201 response reports successful submission", async () => {
  const calls = [];
  const intent = await buildIntent();
  const result = await submitDecisionIntent({
    fetchImpl: async (...args) => {
      calls.push(args);
      return { status: 201 };
    },
    intent,
  });

  assert.equal(result.ok, true);
  assert.equal(result.status, 201);
  assert.equal(result.fallback, false);
  assert.equal(result.intent, intent);
  assert.equal(calls[0][0], "/intents");
  assert.deepEqual(calls[0][1], {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(intent),
  });
});

test("rejected fetch falls back without throwing", async () => {
  const intent = await buildIntent();
  const result = await submitDecisionIntent({
    fetchImpl: async () => {
      throw new Error("offline");
    },
    intent,
  });

  assert.equal(result.ok, false);
  assert.equal(result.status, null);
  assert.equal(result.fallback, true);
  assert.equal(result.intent, intent);
});

test("non-success HTTP status also falls back", async () => {
  const intent = await buildIntent();
  const result = await submitDecisionIntent({
    fetchImpl: async () => ({ status: 500 }),
    intent,
  });

  assert.equal(result.ok, false);
  assert.equal(result.status, 500);
  assert.equal(result.fallback, true);
});

test("source posts to the intents endpoint", async () => {
  const source = await readFile(SOURCE_URL, "utf8");

  assert.match(source, /fetchImpl\(\s*["']\/intents["']/);
});
