import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildCreateProductVideoPrompt,
  copyCreatePrompt,
  formatServiceInfo,
  getReviewModeRoute,
  listReviewModes,
  readStoredReviewMode,
  writeStoredReviewMode,
} from "../../backlot/ui/library-onboarding.js";

const NORMAL_PROMPT = "请帮我创建一个新的商品宣传片项目。请按普通评审引导我确认商品主题、时长、素材、制作档位和预算；创建后把 Backlot 项目网址发给我。";
const MINIMAL_PROMPT = "请帮我创建一个新的商品宣传片项目。请按极简模式（方案、素材、交付三停；素材通过后直接生成，不做独立试片）引导我确认商品主题、时长、素材、制作档位和预算；创建后把 Backlot 项目网址发给我。";
const PRO_PROMPT = "请帮我创建一个新的商品宣传片项目。请按专业模式（七步都要我过目）引导我确认商品主题、时长、素材、制作档位和预算；创建后把 Backlot 项目网址发给我。";

test("prompt defaults to ordinary review and mentions Backlot URL", () => {
  const prompt = buildCreateProductVideoPrompt();

  assert.equal(prompt, NORMAL_PROMPT);
  assert.match(prompt, /Backlot 项目网址/);
});

test("prompt follows the selected review mode", () => {
  assert.equal(buildCreateProductVideoPrompt("minimal"), MINIMAL_PROMPT);
  assert.equal(buildCreateProductVideoPrompt("pro"), PRO_PROMPT);
  assert.equal(buildCreateProductVideoPrompt("unknown"), NORMAL_PROMPT);
});

test("review modes expose 极简 / 普通 / 专业", () => {
  assert.deepEqual(listReviewModes().map((item) => item.label_zh), [
    "极简",
    "普通",
    "专业",
  ]);
});

test("professional route shows all seven confirmation stops", () => {
  const route = getReviewModeRoute("pro");
  assert.equal(route.confirm_steps.length, 7);
  assert.deepEqual(route.confirm_steps.map((step) => step.label_zh), [
    "方案确认",
    "素材检查",
    "试片确认",
    "分段制作",
    "初稿审查",
    "合成终稿",
    "交付确认",
  ]);
  assert.ok(route.confirm_steps.every((step) => step.stop && step.action_zh === "需要你确认"));
});

test("minimal and ordinary routes hide automatic steps", () => {
  const minimal = getReviewModeRoute("minimal");
  const ordinary = getReviewModeRoute("normal");
  assert.deepEqual(minimal.confirm_steps.map((step) => step.label_zh), [
    "方案确认",
    "素材检查",
    "交付确认",
  ]);
  assert.deepEqual(ordinary.confirm_steps.map((step) => step.label_zh), [
    "方案确认",
    "素材检查",
    "试片确认",
    "初稿审查",
    "交付确认",
  ]);
  const byId = Object.fromEntries(minimal.steps.map((step) => [step.id, step]));
  assert.equal(byId.segment_build.stop, false);
  assert.equal(byId.delivery_signoff.stop, true);
});

test("stored review mode round-trips and rejects unknown values", () => {
  const storage = new Map();
  const fake = {
    getItem(key) {
      return storage.has(key) ? storage.get(key) : null;
    },
    setItem(key, value) {
      storage.set(key, value);
    },
  };

  assert.equal(readStoredReviewMode(fake), "normal");
  assert.equal(writeStoredReviewMode(fake, "pro"), "pro");
  assert.equal(readStoredReviewMode(fake), "pro");
  assert.equal(writeStoredReviewMode(fake, "nope"), "normal");
  assert.equal(readStoredReviewMode(fake), "normal");
});

test("service info includes host, count and root", () => {
  assert.deepEqual(formatServiceInfo({
    host: "http://127.0.0.1:8765",
    projectsDir: "F:\\OpenMontage\\projects",
    projectCount: 3,
  }), [
    "本地服务：http://127.0.0.1:8765",
    "已发现 3 个项目",
    "项目目录：F:\\OpenMontage\\projects",
  ]);
});

test("service info missing values degrade safely", () => {
  assert.deepEqual(formatServiceInfo({}), [
    "本地服务：未知",
    "已发现 0 个项目",
    "项目目录：未提供",
  ]);
});

test("clipboard success writes the exact prompt", async () => {
  const writes = [];
  const clipboard = {
    async writeText(value) {
      writes.push(value);
    },
  };

  const result = await copyCreatePrompt({
    clipboard,
    prompt: NORMAL_PROMPT,
  });

  assert.deepEqual(writes, [NORMAL_PROMPT]);
  assert.deepEqual(result, { ok: true, prompt: NORMAL_PROMPT });
});

test("missing clipboard returns false with the original prompt", async () => {
  const result = await copyCreatePrompt({
    clipboard: undefined,
    prompt: NORMAL_PROMPT,
  });

  assert.deepEqual(result, { ok: false, prompt: NORMAL_PROMPT });
});

test("clipboard rejection returns false with the original prompt", async () => {
  const clipboard = {
    async writeText() {
      throw new Error("permission denied");
    },
  };

  const result = await copyCreatePrompt({
    clipboard,
    prompt: NORMAL_PROMPT,
  });

  assert.deepEqual(result, { ok: false, prompt: NORMAL_PROMPT });
});

test("module source contains no fetch or POST", async () => {
  const source = await readFile(
    new URL("../../backlot/ui/library-onboarding.js", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(source, /\bfetch\b/);
  assert.doesNotMatch(source, /\bPOST\b/);
});
