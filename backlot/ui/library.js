import { el, fmtAgo, getJSON, subscribe, thumbURL } from "/ui/lib.js";
import { renderQuitButton, releaseLibraryRunner } from "/ui/board-runtime.js";
import {
  buildCreateProductVideoPrompt,
  copyCreatePrompt,
  formatServiceInfo,
  getReviewModeRoute,
  listReviewModes,
  readStoredReviewMode,
  shouldRemountOnboardingForm,
  writeStoredReviewMode,
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
let creatingProject = false;
let occupantBarMounted = false;
let releasingRunner = false;

function applyTheme(theme) {
  currentTheme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = currentTheme;
  localStorage.setItem(THEME_KEY, currentTheme);
}

function occupantFromHealth(health) {
  if (!health?.runner_alive) return { project_id: "", title: "" };
  const occ = health.runner_occupant || {};
  const id = String(occ.project_id || health.active_project_id || "").trim();
  if (!id) return { project_id: "", title: "" };
  return { project_id: id, title: String(occ.title || id) };
}

function mountOccupantBar() {
  const slot = document.getElementById("runner-occupant");
  if (!slot || occupantBarMounted) return;
  occupantBarMounted = true;
  const title = el("p", { class: "library-occupant-title" });
  const hint = el("p", { class: "library-occupant-hint" },
    "中断只停 runner，不结束项目，网页还在。要关掉网页请点「退出看板」。结束导出需要成片。");
  const feedback = el("span", { class: "library-occupant-feedback", role: "status" });
  const release = el("button", {
    type: "button",
    class: "library-occupant-release",
  }, "中断并做别的");
  release.addEventListener("click", async () => {
    if (releasingRunner) return;
    releasingRunner = true;
    release.disabled = true;
    feedback.textContent = "正在中断…";
    try {
      let result = await releaseLibraryRunner();
      if (!result.ok && result.status === 409) {
        const ok = window.confirm("正在生成。确认中断？项目会标为已中断，不会结束导出。");
        if (!ok) {
          feedback.textContent = "已取消。生成仍在继续。";
          return;
        }
        result = await releaseLibraryRunner({ interrupt: true });
      }
      feedback.textContent = result.friendly_zh;
      if (result.ok) {
        await render();
      }
    } catch {
      feedback.textContent = "中断失败。请留在本页重试。";
    } finally {
      releasingRunner = false;
      release.disabled = false;
    }
  });
  slot.append(
    title,
    hint,
    el("div", { class: "library-occupant-actions" }, release, feedback),
  );
}

function updateOccupantBar(health) {
  mountOccupantBar();
  const slot = document.getElementById("runner-occupant");
  if (!slot) return { project_id: "", title: "" };
  const occ = occupantFromHealth(health);
  slot.hidden = !occ.project_id;
  const title = slot.querySelector(".library-occupant-title");
  if (title) {
    title.textContent = occ.project_id ? `本机正在做：${occ.title}` : "";
  }
  const createBtn = onboarding.querySelector(".library-onboarding-copy");
  if (createBtn && !creatingProject) {
    createBtn.disabled = Boolean(occ.project_id);
    createBtn.title = occ.project_id
      ? "请先点「中断并做别的」，再创建新项目"
      : "填写主题后点开始创建";
  }
  return occ;
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
document.getElementById("liveBadge").before(renderQuitButton());
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

let selectedReviewMode = "normal";
let lastOnboardingHealth = { projects_dir: "未提供" };
let lastProjectCount = 0;

function currentReviewMode() {
  return readStoredReviewMode(window.sessionStorage) || selectedReviewMode;
}

function setReviewMode(mode) {
  selectedReviewMode = writeStoredReviewMode(window.sessionStorage, mode);
  const existing = onboarding.querySelector(".library-mode-route");
  if (existing) {
    existing.replaceWith(renderModeRoute(selectedReviewMode));
    const promptField = onboarding.querySelector(".library-onboarding-prompt");
    if (promptField) {
      promptField.value = buildCreateProductVideoPrompt(selectedReviewMode);
    }
    return;
  }
  renderOnboarding(lastOnboardingHealth, lastProjectCount);
}

function updateOnboardingServiceInfo(health, projectCount) {
  lastOnboardingHealth = health || lastOnboardingHealth;
  lastProjectCount = projectCount;
  const [serviceLine, countLine, rootLine] = formatServiceInfo({
    host: location.host,
    projectsDir: health?.projects_dir,
    projectCount,
  });
  const spans = onboarding.querySelectorAll(".library-service-list span");
  if (spans[0]) spans[0].textContent = serviceLine;
  if (spans[1]) spans[1].textContent = countLine;
  const rootP = onboarding.querySelector(".library-service-details p");
  if (rootP) rootP.textContent = rootLine;
}

function renderModeRoute(mode) {
  const route = getReviewModeRoute(mode);
  const modes = listReviewModes();
  const picker = el("div", {
    class: "library-mode-picker",
    role: "radiogroup",
    "aria-label": "评审方式",
  });
  for (const item of modes) {
    const selected = item.id === route.id;
    picker.append(el("button", {
      type: "button",
      class: "library-mode-btn" + (selected ? " selected" : ""),
      role: "radio",
      "aria-checked": selected ? "true" : "false",
      "data-mode": item.id,
      onclick: () => {
        if (item.id !== route.id) setReviewMode(item.id);
      },
    }, item.label_zh));
  }

  const steps = el("ol", { class: "library-mode-steps" });
  for (const step of route.confirm_steps) {
    steps.append(el("li", {
      class: "library-mode-step stop",
    },
      el("span", { class: "library-mode-step-index" }, String(step.index)),
      el("span", { class: "library-mode-step-name" }, step.label_zh),
      el("span", { class: "library-mode-step-action" }, step.action_zh),
    ));
  }

  return el("div", { class: "library-mode-route" },
    el("p", { class: "library-mode-kicker" }, "评审方式"),
    picker,
    el("p", { class: "library-mode-summary" }, route.summary_zh),
    steps,
    el("p", { class: "library-mode-note" },
      "只列出需要你确认的步骤。其余本机接着走。轻度/中度/重度在进入流程页后选择。"),
  );
}

function renderOnboarding(health, projectCount) {
  lastOnboardingHealth = health || lastOnboardingHealth;
  lastProjectCount = projectCount;
  selectedReviewMode = currentReviewMode();
  const prompt = buildCreateProductVideoPrompt(selectedReviewMode);
  const [serviceLine, countLine, rootLine] = formatServiceInfo({
    host: location.host,
    projectsDir: health?.projects_dir,
    projectCount,
  });
  const themeField = el("input", {
    class: "library-create-input",
    type: "text",
    required: "",
    placeholder: "商品主题（必填）",
    "aria-label": "商品主题",
  });
  const durationField = el("input", {
    class: "library-create-input",
    type: "number",
    min: "1",
    max: "75",
    placeholder: "时长秒数（可选，上限 75）",
    "aria-label": "时长秒数",
  });
  const assetField = el("input", {
    class: "library-create-input",
    type: "text",
    placeholder: "素材网址（可选）",
    "aria-label": "素材网址",
  });
  const fileInput = el("input", {
    class: "library-file-input",
    type: "file",
    multiple: "",
    accept: "image/*,video/*",
    "aria-label": "选择本地文件",
  });
  const folderInput = el("input", {
    class: "library-file-input",
    type: "file",
    multiple: "",
    webkitdirectory: "",
    directory: "",
    "aria-label": "选择本地文件夹",
  });
  const assetHint = el("span", { class: "library-asset-hint" }, "也可选本机文件或文件夹");
  const assetList = el("ul", { class: "library-asset-list", "aria-live": "polite" });
  const selectedFiles = () => [...fileInput.files, ...folderInput.files];
  const syncAssetHint = () => {
    const files = selectedFiles();
    assetList.replaceChildren();
    if (!files.length) {
      assetHint.textContent = "也可选本机文件或文件夹";
      return;
    }
    assetHint.textContent = `已选 ${files.length} 个本地文件，创建时导入项目；能否使用仍在「素材检查」确认。`;
    for (const file of files.slice(0, 12)) {
      assetList.append(el("li", {}, file.webkitRelativePath || file.name));
    }
    if (files.length > 12) {
      assetList.append(el("li", {}, `……还有 ${files.length - 12} 个`));
    }
  };
  fileInput.addEventListener("change", syncAssetHint);
  folderInput.addEventListener("change", syncAssetHint);
  const promptField = el("textarea", {
    class: "library-onboarding-prompt",
    readonly: "",
    rows: "3",
    "aria-label": "创建商品片请求",
  }, prompt);
  const feedback = el("p", {
    class: "library-onboarding-feedback",
    "aria-live": "polite",
  }, "填写主题后点开始创建，进入对应确认步骤。");
  const createButton = el("button", {
    class: "library-onboarding-copy",
    type: "button",
    onclick: async () => {
      const title = themeField.value.trim();
      if (!title) {
        feedback.textContent = "请先填写商品主题";
        themeField.focus();
        return;
      }
      const occ = occupantFromHealth(lastOnboardingHealth);
      if (occ.project_id) {
        feedback.textContent = `本机正在做「${occ.title}」。请先点「中断并做别的」。`;
        return;
      }
      creatingProject = true;
      feedback.textContent = "正在创建项目…";
      createButton.disabled = true;
      const files = selectedFiles();
      try {
        let response;
        if (files.length) {
          const form = new FormData();
          form.append("title", title);
          form.append("review_mode", currentReviewMode());
          if (durationField.value !== "") {
            form.append("duration_seconds", durationField.value);
          }
          if (assetField.value.trim()) {
            form.append("asset_location", assetField.value.trim());
          }
          for (const file of files) {
            form.append("files", file, file.webkitRelativePath || file.name);
          }
          response = await fetch("/api/library/create-project", {
            method: "POST",
            body: form,
          });
        } else {
          response = await fetch("/api/library/create-project", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              title,
              asset_location: assetField.value.trim(),
              duration_seconds: durationField.value === "" ? null : Number(durationField.value),
              review_mode: currentReviewMode(),
            }),
          });
        }
        const data = await response.json().catch(() => ({}));
        const detail = data.detail;
        const message = (detail && detail.friendly_zh)
          || (typeof detail === "string" ? detail : "")
          || data.friendly_zh
          || "创建失败";
        if (!response.ok) {
          feedback.textContent = message;
          return;
        }
        if (data.imported_count) {
          feedback.textContent = `已导入 ${data.imported_count} 个文件，正在进入流程页…`;
        }
        const suffix = new URLSearchParams(location.search).has("static") ? "?static=1" : "";
        window.location.href = `${data.board_path}${suffix}`;
      } catch {
        feedback.textContent = "创建失败。请回聊天，让 Agent 创建项目并打开看板。";
      } finally {
        creatingProject = false;
        createButton.disabled = false;
      }
    },
  }, "开始创建项目");
  const copyButton = el("button", {
    class: "library-copy-chat",
    type: "button",
    onclick: async () => {
      const nextPrompt = buildCreateProductVideoPrompt(currentReviewMode());
      promptField.value = nextPrompt;
      const result = await copyCreatePrompt({
        clipboard: navigator.clipboard,
        prompt: nextPrompt,
      });
      if (result.ok) {
        feedback.textContent = "已复制，请回聊天粘贴并发送。";
        return;
      }
      feedback.textContent = "无法自动复制，请选中下方文本并手动复制到聊天。";
      promptField.focus();
      promptField.select();
    },
  }, "复制到聊天");

  onboarding.replaceChildren(
    el("div", { class: "library-onboarding-head" },
      el("div", {},
        el("h2", { id: "onboardingTitle" }, "创建新商品片"),
        el("p", {},
          "选评审方式、填主题，点开始创建后进入流程页按步确认。复制到聊天是退路。"),
      ),
      createButton,
    ),
    renderModeRoute(selectedReviewMode),
    el("div", { class: "library-create-fields" },
      themeField,
      durationField,
      el("div", { class: "library-asset-row" },
        assetField,
        el("label", { class: "library-file-btn" }, "选择文件", fileInput),
        el("label", { class: "library-file-btn" }, "选择文件夹", folderInput),
      ),
      assetHint,
      assetList,
    ),
    el("div", { class: "library-create-actions" }, copyButton),
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

function card(p, occupant) {
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

  const completed = Boolean(p.completed || p.lifecycle_status === "completed");
  const stopLine = p.user_stage_zh
    ? (completed ? "已结束并导出" : `当前停点：${p.user_stage_zh}`)
    : (completed ? "已结束并导出" : `编号 ${p.project_id}`);
  const meta = el("div", { class: "lb-meta" },
    el("span", { class: "chip" }, p.pipeline_type || LABELS.unknown),
    p.review_mode_zh ? el("span", { class: "chip" }, p.review_mode_zh) : null,
    el("span", { class: "chip" }, stopLine),
    p.production_tier_zh ? el("span", { class: "chip" }, `制作档 ${p.production_tier_zh}`) : null,
    p.imported_asset_count ? el("span", { class: "chip" }, `${p.imported_asset_count} 个素材`) : null,
    p.scene_count ? el("span", { class: "chip" }, `${p.scene_count} ${LABELS.scenes}`) : null,
    p.render_count ? el("span", { class: "chip" }, `${p.render_count} ${LABELS.renders}`) : null,
    el("span", { class: "when" }, p.last_activity ? fmtAgo(p.last_activity) : "刚刚"),
  );

  const staticSuffix = new URLSearchParams(location.search).has("static") ? "?static=1" : "";
  const href = `/p/${p.project_id}${staticSuffix}`;
  const node = el("div", {
    class: `lib-card${p.live ? " live-card" : ""}`,
    style: "text-decoration:none;color:inherit;cursor:pointer",
  },
    poster,
    el("div", { class: "lib-body" },
      el("h3", {}, p.title || p.project_id),
      meta,
      p.stage_states.length ? miniRail(p.stage_states) : null,
    ),
  );
  if (completed && p.export_path) {
    const download = el("a", {
      class: "chip",
      href: `/media/${encodeURIComponent(p.project_id)}/${String(p.export_path).split("/").map(encodeURIComponent).join("/")}`,
      download: "final.mp4",
      style: "margin:8px 12px 12px;display:inline-block",
    }, "下载成片");
    download.addEventListener("click", (event) => event.stopPropagation());
    node.append(download);
  }
  if (completed) {
    node.addEventListener("click", () => {
      window.location.href = href;
    });
  } else {
    node.addEventListener("click", async () => {
      if (occupant.project_id && occupant.project_id !== p.project_id) {
        window.alert(
          `本机正在做「${occupant.title}」。请先点「中断并做别的」，再继续其它项目。`,
        );
        return;
      }
      const ok = window.confirm(
        `继续这个项目？\n编号：${p.project_id}\n${stopLine}\n将占用本机唯一 runner，从当前停点接着做，不会新建，也不会自动开烧。`,
      );
      if (!ok) return;
      try {
        const response = await fetch("/api/library/continue-project", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: p.project_id }),
        });
        const data = await response.json().catch(() => ({}));
        const detail = data.detail;
        const message = (detail && detail.friendly_zh)
          || data.friendly_zh
          || "无法继续这个项目";
        if (!response.ok) {
          window.alert(message);
          return;
        }
        window.location.href = `${data.board_path || href}`;
      } catch {
        window.alert("无法继续这个项目。请回聊天让 Agent 停 runner 后再试。");
      }
    });
  }
  return node;
}

async function render() {
  const [projects, health] = await Promise.all([
    getJSON("/api/projects"),
    getJSON("/api/health").catch(() => ({ projects_dir: "未提供" })),
  ]);
  document.getElementById("count").textContent = `${projects.length} ${LABELS.projects}`;
  lastOnboardingHealth = health || lastOnboardingHealth;
  const liveCount = projects.filter((p) => p.live).length;
  const badge = document.getElementById("liveBadge");
  badge.classList.toggle("idle", liveCount === 0);
  document.getElementById("liveText").textContent = liveCount
    ? `${liveCount} ${LABELS.LIVE}`
    : LABELS.IDLE;
  const occupant = updateOccupantBar(health);
  if (shouldRemountOnboardingForm({
    mounted: onboarding.hasChildNodes(),
    creating: creatingProject,
  })) {
    renderOnboarding(health, projects.length);
    updateOccupantBar(health);
  } else {
    updateOnboardingServiceInfo(health, projects.length);
  }
  grid.innerHTML = "";
  document.getElementById("empty").style.display = projects.length ? "none" : "block";
  for (const p of projects) grid.append(card(p, occupant));
}

render().catch(console.error);
if (!new URLSearchParams(location.search).has("static")) {
  subscribe("/api/library/events", () => render().catch(console.error));
}
