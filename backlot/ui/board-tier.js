import { el, getJSON } from "./lib.js";

const TIERS = [
  { id: "light", label_zh: "轻度", hint: "零 Key / Remotion 等" },
  { id: "medium", label_zh: "中度", hint: "需要 Pexels 或 Pixabay Key" },
  { id: "heavy", label_zh: "重度", hint: "需要视频模型 Key" },
];

let keyFlags = null;
let selectedTier = "light";
let busy = false;
let statusText = "";
let loadedFor = "";

function lockedTierId(raw) {
  const value = String(raw || "").trim();
  if (value === "轻" || value === "light") return "light";
  if (value === "中" || value === "medium") return "medium";
  if (value === "重" || value === "heavy") return "heavy";
  return "";
}

function applyFlags(flags, { preferLocked } = {}) {
  keyFlags = flags || keyFlags || {};
  const locked = preferLocked || "";
  if (locked) selectedTier = locked;
  else if (!keyFlags.video_key_present && selectedTier === "heavy") {
    selectedTier = "light";
  }
}

function statusLine() {
  const video = Boolean(keyFlags?.video_key_present);
  const stock = Boolean(keyFlags?.stock_key_present);
  const parts = [];
  parts.push(video ? "重度可用" : "重度需要视频模型 Key");
  parts.push(stock ? "中度可用" : "中度需要素材库 Key");
  if (keyFlags?.scanned_at) parts.push(`刷新于 ${String(keyFlags.scanned_at).replace("T", " ").slice(0, 19)}`);
  return parts.join(" · ");
}

function blockMessage(tier) {
  if (tier === "heavy" && !keyFlags?.video_key_present) {
    return "重度需要视频模型 Key。请写入仓根 .env 后点「已填入 Key，刷新可用性」。";
  }
  if (tier === "medium" && !keyFlags?.stock_key_present) {
    return "中度需要素材库 Key（Pexels 或 Pixabay）。请写入仓根 .env 后点「已填入 Key，刷新可用性」。";
  }
  return "";
}

export function renderProductionTierPanel({
  projectId,
  lockedTier,
  requestRender,
}) {
  const locked = lockedTierId(lockedTier);
  if (loadedFor !== projectId) {
    loadedFor = projectId;
    keyFlags = null;
    selectedTier = locked || "light";
    statusText = "";
  } else if (locked && selectedTier !== locked && !busy) {
    selectedTier = locked;
  }

  if (!keyFlags) {
    getJSON("/api/health")
      .then((flags) => {
        applyFlags(flags, { preferLocked: locked });
        if (typeof requestRender === "function") requestRender();
      })
      .catch(() => {
        keyFlags = {
          video_key_present: false,
          stock_key_present: false,
        };
        if (typeof requestRender === "function") requestRender();
      });
  }

  const options = el("div", { class: "tier-picker-options" });
  for (const tier of TIERS) {
    const selected = selectedTier === tier.id;
    const button = el("button", {
      type: "button",
      class: `tier-picker-option${selected ? " selected" : ""}`,
      "data-tier": tier.id,
      "aria-pressed": selected ? "true" : "false",
    },
      el("b", {}, tier.label_zh),
      el("span", {}, tier.hint));
    button.addEventListener("click", () => {
      selectedTier = tier.id;
      statusText = "";
      if (typeof requestRender === "function") requestRender();
    });
    options.append(button);
  }

  const refreshBtn = el("button", {
    type: "button",
    class: "tier-refresh-btn",
    disabled: busy ? "" : null,
  }, "已填入 Key，刷新可用性");
  refreshBtn.addEventListener("click", async () => {
    busy = true;
    statusText = "正在刷新…";
    if (typeof requestRender === "function") requestRender();
    try {
      const response = await fetch("/api/keys/refresh", { method: "POST" });
      const payload = await response.json();
      applyFlags(payload, { preferLocked: locked });
      statusText = payload.friendly_zh || "已刷新。";
    } catch {
      statusText = "刷新失败。请确认本机看板仍在运行，然后重试。";
    } finally {
      busy = false;
      if (typeof requestRender === "function") requestRender();
    }
  });

  const startBtn = el("button", {
    type: "button",
    class: "tier-start-btn",
    disabled: busy ? "" : null,
  }, "确认开始出片");
  startBtn.addEventListener("click", async () => {
    const blocked = blockMessage(selectedTier);
    if (blocked) {
      statusText = blocked;
      window.alert(blocked);
      if (typeof requestRender === "function") requestRender();
      return;
    }
    busy = true;
    statusText = "正在锁定制作档…";
    if (typeof requestRender === "function") requestRender();
    try {
      const response = await fetch(
        `/api/project/${encodeURIComponent(projectId)}/start-production`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ production_tier: selectedTier }),
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = payload.detail || payload;
        const message = detail.friendly_zh || "无法开始出片。";
        statusText = message;
        window.alert(message);
        return;
      }
      applyFlags(payload);
      statusText = payload.friendly_zh || "已锁定制作档。";
    } catch {
      statusText = "开始失败。请留在本页重试。";
    } finally {
      busy = false;
      if (typeof requestRender === "function") requestRender();
    }
  });

  return el("div", { class: "notice commercial-tier-panel" },
    el("div", { class: "tier-panel-head" },
      el("b", {}, "制作档位"),
      el("span", { class: "tier-panel-status" }, statusLine())),
    el("p", { class: "tier-panel-copy" },
      "轻 / 中 / 重始终可点。缺 Key 时仍可选重度，点开始会被拦住。补好 .env 后点刷新即可。"),
    options,
    el("div", { class: "tier-panel-actions" }, refreshBtn, startBtn),
    statusText
      ? el("div", { class: "tier-panel-feedback", role: "status" }, statusText)
      : null);
}
