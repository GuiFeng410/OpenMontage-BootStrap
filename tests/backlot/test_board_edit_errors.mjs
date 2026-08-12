import assert from "node:assert/strict";
import test from "node:test";

import { submitErrorMessage } from "../../backlot/ui/board-edit-errors.js";

test("gate 409 shows the server reason and friendly message", () => {
  const message = submitErrorMessage(409, {
    kind: "editing_gate",
    reason_codes: ["compose_required"],
    friendly_zh: "cuts 已应用，需要重合成后再提交。",
  });

  assert.equal(
    message,
    "cuts 已应用，需要重合成后再提交。（compose_required）",
  );
});

test("conflict 409 keeps the duplicate submission message", () => {
  assert.equal(
    submitErrorMessage(409, "intent_id already exists"),
    "这组改动之前已经提交过了，无需重复提交。",
  );
});
