import assert from "node:assert/strict";
import test from "node:test";

import {
  clearDraft,
  createDraft,
  decisionRevision,
  inspectStoredDraft,
  restoreDraft,
  saveDraft,
  selectOption,
  setDraftNote,
  summarizeDraft,
} from "../../backlot/ui/board-intent-state.js";

function memoryStorage() {
  const values = new Map();
  return {
    values,
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

function baseDraft() {
  return createDraft({
    projectId: "jade",
    stage: "brief_locked",
    revision: "h1",
  });
}

test("same decision payload has a stable canonical revision", () => {
  const first = decisionRevision({
    projectId: "jade",
    stage: "brief_locked",
    timestamp: "2026-08-13T00:00:00Z",
    decision: {
      prompt_zh: "请选择制作档位",
      options: [{ id: "heavy", metadata: { z: 2, a: 1 } }],
      title_zh: "制作档位",
    },
  });
  const reordered = decisionRevision({
    timestamp: "2026-08-13T00:00:00Z",
    stage: "brief_locked",
    projectId: "jade",
    decision: {
      title_zh: "制作档位",
      options: [{ metadata: { a: 1, z: 2 }, id: "heavy" }],
      prompt_zh: "请选择制作档位",
    },
  });

  assert.match(first, /^h[0-9a-z]+$/);
  assert.equal(first, reordered);
});

test("revision changes when identity or decision content changes", () => {
  const input = {
    projectId: "jade",
    stage: "brief_locked",
    timestamp: "2026-08-13T00:00:00Z",
    decision: {
      title_zh: "制作档位",
      prompt_zh: "请选择制作档位",
      options: [{ id: "heavy" }],
    },
  };
  const baseline = decisionRevision(input);
  const variants = [
    { ...input, projectId: "opal" },
    { ...input, stage: "product_info" },
    { ...input, timestamp: "2026-08-13T00:01:00Z" },
    { ...input, decision: { ...input.decision, title_zh: "新标题" } },
    { ...input, decision: { ...input.decision, prompt_zh: "新提示" } },
    {
      ...input,
      decision: { ...input.decision, options: [{ id: "medium" }] },
    },
  ];

  for (const variant of variants) {
    assert.notEqual(decisionRevision(variant), baseline);
  }
});

test("createDraft returns the fixed versioned shape", () => {
  const draft = baseDraft();

  assert.equal(draft.version, "1.0");
  assert.equal(draft.project_id, "jade");
  assert.equal(draft.stage, "brief_locked");
  assert.equal(draft.revision, "h1");
  assert.deepEqual(draft.selections, []);
  assert.equal(draft.note, "");
  assert.equal(Number.isNaN(Date.parse(draft.updated_at)), false);
});

test("selectOption replaces one decision without mutating its source", () => {
  const source = baseDraft();
  const first = selectOption(source, "brief_locked::production_tier", {
    id: "heavy",
    label_zh: "重度",
    description_zh: "不应进入草稿",
  });
  const second = selectOption(first, "brief_locked::production_tier", {
    option_id: "medium",
    label_zh: "中度",
    impact_zh: "不应进入草稿",
  });

  assert.deepEqual(source.selections, []);
  assert.deepEqual(first.selections, [{
    decision_key: "brief_locked::production_tier",
    option_id: "heavy",
    label_zh: "重度",
  }]);
  assert.deepEqual(second.selections, [{
    decision_key: "brief_locked::production_tier",
    option_id: "medium",
    label_zh: "中度",
  }]);
});

test("different decision keys coexist", () => {
  const tier = selectOption(baseDraft(), "tier", {
    id: "heavy",
    label_zh: "重度",
  });
  const runtime = selectOption(tier, "runtime", {
    id: "hyperframes",
    label_zh: "HyperFrames",
  });

  assert.deepEqual(runtime.selections.map((item) => item.decision_key), [
    "tier",
    "runtime",
  ]);
});

test("setDraftNote preserves input while summary trims display copy", () => {
  const source = baseDraft();
  const noted = setDraftNote(source, "  保留片尾品牌标识  ");

  assert.equal(source.note, "");
  assert.equal(noted.note, "  保留片尾品牌标识  ");
  assert.match(summarizeDraft(noted), /备注：保留片尾品牌标识/);
  assert.doesNotMatch(summarizeDraft(noted), /备注：  /);
});

test("summary contains pending wording, identity and numbered choices", () => {
  const selected = selectOption(baseDraft(), "tier", {
    id: "heavy",
    label_zh: "重度",
  });
  const summary = summarizeDraft(selected);

  assert.match(summary, /【Backlot待确认】/);
  assert.match(summary, /jade/);
  assert.match(summary, /brief_locked/);
  assert.match(summary, /1[.、]\s*重度/);
  assert.match(summary, /点「进入下一步」后请留在本页/);
  assert.match(summary, /尚未正式执行/);
  assert.doesNotMatch(summary, /请回聊天发送：确认面板选择/);
  assert.doesNotMatch(summary, /已批准|正式批准|已执行/);
});

test("a draft restores only for the same revision", () => {
  const storage = memoryStorage();
  const draft = selectOption(baseDraft(), "tier", {
    id: "heavy",
    label_zh: "重度",
  });
  saveDraft(storage, draft);

  assert.deepEqual(
    restoreDraft(storage, {
      projectId: "jade",
      stage: "brief_locked",
      revision: "h1",
    }),
    draft,
  );
  assert.equal(
    restoreDraft(storage, {
      projectId: "jade",
      stage: "brief_locked",
      revision: "different",
    }),
    null,
  );
});

test("stored draft inspection distinguishes missing current and stale revisions", () => {
  const storage = memoryStorage();
  const identity = {
    projectId: "jade",
    stage: "brief_locked",
    revision: "h1",
  };

  assert.deepEqual(inspectStoredDraft(storage, identity), {
    status: "missing",
    draft: null,
  });

  const draft = selectOption(baseDraft(), "tier", {
    id: "heavy",
    label_zh: "重度",
  });
  saveDraft(storage, draft);
  assert.deepEqual(inspectStoredDraft(storage, identity), {
    status: "current",
    draft,
  });
  assert.deepEqual(inspectStoredDraft(storage, {
    ...identity,
    revision: "h2",
  }), {
    status: "stale",
    draft: null,
  });
});

test("invalid stored JSON or draft identity returns null", () => {
  const storage = memoryStorage();
  const key = "backlot.intent-draft.v1:jade:brief_locked";
  storage.setItem(key, "{invalid");
  assert.deepEqual(
    inspectStoredDraft(storage, {
      projectId: "jade",
      stage: "brief_locked",
      revision: "h1",
    }),
    { status: "corrupt", draft: null },
  );
  assert.equal(
    restoreDraft(storage, {
      projectId: "jade",
      stage: "brief_locked",
      revision: "h1",
    }),
    null,
  );

  for (const invalid of [
    { ...baseDraft(), version: "2.0" },
    { ...baseDraft(), project_id: "opal" },
    { ...baseDraft(), stage: "product_info" },
  ]) {
    storage.setItem(key, JSON.stringify(invalid));
    assert.equal(
      restoreDraft(storage, {
        projectId: "jade",
        stage: "brief_locked",
        revision: "h1",
      }),
      null,
    );
  }
});

test("storage failures are contained", () => {
  const throwingStorage = {
    getItem() {
      throw new Error("read failed");
    },
    setItem() {
      throw new Error("write failed");
    },
    removeItem() {
      throw new Error("remove failed");
    },
  };

  assert.doesNotThrow(() => saveDraft(throwingStorage, baseDraft()));
  assert.equal(
    restoreDraft(throwingStorage, {
      projectId: "jade",
      stage: "brief_locked",
      revision: "h1",
    }),
    null,
  );
  assert.doesNotThrow(() => clearDraft(throwingStorage, {
    projectId: "jade",
    stage: "brief_locked",
  }));
});

test("clearDraft removes only the exact project-stage key", () => {
  const storage = memoryStorage();
  storage.setItem("backlot.intent-draft.v1:jade:brief_locked", "target");
  storage.setItem("backlot.intent-draft.v1:jade:product_info", "keep-stage");
  storage.setItem("backlot.intent-draft.v1:opal:brief_locked", "keep-project");

  clearDraft(storage, { projectId: "jade", stage: "brief_locked" });

  assert.equal(
    storage.getItem("backlot.intent-draft.v1:jade:brief_locked"),
    null,
  );
  assert.equal(
    storage.getItem("backlot.intent-draft.v1:jade:product_info"),
    "keep-stage",
  );
  assert.equal(
    storage.getItem("backlot.intent-draft.v1:opal:brief_locked"),
    "keep-project",
  );
});
