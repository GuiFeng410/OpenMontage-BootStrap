import { el, getJSON } from "./lib.js";

const TIERS = [
  { id: "light", label_zh: "轻度", hint: "适合简单讲解类说明" },
  { id: "medium", label_zh: "中度", hint: "适合用素材库画面做产品介绍" },
  { id: "heavy", label_zh: "重度", hint: "电商视频选这个" },
];
const VIDEO_MODEL_CATALOG = [
  {
    id: "agnes-video-v2.0",
    channel: "agnes",
    label_zh: "Agnes",
    keyNames: ["AGNES_API_KEY", "AGNES_AI_API_KEY"],
    capability_zh: "超长自动切段拼接。",
    board_generate: true,
  },
  {
    id: "hy-video-1.5",
    channel: "tokenhub",
    label_zh: "TokenHub·混元",
    keyNames: ["TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY"],
    capability_zh: "看板可开烧。单段时长由模型定，长片自动拼接。",
    board_generate: true,
  },
  {
    id: "pixverse-video-v6.0",
    channel: "tokenhub",
    label_zh: "TokenHub·Pixverse",
    keyNames: ["TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY"],
    capability_zh: "看板可开烧。默认可约 5 秒一段，长片自动拼接。",
    board_generate: true,
  },
];
const AI_PRESETS = [50, 70, 100];
const AI_STEP = 10;
const AI_MIN = 0;
const AI_MAX = 100;
const DEFAULT_AI_PCT = 100;

let keyFlags = null;
let selectedTier = "light";
let selectedAiPct = DEFAULT_AI_PCT;
let selectedModelId = "";
let capOpen = false;
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

function clampAiPct(raw, fallback = DEFAULT_AI_PCT) {
  const n = Number(raw);
  if (!Number.isFinite(n)) return fallback;
  const bounded = Math.max(AI_MIN, Math.min(AI_MAX, n));
  return Math.round(bounded / AI_STEP) * AI_STEP;
}

function initialAiPct(lockedAiSharePct, lockedMotionMix) {
  if (lockedAiSharePct != null && String(lockedAiSharePct).trim() !== "") {
    return clampAiPct(lockedAiSharePct);
  }
  const mix = String(lockedMotionMix || "").replace("：", ":");
  if (mix === "0:1") return 100;
  if (mix === "1:2") return 70;
  if (mix === "1:1") return 50;
  if (mix === "2:1") return 30;
  return DEFAULT_AI_PCT;
}

function videoModels() {
  const fromApi = Array.isArray(keyFlags?.video_models) ? keyFlags.video_models : [];
  const rows = fromApi.length
    ? fromApi
    : VIDEO_MODEL_CATALOG.map((spec) => {
      const names = new Set(keyFlags?.video_key_names_present || []);
      const keyReady = spec.keyNames.some((name) => names.has(name));
      return {
        id: spec.id,
        channel: spec.channel,
        label_zh: spec.label_zh,
        capability_zh: spec.capability_zh,
        board_generate: spec.board_generate !== false,
        key_ready: keyReady,
        available: keyReady && spec.board_generate !== false,
      };
    });
  return rows.map((item) => {
    const board = item.board_generate !== false;
    return {
      ...item,
      board_generate: board,
      available: Boolean(item.available) && board,
    };
  });
}

function firstAvailableModelId() {
  const hit = videoModels().find((item) => item.available);
  return hit?.id || "";
}

function applyFlags(flags) {
  keyFlags = flags || keyFlags || {};
  if (!selectedModelId) {
    selectedModelId = firstAvailableModelId();
  }
}

function blockMessage(tier) {
  if (tier === "heavy" && !keyFlags?.video_key_present) {
    return "重度需要已填 Key 的视频模型。可开烧：Agnes、混元、Pixverse。请写入对应 Key 后刷新。";
  }
  if (tier === "heavy" && !selectedModelId) {
    return "请选择一个已填入 Key 的视频模型。可开烧：Agnes、混元、Pixverse。";
  }
  const picked = videoModels().find((item) => item.id === selectedModelId);
  if (tier === "heavy" && picked && !picked.board_generate) {
    return "当前模型看板暂不能开烧，不会改走其它渠道。请改选已接线模型，或回库页中断后新建。";
  }
  if (tier === "medium" && !keyFlags?.stock_key_present) {
    return "中度需要素材库 Key（Pexels 或 Pixabay）。请写入仓根 .env 后点「已填入 Key，刷新可用性」。";
  }
  return "";
}

function renderAiMix({ requestRender }) {
  const value = el("div", { class: "tier-ai-value" }, `AI ${selectedAiPct}%`);
  const minus = el("button", { type: "button", class: "tier-ai-step", "aria-label": "降低 AI 占比" }, "←");
  minus.addEventListener("click", () => {
    selectedAiPct = Math.max(AI_MIN, selectedAiPct - AI_STEP);
    statusText = "";
    if (typeof requestRender === "function") requestRender();
  });
  const plus = el("button", { type: "button", class: "tier-ai-step", "aria-label": "提高 AI 占比" }, "→");
  plus.addEventListener("click", () => {
    selectedAiPct = Math.min(AI_MAX, selectedAiPct + AI_STEP);
    statusText = "";
    if (typeof requestRender === "function") requestRender();
  });
  const presets = el("div", { class: "tier-ai-presets" });
  for (const pct of AI_PRESETS) {
    const selected = selectedAiPct === pct;
    const btn = el("button", {
      type: "button",
      class: `tier-ai-preset${selected ? " selected" : ""}`,
    }, pct === 100 ? `${pct}% 默认` : `${pct}%`);
    btn.addEventListener("click", () => {
      selectedAiPct = pct;
      statusText = "";
      if (typeof requestRender === "function") requestRender();
    });
    presets.append(btn);
  }
  return el("div", { class: "tier-ai-mix" },
    el("div", { class: "tier-ai-label" }, "AI 占比"),
    el("div", { class: "tier-ai-row" }, minus, value, plus),
    presets,
    el("div", { class: "tier-ai-hint" },
      `运镜约 ${100 - selectedAiPct}% · 具体生成情况视模型能力而定`));
}

function renderModelPicker({ requestRender }) {
  const list = el("div", { class: "tier-model-options" });
  const models = videoModels();
  const selected = models.find((item) => item.id === selectedModelId) || models.find((item) => item.available);
  for (const item of models) {
    const isSelected = selectedModelId === item.id;
    const canSelect = Boolean(item.available);
    const button = el("button", {
      type: "button",
      class: `tier-model-option${isSelected ? " selected" : ""}${canSelect ? "" : " disabled"}`,
      disabled: canSelect ? null : "",
      "aria-pressed": isSelected ? "true" : "false",
    }, item.board_generate === false ? `${item.label_zh}（看板暂不能开烧）` : item.label_zh);
    if (canSelect) {
      button.addEventListener("click", () => {
        selectedModelId = item.id;
        statusText = "";
        if (typeof requestRender === "function") requestRender();
      });
    }
    list.append(button);
  }
  if (!models.some((item) => item.available)) {
    list.append(el("div", { class: "tier-model-empty" },
      "没有看板能开烧的模型。请写入 Agnes Key 后刷新。混元 / Pixverse 暂不能在看板开烧。"));
  }
  const cap = el("details", { class: "tier-model-cap" });
  if (capOpen) cap.open = true;
  cap.append(el("summary", {}, "能力说明"));
  cap.append(el("div", {},
    selected?.capability_zh || "请先选择已填入 Key 的模型。",
    " 具体生成情况视模型能力而定。"));
  cap.addEventListener("toggle", () => {
    capOpen = cap.open;
  });
  return el("div", { class: "tier-model-picker" },
    el("div", { class: "tier-ai-label" }, "视频模型"),
    list,
    cap);
}

export function renderProductionTierPanel({
  projectId,
  lockedTier,
  lockedAiSharePct,
  lockedMotionMix,
  lockedVideoModel,
  requestRender,
  requestRefresh,
}) {
  const locked = lockedTierId(lockedTier);
  if (loadedFor !== projectId) {
    loadedFor = projectId;
    keyFlags = null;
    selectedTier = locked || "light";
    selectedAiPct = initialAiPct(lockedAiSharePct, lockedMotionMix);
    selectedModelId = String(lockedVideoModel || "").trim();
    capOpen = false;
    statusText = "";
  } else if (locked && selectedTier !== locked && !busy) {
    selectedTier = locked;
  }

  if (!keyFlags) {
    getJSON("/api/health")
      .then((flags) => {
        applyFlags(flags);
        if (!selectedModelId) selectedModelId = firstAvailableModelId();
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
      if (tier.id === "heavy" && !selectedModelId) {
        selectedModelId = firstAvailableModelId();
      }
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
      applyFlags(payload);
      statusText = payload.friendly_zh || "已刷新。";
    } catch {
      statusText = "刷新失败。请确认本机看板仍在运行，然后重试。";
    } finally {
      busy = false;
      const redraw = requestRefresh || requestRender;
      if (typeof redraw === "function") redraw();
    }
  });

  const flagsReady = keyFlags !== null;
  const blocked = flagsReady ? blockMessage(selectedTier) : "";
  const startBtn = el("button", {
    type: "button",
    class: "tier-start-btn",
    disabled: busy || (selectedTier === "heavy" && !flagsReady) || blocked ? "" : null,
    title: blocked || "锁定制作档。本页不会直接调付费接口。",
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
      const body = { production_tier: selectedTier };
      if (selectedTier === "heavy") {
        body.ai_share_pct = selectedAiPct;
        body.video_model = selectedModelId;
      }
      const response = await fetch(
        `/api/project/${encodeURIComponent(projectId)}/start-production`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
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
      const redraw = requestRefresh || requestRender;
      if (typeof redraw === "function") redraw();
    }
  });

  if (blocked && !statusText) {
    statusText = blocked;
  }
  const children = [
    el("div", { class: "tier-panel-head" }, el("b", {}, "制作档位")),
    options,
  ];
  if (selectedTier === "heavy") {
    children.push(el("div", { class: "tier-heavy-tools" },
      renderModelPicker({ requestRender }),
      renderAiMix({ requestRender })));
  }
  children.push(el("div", { class: "tier-panel-actions" }, refreshBtn, startBtn));
  if (statusText) {
    children.push(el("div", { class: "tier-panel-feedback", role: "status" }, statusText));
  }
  return el("div", { class: "notice commercial-tier-panel" }, ...children);
}
