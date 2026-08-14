const CREATE_PRODUCT_VIDEO_PROMPT = "请帮我创建一个新的商品宣传片项目。请按默认推荐引导我确认商品主题、时长、素材、制作档位、预算和快速模式；创建后把 Backlot 项目网址发给我。";

export function buildCreateProductVideoPrompt() {
  return CREATE_PRODUCT_VIDEO_PROMPT;
}

export function formatServiceInfo({
  host = "未知",
  projectsDir = "未提供",
  projectCount = 0,
} = {}) {
  return [
    `本地服务：${host ?? "未知"}`,
    `已发现 ${projectCount ?? 0} 个项目`,
    `项目目录：${projectsDir ?? "未提供"}`,
  ];
}

export async function copyCreatePrompt({ clipboard, prompt }) {
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
