export const REVIEW_MODE_KEY = "backlot.review-mode.v1";
export const DEFAULT_REVIEW_MODE = "normal";
export const REVIEW_MODE_IDS = ["minimal", "normal", "pro"] as const;

export type ReviewModeId = (typeof REVIEW_MODE_IDS)[number];

export const COMMERCIAL_STEPS = [
  { id: "brief_locked", label_zh: "方案确认" },
  { id: "assets_gate", label_zh: "素材检查" },
  { id: "sample_review", label_zh: "试片确认" },
  { id: "segment_build", label_zh: "分段制作" },
  { id: "draft_review", label_zh: "初稿审查" },
  { id: "final_compose", label_zh: "合成终稿" },
  { id: "delivery_signoff", label_zh: "交付确认" },
] as const;

const REVIEW_MODE_META: Record<
  ReviewModeId,
  {
    id: ReviewModeId;
    label_zh: string;
    summary_zh: string;
    prompt_guide: string;
    stop_ids: string[];
  }
> = {
  minimal: {
    id: "minimal",
    label_zh: "极简",
    summary_zh:
      "三停：方案、素材、交付。素材通过后直接生成正式段，不做独立试片；失败、缺 Key、超预算才回聊天。",
    prompt_guide: "请按极简模式（方案、素材、交付三停；素材通过后直接生成，不做独立试片）引导",
    stop_ids: ["brief_locked", "assets_gate", "delivery_signoff"],
  },
  normal: {
    id: "normal",
    label_zh: "普通",
    summary_zh: "默认。方案、试片、初稿/问题片段需要你过目；其余本机接着走。",
    prompt_guide: "请按普通评审引导",
    stop_ids: [
      "brief_locked",
      "assets_gate",
      "sample_review",
      "draft_review",
      "delivery_signoff",
    ],
  },
  pro: {
    id: "pro",
    label_zh: "专业",
    summary_zh: "完整七步都展开。分段分批审，确认更多。",
    prompt_guide: "请按专业模式（七步都要我过目）引导",
    stop_ids: COMMERCIAL_STEPS.map((step) => step.id),
  },
};

export function normalizeReviewMode(mode: string | null | undefined): ReviewModeId {
  return REVIEW_MODE_IDS.includes(mode as ReviewModeId)
    ? (mode as ReviewModeId)
    : DEFAULT_REVIEW_MODE;
}

export function listReviewModes() {
  return REVIEW_MODE_IDS.map((id) => ({
    id,
    label_zh: REVIEW_MODE_META[id].label_zh,
    summary_zh: REVIEW_MODE_META[id].summary_zh,
  }));
}

export function getReviewModeRoute(mode: string | null | undefined) {
  const id = normalizeReviewMode(mode);
  const meta = REVIEW_MODE_META[id];
  const stops = new Set(meta.stop_ids);
  const steps = COMMERCIAL_STEPS.map((step, index) => ({
    id: step.id,
    index: index + 1,
    label_zh: step.label_zh,
    stop: stops.has(step.id),
    action_zh: stops.has(step.id) ? "需要你确认" : "本机接着走",
  }));
  return {
    id,
    label_zh: meta.label_zh,
    summary_zh: meta.summary_zh,
    steps,
    confirm_steps: steps
      .filter((step) => step.stop)
      .map((step, index) => ({ ...step, index: index + 1 })),
  };
}

export function buildCreateProductVideoPrompt(mode: string | null | undefined) {
  const id = normalizeReviewMode(mode);
  const guide = REVIEW_MODE_META[id].prompt_guide;
  return (
    `请帮我创建一个新的商品宣传片项目。${guide}我确认商品主题、时长、素材、制作档位和预算；`
    + "创建后把 Backlot 项目网址发给我。"
  );
}

export function readStoredReviewMode(storage: Storage | null | undefined) {
  try {
    return normalizeReviewMode(storage?.getItem?.(REVIEW_MODE_KEY));
  } catch {
    return DEFAULT_REVIEW_MODE;
  }
}

export function writeStoredReviewMode(
  storage: Storage | null | undefined,
  mode: string,
) {
  const id = normalizeReviewMode(mode);
  try {
    storage?.setItem?.(REVIEW_MODE_KEY, id);
  } catch {
    // sessionStorage may throw in private mode; selection still works in memory.
  }
  return id;
}

export function formatServiceInfo({
  host = "未知",
  projectsDir = "未提供",
  projectCount = 0,
}: {
  host?: string;
  projectsDir?: string;
  projectCount?: number;
} = {}) {
  return [
    `本地服务：${host ?? "未知"}`,
    `已发现 ${projectCount ?? 0} 个项目`,
    `项目目录：${projectsDir ?? "未提供"}`,
  ] as const;
}

export async function copyCreatePrompt({
  clipboard,
  prompt,
}: {
  clipboard?: { writeText?: (text: string) => Promise<void> };
  prompt: string;
}) {
  try {
    if (typeof clipboard?.writeText !== "function") {
      return { ok: false, prompt };
    }
    await clipboard.writeText(prompt);
    return { ok: true, prompt };
  } catch {
    return { ok: false, prompt };
  }
}
