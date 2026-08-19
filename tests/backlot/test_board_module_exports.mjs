import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

import {
  createBoardContext,
  normalizeBoardState,
  refreshBoard,
  startBoardLiveFeed,
} from "../../backlot/ui/board-core.js";
import {
  renderStageDrawer,
  renderStageRail,
  stageLabel,
  stageNeedsDecision,
} from "../../backlot/ui/board-rail.js";
import {
  commercialContentView,
  isCommercial,
  renderAwaitingNotice,
  renderCommercialBoard,
} from "../../backlot/ui/board-commercial.js";
import { createReplayController } from "../../backlot/ui/board-replay.js";

const selectorContract = JSON.parse(
  await readFile(
    new URL("./fixtures/b1-ui-selector-contract.json", import.meta.url),
    "utf8",
  ),
);
const commercialSource = await readFile(
  new URL("../../backlot/ui/board-commercial.js", import.meta.url),
  "utf8",
);
const editSource = await readFile(
  new URL("../../backlot/ui/board-edit.js", import.meta.url),
  "utf8",
);
const boardSource = await readFile(
  new URL("../../backlot/ui/board.js", import.meta.url),
  "utf8",
);
const railSource = await readFile(
  new URL("../../backlot/ui/board-rail.js", import.meta.url),
  "utf8",
);
const intentSource = await readFile(
  new URL("../../backlot/ui/board-intent-panel.js", import.meta.url),
  "utf8",
);
const EXPECTED_SELECTORS = [
  ".commercial-board",
  ".commercial-beat-card[data-beat]",
  ".stage",
  ".rail",
  ".sse-banner",
  ".sse-refresh-btn",
  ".edit-tab-btn",
  ".commercial-decision-option",
  ".commercial-chat-only",
  ".commercial-stage-status",
  ".commercial-review-fold",
];
const SELECTOR_IMPLEMENTATIONS = {
  ".commercial-board": [commercialSource, "board commercial-board"],
  ".commercial-beat-card[data-beat]": [
    commercialSource,
    ".commercial-beat-card[data-beat=",
  ],
  ".stage": [railSource, "class: `stage "],
  ".rail": [railSource, 'class: "rail"'],
  ".sse-banner": [commercialSource, "sse-banner"],
  ".sse-refresh-btn": [commercialSource, "sse-refresh-btn"],
  ".edit-tab-btn": [boardSource, "edit-tab-btn"],
  ".commercial-decision-option": [intentSource, "commercial-decision-option"],
  ".commercial-chat-only": [
    `${commercialSource}\n${intentSource}`,
    "commercial-chat-only",
  ],
  ".commercial-stage-status": [commercialSource, "commercial-stage-status"],
  ".commercial-review-fold": [commercialSource, "commercial-review-fold"],
};

test("board core exposes stable interfaces", () => {
  assert.equal(typeof createBoardContext, "function");
  assert.equal(typeof normalizeBoardState, "function");
  assert.equal(typeof refreshBoard, "function");
  assert.equal(typeof startBoardLiveFeed, "function");
});

test("board rail exposes stable interfaces", () => {
  assert.equal(typeof stageLabel, "function");
  assert.equal(typeof stageNeedsDecision, "function");
  assert.equal(typeof renderStageRail, "function");
  assert.equal(typeof renderStageDrawer, "function");
});

test("commercial board exposes stable interfaces", () => {
  assert.equal(typeof isCommercial, "function");
  assert.equal(typeof commercialContentView, "function");
  assert.equal(typeof renderAwaitingNotice, "function");
  assert.equal(typeof renderCommercialBoard, "function");
});

test("commercial UI contract fixture remains stable", () => {
  assert.equal(selectorContract.version, "1.0");
  assert.deepEqual(selectorContract.selectors, EXPECTED_SELECTORS);
  for (const selector of selectorContract.selectors) {
    const [source, fragment] = SELECTOR_IMPLEMENTATIONS[selector] || [];
    assert.ok(source?.includes(fragment), `missing selector implementation: ${selector}`);
  }
  for (const copy of selectorContract.copy_contract) {
    assert.ok(
      `${commercialSource}\n${editSource}`.includes(copy),
      `missing copy contract: ${copy}`,
    );
  }
});

test("commercial content follows a paused board stop over stale checkpoints", () => {
  const state = {
    commercial: {
      confirm_stop_ids: ["sample_review", "segment_build", "draft_review"],
      board_stop: {stage: "segment_build", paused: true},
    },
    stages: [
      {name: "sample_review", status: "in_progress"},
      {name: "segment_build", status: "pending"},
      {name: "draft_review", status: "pending"},
    ],
  };
  assert.equal(commercialContentView(state), "segment");
});

test("replay module exposes controller factory", () => {
  assert.equal(typeof createReplayController, "function");
  const controller = createReplayController({ rerender() {} });
  for (const key of ["viewFor", "renderBar", "reset", "isActive"]) {
    assert.equal(typeof controller[key], "function");
  }
});
