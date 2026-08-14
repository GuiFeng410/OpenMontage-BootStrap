import assert from "node:assert/strict";
import test from "node:test";

import {
  formatIntentStatusLine,
  intentStatusZh,
} from "../../backlot/ui/board-commercial.js";

test("intentStatusZh maps interaction statuses to Chinese labels", () => {
  assert.equal(intentStatusZh("pending"), "待确认");
  assert.equal(intentStatusZh("planned"), "已汇总");
  assert.equal(intentStatusZh("approved"), "聊天已确认");
  assert.equal(intentStatusZh("applied"), "已执行");
  assert.equal(intentStatusZh("superseded"), "已作废");
  assert.equal(intentStatusZh("rejected"), "已拒绝");
  assert.equal(intentStatusZh("failed"), "失败");
  assert.equal(intentStatusZh("unknown"), "");
});

test("formatIntentStatusLine is status · summary", () => {
  assert.equal(
    formatIntentStatusLine({ status: "pending", summary: "采用轻度档" }),
    "待确认 · 采用轻度档",
  );
});

test("status labels never look like the page already approved", () => {
  const labels = [
    "pending",
    "planned",
    "approved",
    "applied",
    "superseded",
    "rejected",
    "failed",
  ].map(intentStatusZh).join(" ");
  for (const forbidden of ["立即创建", "开始生成", "已生效"]) {
    assert.equal(labels.includes(forbidden), false);
  }
});
