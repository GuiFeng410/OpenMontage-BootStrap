import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildCreateProductVideoPrompt,
  copyCreatePrompt,
  formatServiceInfo,
} from "../../backlot/ui/library-onboarding.js";

const EXACT_PROMPT = "请帮我创建一个新的商品宣传片项目。请按默认推荐引导我确认商品主题、时长、素材、制作档位、预算和快速模式；创建后把 Backlot 项目网址发给我。";

test("prompt is exact and mentions Backlot URL", () => {
  const prompt = buildCreateProductVideoPrompt();

  assert.equal(prompt, EXACT_PROMPT);
  assert.match(prompt, /Backlot 项目网址/);
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
    prompt: EXACT_PROMPT,
  });

  assert.deepEqual(writes, [EXACT_PROMPT]);
  assert.deepEqual(result, { ok: true, prompt: EXACT_PROMPT });
});

test("missing clipboard returns false with the original prompt", async () => {
  const result = await copyCreatePrompt({
    clipboard: undefined,
    prompt: EXACT_PROMPT,
  });

  assert.deepEqual(result, { ok: false, prompt: EXACT_PROMPT });
});

test("clipboard rejection returns false with the original prompt", async () => {
  const clipboard = {
    async writeText() {
      throw new Error("permission denied");
    },
  };

  const result = await copyCreatePrompt({
    clipboard,
    prompt: EXACT_PROMPT,
  });

  assert.deepEqual(result, { ok: false, prompt: EXACT_PROMPT });
});

test("module source contains no fetch or POST", async () => {
  const source = await readFile(
    new URL("../../backlot/ui/library-onboarding.js", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(source, /\bfetch\b/);
  assert.doesNotMatch(source, /\bPOST\b/);
});
