import { el, fmtAgo, getJSON, subscribe, thumbURL } from "/ui/lib.js";
import {
  buildCreateProductVideoPrompt,
  copyCreatePrompt,
  formatServiceInfo,
} from "/ui/library-onboarding.js";

const grid = document.getElementById("grid");
const onboarding = document.getElementById("onboarding");
const THEME_KEY = "backlot.theme";
const LABELS = {
  "NO MEDIA YET": "暂无媒体",
  "AWAITING YOU": "等待确认",
  "LIVE": "进行中",
  "IDLE": "空闲",
  "projects": "个项目",
  "scenes": "个场景",
  "renders": "个成片",
  "unknown": "未识别管线",
};
let currentTheme = localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";

function applyTheme(theme) {
  currentTheme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = currentTheme;
  localStorage.setItem(THEME_KEY, currentTheme);
}

function renderThemeToggle() {
  const next = currentTheme === "light" ? "dark" : "light";
  const nextLabel = next === "light" ? "浅色" : "深色";
  return el("button", {
    class: "theme-toggle",
    type: "button",
    title: `切换到${nextLabel}主题`,
    "aria-label": `切换到${nextLabel}主题`,
    "aria-pressed": currentTheme === "light" ? "true" : "false",
    onclick: () => {
      applyTheme(next);
      const replacement = renderThemeToggle();
      document.querySelector(".theme-toggle").replaceWith(replacement);
    },
  }, el("span", { class: "theme-toggle-icon", "aria-hidden": "true" }, currentTheme === "light" ? "☾" : "☀"));
}

applyTheme(currentTheme);
document.getElementById("liveBadge").before(renderThemeToggle());

function miniRail(states) {
  const rail = el("div", { class: "mini-rail" });
  for (const s of states) {
    const cls = s.status === "completed" ? "d"
      : s.status === "in_progress" ? "a"
      : s.status === "awaiting_human" ? "w" : "";
    rail.append(el("i", { class: cls, title: `${s.name}: ${s.status}` }));
  }
  return rail;
}

function renderOnboarding(health, projectCount) {
  const prompt = buildCreateProductVideoPrompt();
  const [serviceLine, countLine, rootLine] = formatServiceInfo({
    host: location.host,
    projectsDir: health?.projects_dir,
    projectCount,
  });
  const promptField = el("textarea", {
    class: "library-onboarding-prompt",
    readonly: "",
    rows: "4",
    "aria-label": "创建商品片请求",
  }, prompt);
  const feedback = el("p", {
    class: "library-onboarding-feedback",
    "aria-live": "polite",
  }, "复制请求后，回聊天发送。");
  const copyButton = el("button", {
    class: "library-onboarding-copy",
    type: "button",
    onclick: async () => {
      const result = await copyCreatePrompt({
        clipboard: navigator.clipboard,
        prompt,
      });
      if (result.ok) {
        feedback.textContent = "已复制，请回聊天粘贴并发送。";
        return;
      }
      feedback.textContent = "无法自动复制，请选中下方文本并手动复制到聊天。";
      promptField.focus();
      promptField.select();
    },
  }, "复制“创建商品片”请求");

  onboarding.replaceChildren(
    el("div", { class: "library-onboarding-head" },
      el("div", {},
        el("h2", { id: "onboardingTitle" }, "创建新商品片"),
        el("p", {},
          "Backlot 负责展示项目和生产证据；正式项目由 Agent 在聊天中创建。"),
      ),
      copyButton,
    ),
    promptField,
    feedback,
    el("div", { class: "library-service-list", "aria-label": "服务信息" },
      el("span", {}, serviceLine),
      el("span", {}, countLine),
    ),
    el("details", { class: "library-service-details" },
      el("summary", {}, "技术信息"),
      el("p", {}, rootLine),
    ),
  );
}

function card(p) {
  const poster = el("div", { class: "lib-poster" });
  if (p.poster) {
    poster.append(el("img", { src: thumbURL(p.project_id, p.poster, 640), loading: "lazy", alt: "" }));
  } else {
    poster.append(el("span", { class: "lp-txt" }, LABELS["NO MEDIA YET"]));
  }
  if (p.live && p.active_stage) {
    poster.append(el("span", { class: "lp-live" },
      el("span", { class: "dot" }),
      p.awaiting_human
        ? `◈ ${LABELS["AWAITING YOU"]}`
        : `${LABELS.LIVE} · ${p.active_stage.toUpperCase()}`));
  } else if (p.awaiting_human) {
    poster.append(el("span", { class: "lp-live" }, `◈ ${LABELS["AWAITING YOU"]}`));
  }

  const meta = el("div", { class: "lb-meta" },
    el("span", { class: "chip" }, p.pipeline_type || LABELS.unknown),
    p.scene_count ? el("span", { class: "chip" }, `${p.scene_count} ${LABELS.scenes}`) : null,
    p.render_count ? el("span", { class: "chip" }, `${p.render_count} ${LABELS.renders}`) : null,
    el("span", { class: "when" }, fmtAgo(p.last_activity)),
  );

  const staticSuffix = new URLSearchParams(location.search).has("static") ? "?static=1" : "";
  return el("a", { class: `lib-card${p.live ? " live-card" : ""}`, href: `/p/${p.project_id}${staticSuffix}`, style: "text-decoration:none;color:inherit" },
    poster,
    el("div", { class: "lib-body" },
      el("h3", {}, p.title || p.project_id),
      meta,
      p.stage_states.length ? miniRail(p.stage_states) : null,
    ),
  );
}

async function render() {
  const [projects, health] = await Promise.all([
    getJSON("/api/projects"),
    getJSON("/api/health").catch(() => ({ projects_dir: "未提供" })),
  ]);
  document.getElementById("count").textContent = `${projects.length} ${LABELS.projects}`;
  const liveCount = projects.filter((p) => p.live).length;
  const badge = document.getElementById("liveBadge");
  badge.classList.toggle("idle", liveCount === 0);
  document.getElementById("liveText").textContent = liveCount
    ? `${liveCount} ${LABELS.LIVE}`
    : LABELS.IDLE;
  renderOnboarding(health, projects.length);
  grid.innerHTML = "";
  document.getElementById("empty").style.display = projects.length ? "none" : "block";
  for (const p of projects) grid.append(card(p));
}

render().catch(console.error);
if (!new URLSearchParams(location.search).has("static")) {
  subscribe("/api/library/events", () => render().catch(console.error));
}
