import assert from "node:assert/strict";
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
