export const TIERS = [
  { id: "light", label_zh: "轻度", hint: "适合简单讲解类说明" },
  { id: "medium", label_zh: "中度", hint: "适合用素材库画面做产品介绍" },
  { id: "heavy", label_zh: "重度", hint: "电商视频选这个" },
] as const;

export const VIDEO_MODEL_CATALOG = [
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
] as const;

export const AI_PRESETS = [50, 70, 100] as const;
export const AI_STEP = 10;
export const AI_MIN = 0;
export const AI_MAX = 100;
export const DEFAULT_AI_PCT = 100;

export type VideoModelFlag = {
  id: string;
  channel?: string;
  label_zh?: string;
  capability_zh?: string;
  board_generate?: boolean;
  key_ready?: boolean;
  available?: boolean;
};

export type KeyFlags = {
  video_key_present?: boolean;
  stock_key_present?: boolean;
  video_key_names_present?: string[];
  video_models?: VideoModelFlag[];
  friendly_zh?: string;
};

export type ResolvedVideoModel = {
  id: string;
  channel?: string;
  label_zh: string;
  capability_zh?: string;
  board_generate: boolean;
  key_ready?: boolean;
  available: boolean;
};

export function lockedTierId(raw: unknown): "light" | "medium" | "heavy" | "" {
  const value = String(raw || "").trim();
  if (value === "轻" || value === "轻度" || value === "light") return "light";
  if (value === "中" || value === "中度" || value === "medium") return "medium";
  if (value === "重" || value === "重度" || value === "heavy") return "heavy";
  return "";
}

export function clampAiPct(raw: unknown, fallback = DEFAULT_AI_PCT): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return fallback;
  const bounded = Math.max(AI_MIN, Math.min(AI_MAX, n));
  return Math.round(bounded / AI_STEP) * AI_STEP;
}

export function initialAiPct(lockedAiSharePct: unknown, lockedMotionMix: unknown): number {
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

export function videoModels(keyFlags: KeyFlags | null | undefined): ResolvedVideoModel[] {
  const fromApi = Array.isArray(keyFlags?.video_models) ? keyFlags.video_models : [];
  const rows: ResolvedVideoModel[] = fromApi.length
    ? fromApi.map((item) => ({
        id: String(item.id || ""),
        channel: item.channel,
        label_zh: String(item.label_zh || item.id || ""),
        capability_zh: item.capability_zh,
        board_generate: item.board_generate !== false,
        key_ready: item.key_ready,
        available: Boolean(item.available),
      }))
    : VIDEO_MODEL_CATALOG.map((spec) => {
        const names = new Set(keyFlags?.video_key_names_present || []);
        const keyReady = spec.keyNames.some((name) => names.has(name));
        const board = Boolean(spec.board_generate);
        return {
          id: spec.id,
          channel: spec.channel,
          label_zh: spec.label_zh,
          capability_zh: spec.capability_zh,
          board_generate: board,
          key_ready: keyReady,
          available: keyReady && board,
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

export function firstAvailableModelId(keyFlags: KeyFlags | null | undefined): string {
  const hit = videoModels(keyFlags).find((item) => item.available);
  return hit?.id || "";
}

export function blockMessage(
  tier: string,
  keyFlags: KeyFlags | null | undefined,
  selectedModelId: string,
): string {
  if (tier === "heavy" && !keyFlags?.video_key_present) {
    return "重度需要已填 Key 的视频模型。可开烧：Agnes、混元、Pixverse。请写入对应 Key 后刷新。";
  }
  if (tier === "heavy" && !selectedModelId) {
    return "请选择一个已填入 Key 的视频模型。可开烧：Agnes、混元、Pixverse。";
  }
  const picked = videoModels(keyFlags).find((item) => item.id === selectedModelId);
  if (tier === "heavy" && picked && !picked.board_generate) {
    return "当前模型看板暂不能开烧，不会改走其它渠道。请改选已接线模型，或回库页中断后新建。";
  }
  if (tier === "medium" && !keyFlags?.stock_key_present) {
    return "中度需要素材库 Key（Pexels 或 Pixabay）。请写入仓根 .env 后点「已填入 Key，刷新可用性」。";
  }
  return "";
}
