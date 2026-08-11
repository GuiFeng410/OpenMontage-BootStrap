// Backlot project board — renders BoardState and stays live via SSE.

import {
  STAGE_ICONS, el, fmtAgo, fmtClock, fmtDuration, fmtMoney, fmtMoneyCny,
  getJSON, mediaURL, subscribe, thumbURL, waveBars,
} from "/ui/lib.js";

const rawProjectPath = location.pathname.split("/p/")[1] || "";
const projectId = decodeURIComponent(rawProjectPath);
const encodedProjectId = encodeURIComponent(projectId);
const app = document.getElementById("app");
const modal = document.getElementById("modal");
const player = document.getElementById("player");

const THEME_KEY = "backlot.theme";
let currentTheme = localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
let state = null;
let selectedStage = null;   // stage drawer open for this stage name
let activeRender = 0;
let firstPaint = true;
let sseStatus = "connecting"; // connecting | live | disconnected
let replay = null;          // {t0, t1, t, playing} — replay mode when non-null

function applyTheme(theme) {
  currentTheme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = currentTheme;
  localStorage.setItem(THEME_KEY, currentTheme);
}

function renderThemeToggle() {
  const next = currentTheme === "light" ? "dark" : "light";
  return el("button", {
    class: "theme-toggle",
    type: "button",
    title: `Switch to ${next} theme`,
    "aria-label": `Switch to ${next} theme`,
    "aria-pressed": currentTheme === "light" ? "true" : "false",
    onclick: () => {
      applyTheme(next);
      render();
    },
  }, el("span", { class: "theme-toggle-icon", "aria-hidden": "true" }, currentTheme === "light" ? "☾" : "☀"));
}

applyTheme(currentTheme);

function isCommercial(s) {
  return s?.pipeline?.pipeline_type === "bootstrap-commercial";
}

function stageLabel(st) {
  return st.label_zh || st.name;
}

function stageSubZh(st) {
  if (st.status === "awaiting_human") return "等你聊天确认\n在聊天里回复继续";
  if (st.status === "in_progress" && st.stalled) {
    return `可能卡住 · ${st.stalled_minutes} 分钟无活动\n可询问 Agent 状态`;
  }
  if (st.status === "in_progress" && st.partial_progress) {
    const done = st.partial_progress.beats_done || st.partial_progress.completed_scene_ids;
    if (Array.isArray(done)) return `已完成 ${done.length} 段`;
    return "制作中";
  }
  if (st.status === "in_progress") return "制作中";
  if (st.status === "failed") return st.error ? String(st.error).slice(0, 60) : "失败";
  if (st.status === "completed") return st.gated && st.human_approved ? "已通过" : "已完成";
  if (st.timestamp) return fmtClock(st.timestamp);
  return "待开始";
}

function stageStatusZh(status) {
  return {
    pending: "待开始",
    in_progress: "制作中",
    awaiting_human: "等待确认",
    completed: "已完成",
    failed: "失败",
  }[status] || status;
}

// ---------------------------------------------------------------------------
// header slate
// ---------------------------------------------------------------------------

function renderSlate(s) {
  const board = s.storyboard;
  const commercial = isCommercial(s);
  const chips = commercial
    ? [
        el("span", { class: "chip" }, "商品片 · bootstrap-commercial"),
        s.commercial?.brief_summary?.duration_seconds
          ? el("span", { class: "chip" }, `${s.commercial.brief_summary.duration_seconds}s · ${s.commercial.brief_summary.review_mode_zh || ""}`)
          : null,
        s.commercial?.brief_summary?.style_label_zh
          ? el("span", { class: "chip" }, s.commercial.brief_summary.style_label_zh)
          : null,
      ]
    : [
        el("span", { class: "chip" }, `${s.pipeline.pipeline_type} pipeline`),
        board && board.total_duration_seconds
          ? el("span", { class: "chip" }, `${board.scenes.length} scenes · ${fmtDuration(board.total_duration_seconds)}`)
          : null,
        s.style_playbook ? el("span", { class: "chip" }, s.style_playbook) : null,
      ];

  const awaiting = s.stages.find((x) => x.status === "awaiting_human");
  const inProgress = s.stages.find((x) => x.status === "in_progress");
  const stalled = s.stages.find((x) => x.stalled);
  let liveEl;
  if (awaiting) {
    liveEl = el("span", { class: "live" },
      el("span", { class: "dot" }),
      commercial ? "◈ 需要你决定" : "◈ AWAITING YOU");
  } else if (stalled) {
    liveEl = el("span", { class: "live", style: "color:var(--red)" },
      el("span", { class: "dot", style: "background:var(--red);animation:none" }),
      commercial ? "⚠ 可能卡住" : "⚠ STALLED?");
  } else if (s.live || inProgress) {
    liveEl = el("span", { class: "live" }, el("span", { class: "dot" }), commercial ? "进行中" : "LIVE");
  } else {
    liveEl = el("span", { class: "live idle" }, el("span", { class: "dot" }),
      commercial
        ? `空闲${s.last_activity ? " · " + fmtAgo(s.last_activity) : ""}`
        : `IDLE${s.last_activity ? " · " + fmtAgo(s.last_activity).toUpperCase() : ""}`);
  }

  const cost = el("div", { class: "cost" });
  if (commercial && s.commercial?.cost_cny?.spent_cny != null) {
    const cc = s.commercial.cost_cny;
    const spent = cc.spent_cny;
    const budget = cc.budget_cny;
    const hasBudget = budget != null;
    const pct = hasBudget && budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;
    cost.append(el("div", { class: "nums" }, el("b", {}, fmtMoneyCny(spent)),
      hasBudget ? el("span", {}, ` / ${fmtMoneyCny(budget)}`) : ""));
    if (hasBudget) {
      cost.append(el("div", { class: "bar" }, el("i", {
        class: pct > 90 ? "crit" : pct > 75 ? "warn" : "", style: `width:${pct}%`,
      })));
    }
    cost.append(el("div", { class: "label" }, "本任务 API（非售价）"));
  } else if (s.cost) {
    const spent = s.cost.total_spent_usd ?? 0;
    const budget = spent + (s.cost.budget_remaining_usd ?? 0);
    const hasBudget = s.cost.budget_remaining_usd != null;
    const pct = hasBudget && budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;
    cost.append(el("div", { class: "nums" }, el("b", {}, fmtMoney(spent)),
      hasBudget ? el("span", {}, ` / ${fmtMoney(budget)}`) : ""));
    if (hasBudget) {
      cost.append(el("div", { class: "bar" }, el("i", {
        class: pct > 90 ? "crit" : pct > 75 ? "warn" : "", style: `width:${pct}%`,
      })));
    }
    cost.append(el("div", { class: "label" }, "generation spend"));
  }

  return el("header", { class: "slate" },
    el("div", { class: "clapper" }),
    el("div", {},
      el("a", { class: "wordmark", href: "/", style: "text-decoration:none" }, "Backlot"),
      el("h1", {},
        isCommercial(s)
          ? el("a", { href: "/", style: "color:inherit;text-decoration:none", title: "返回项目库切换其它项目" }, s.title)
          : s.title),
      isCommercial(s)
        ? el("div", { class: "project-switch-hint" },
            el("a", { href: "/", style: "color:var(--text-3);font-size:calc(10.5px * var(--fs-scale))" }, "← 所有项目"))
        : null,
    ),
    ...chips,
    el("div", { class: "spacer" }),
    renderThemeToggle(),
    liveEl,
    cost,
  );
}

// ---------------------------------------------------------------------------
// stage rail
// ---------------------------------------------------------------------------

function stageSub(st) {
  if (st.status === "awaiting_human") return "awaiting your approval\nreply in chat to continue";
  if (st.status === "in_progress" && st.stalled) {
    return `stalled? no activity for ${st.stalled_minutes}m\nask the agent for status`;
  }
  if (st.status === "in_progress" && st.partial_progress) {
    const done = st.partial_progress.completed_scene_ids;
    if (Array.isArray(done)) return `${done.length} scene${done.length === 1 ? "" : "s"} done`;
    return "in progress";
  }
  if (st.status === "in_progress") return "in progress";
  if (st.status === "failed") return st.error ? String(st.error).slice(0, 60) : "failed";
  if (st.timestamp) {
    const approved = st.gated && st.human_approved ? " · approved" : "";
    return fmtClock(st.timestamp) + approved;
  }
  return "";
}

function renderRail(s) {
  const rail = el("nav", { class: "rail" });
  const commercial = isCommercial(s);
  const focusName = commercial ? commercialFocusStage(s) : null;
  let pendingIndex = 1;
  for (const st of s.stages) {
    const cls = st.status === "completed" ? "done"
      : st.status === "in_progress" ? (st.stalled ? "active stalled" : "active")
      : st.status === "awaiting_human" ? "await"
      : st.status === "failed" ? "failed" : "";
    const icon = STAGE_ICONS[st.status] || String(pendingIndex);
    if (!STAGE_ICONS[st.status]) pendingIndex += 1;
    const sub = commercial ? stageSubZh(st) : stageSub(st);
    const isFocus = focusName && st.name === focusName;
    const node = el("div", {
      class: `stage ${cls}${selectedStage === st.name ? " selected" : ""}${isFocus ? " focus" : ""}${st.undeclared ? " undeclared" : ""}`,
      title: st.undeclared ? `"${st.name}" ran but isn't declared by this pipeline's manifest` : null,
      onclick: () => toggleDrawer(st.name),
    },
      el("span", { class: "line" }),
      el("span", { class: "node" }, icon),
      el("span", { class: "name" }, stageLabel(st)),
      el("span", { class: "sub", style: "white-space:pre-line" },
        st.undeclared ? `${sub}\n未列入管线`.trim() : sub),
    );
    rail.append(node);
  }
  return rail;
}

function toggleDrawer(stageName) {
  selectedStage = selectedStage === stageName ? null : stageName;
  render();
}

const STAGE_ARTIFACTS = {
  research: ["research_brief"],
  proposal: ["proposal_packet"],
  idea: ["brief"],
  script: ["script"],
  scene_plan: ["scene_plan"],
  assets: ["asset_manifest"],
  edit: ["edit_decisions"],
  compose: ["render_report", "final_review"],
  publish: ["publish_log"],
};

const COMMERCIAL_STAGE_ARTIFACTS = {
  brief_locked: ["brief", "video_plan"],
  assets_gate: ["brief", "asset_precheck", "asset_ledger", "segment_cards"],
  sample_review: ["sample_reel"],
  segment_build: ["review_overview", "batch01_review", "batch02_review"],
  draft_review: ["full_draft_pro"],
  delivery_signoff: ["cost_log"],
};

function renderDrawer(s) {
  if (!selectedStage) return null;
  const st = s.stages.find((x) => x.name === selectedStage);
  if (!st) return null;

  const body = el("div", { class: "drawer-body" });

  if (isCommercial(s)) {
    body.append(el("div", { class: "hint", style: "margin-bottom:12px;line-height:1.6" },
      "商品片阶段详情已在下方「方案摘要 / Beat 胶片条 / 成片预览」展示。",
      el("br"),
      "原始 JSON 见 ", el("code", {}, "artifacts/"), " 目录；审批请在聊天进行。"));
    const meta = st.metadata || {};
    if (meta.decision_prompt_zh) {
      body.append(el("div", { class: "commercial-decision-hint" },
        el("b", {}, "若本阶段等待你："),
        el("div", {}, meta.decision_prompt_zh)));
    }
    if (meta.approval_note) {
      body.append(el("div", { class: "hint" }, `已记录批准：${meta.approval_note}`));
    }
    return el("div", { class: "drawer commercial-drawer" },
      el("div", { class: "drawer-head" },
        el("h3", {}, `${stageLabel(st)} — ${stageStatusZh(st.status)}`),
        st.timestamp ? el("span", { class: "meta", style: "font-family:var(--mono);font-size:calc(10.5px * var(--fs-scale));color:var(--text-3)" }, st.timestamp) : null,
        el("span", { class: "close", onclick: () => toggleDrawer(st.name) }, "关闭 ✕"),
      ),
      body);
  }

  if (st.review) {
    body.append(el("div", { class: "findings", style: "margin-bottom:12px" },
      el("span", { class: `f ${st.review.critical ? "crit" : ""}` }, `${st.review.critical ?? 0} critical`),
      el("span", { class: `f ${st.review.suggestions ? "sugg" : ""}` }, `${st.review.suggestions ?? 0} suggestions`),
      el("span", { class: "f" }, `${st.review.nitpicks ?? 0} nitpicks`),
      typeof st.review.summary === "string" ? el("span", { style: "font-size:calc(11.5px * var(--fs-scale));color:var(--text-2);margin-left:8px" }, st.review.summary) : null,
    ));
  }

  const names = (isCommercial(s) ? COMMERCIAL_STAGE_ARTIFACTS : STAGE_ARTIFACTS)[st.name] || [];
  let shown = false;
  for (const name of names) {
    const artifact = s.artifacts[name];
    if (!artifact) continue;
    shown = true;
    body.append(
      el("div", { class: "d-cat", style: "font-family:var(--mono);font-size:calc(9.5px * var(--fs-scale));color:var(--text-3);letter-spacing:.1em;text-transform:uppercase;margin:6px 0 4px" }, name),
      el("pre", {}, JSON.stringify(artifact, null, 2)),
    );
  }
  if (!shown) {
    body.append(el("div", { class: "hint" },
      st.status === "pending" ? "This stage hasn't run yet." : "No canonical artifact found on disk for this stage."));
  }

  return el("div", { class: "drawer" },
    el("div", { class: "drawer-head" },
      el("h3", {}, `${stageLabel(st)} — ${st.status}`),
      st.gate_skipped ? el("span", { class: "gate-chip" }, "⚑ GATE SKIPPED") : null,
      st.versions > 1 ? el("span", { class: "ver-chip" }, `v${st.versions}`) : null,
      st.timestamp ? el("span", { class: "meta", style: "font-family:var(--mono);font-size:calc(10.5px * var(--fs-scale));color:var(--text-3)" }, st.timestamp) : null,
      el("span", { class: "close", onclick: () => toggleDrawer(st.name) }, "CLOSE ✕"),
    ),
    body,
  );
}

// ---------------------------------------------------------------------------
// script card
// ---------------------------------------------------------------------------

function scriptSections(script, limit) {
  const sections = script.sections || [];
  const shown = limit ? sections.slice(0, limit) : sections;
  const nodes = [];
  for (const sec of shown) {
    nodes.push(el("div", { class: "sp-slug" },
      `${(sec.id || "").toUpperCase()} — ${sec.label || "Section"} `,
      el("span", { class: "tc" }, `${fmtDuration(sec.start_seconds)} – ${fmtDuration(sec.end_seconds)}`)));
    if (sec.text) nodes.push(el("div", { class: "sp-action" }, sec.text));
    if (sec.speaker_directions) nodes.push(el("div", { class: "sp-paren" }, `(${sec.speaker_directions})`));
    const cues = sec.enhancement_cues || [];
    if (cues.length) {
      nodes.push(el("div", { style: "margin-left:42px" },
        cues.map((c) => el("span", { class: "sp-cue" }, `▸ ${c.type} · ${String(c.description || "").slice(0, 60)}`))));
    }
  }
  if (limit && sections.length > limit) {
    nodes.push(el("div", { class: "sp-fade" }, `… ${sections.length - limit} more sections`));
  }
  return nodes;
}

function renderScriptCard(s) {
  const script = s.artifacts.script;
  if (!script) return null;
  const scriptStage = s.stages.find((x) => x.name === "script");
  const approved = scriptStage && scriptStage.status === "completed";

  const card = el("div", { class: "script-card script-preview", title: "Click to expand full script", onclick: openScriptModal },
    approved ? el("span", { class: "script-approved" }, "APPROVED") : null,
    el("div", { class: "sp-title" }, script.title || s.title),
    el("div", { class: "sp-meta" },
      `script · ${fmtDuration(script.total_duration_seconds)} · ${(script.sections || []).length} sections`),
    ...scriptSections(script, 4),
    el("span", { class: "sp-expand" }, "⤢ EXPAND SCRIPT"),
  );
  return card;
}

function openScriptModal() {
  const script = state && state.artifacts.script;
  if (!script) return;
  modal.innerHTML = "";
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, "ESC · CLOSE"),
    el("div", { class: "modal-page" },
      el("div", { class: "script-card", style: "cursor:default" },
        el("div", { class: "sp-title" }, script.title || state.title),
        el("div", { class: "sp-meta" },
          `script · ${fmtDuration(script.total_duration_seconds)} · ${(script.sections || []).length} sections`),
        ...scriptSections(script, 0),
        el("div", { class: "sp-fade" }, "END"),
      )),
  );
  modal.classList.add("open");
}

function openNarrModal(card) {
  modal.innerHTML = "";
  const meta = [sceneLabel(card.id), card.section_label, fmtDuration(card.duration_seconds)]
    .filter(Boolean).join(" · ");
  modal.append(
    el("span", { class: "modal-close", onclick: closeModal }, "ESC · CLOSE"),
    el("div", { class: "modal-page" },
      el("div", { class: "script-card", style: "cursor:default" },
        el("div", { class: "sp-meta" }, meta),
        card.narration ? el("div", { class: "sp-action", style: "margin-left:0" }, card.narration) : null,
        card.shot_intent ? el("div", { class: "sp-paren", style: "margin-left:0" }, `Intent — ${card.shot_intent}`) : null,
        card.description ? el("div", { class: "sp-paren", style: "margin-left:0" }, card.description) : null,
      )),
  );
  modal.classList.add("open");
}

function closeModal() { modal.classList.remove("open"); }
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

// ---------------------------------------------------------------------------
// right rail: decisions, activity
// ---------------------------------------------------------------------------

function renderDecisions(s) {
  const log = s.artifacts.decision_log;
  const decisions = (log && log.decisions) || [];
  if (!decisions.length) return null;
  const body = el("div", { class: "panel-body" });
  // Collapse by category+subject: a decision that changed mid-run (e.g. voice
  // openai_onyx → chirp3) is superseded by the later entry — show the CURRENT
  // choice, not the first one recorded, and mark that it was revised.
  const current = new Map();
  decisions.forEach((d, i) => {
    const key = `${d.category || "decision"}::${d.subject || ""}`;
    const prev = current.get(key);
    current.set(key, { d, order: i, revised: prev ? prev.revised + 1 : 0 });
  });
  const shown = [...current.values()].sort((a, b) => b.order - a.order).slice(0, 8);
  for (const { d, revised } of shown) {
    const selLabel = (() => {
      // Prefer the human label of the selected option over its bare id.
      const opt = (d.options_considered || []).find((o) => (o.option_id ?? o.label) === d.selected);
      return (opt && opt.label) || d.selected || "";
    })();
    const alts = (d.options_considered || [])
      .filter((o) => (o.option_id ?? o.label) !== d.selected && (o.option_id || o.label));
    body.append(el("div", { class: "decision" },
      el("div", { class: "d-cat" }, `${d.category || "decision"}${d.confidence ? ` · ${d.confidence}` : ""}`,
        revised ? el("span", { class: "d-revised" }, " · revised") : null),
      el("div", { class: "d-pick" }, `${d.subject || ""} `, el("span", { class: "arrow" }, "→"), ` ${selLabel}`),
      d.reason ? el("div", { class: "d-why" }, d.reason) : null,
      alts.length ? el("div", { class: "d-alt" }, "also considered: ",
        alts.slice(0, 3).map((o, i) => [i ? " · " : "", el("s", {}, o.label || o.option_id)]).flat()) : null,
    ));
  }
  return el("div", { class: "panel" },
    el("div", { class: "panel-head" }, el("h2", {}, "Decisions"), el("span", { class: "meta" }, "decision_log.json")),
    body);
}

function renderActivity(s) {
  const events = s.events || [];
  if (!events.length) return null;
  const zh = isCommercial(s);
  const body = el("div", { class: "panel-body" });
  // A start is "running" only until a later finish/error for the same
  // tool+scene closes it — closed starts are dropped (the finish row tells
  // the story), unmatched starts render as live. Counted (not keyed-single)
  // so parallel runs of the same tool on the same scene stay visible.
  const open = new Map(); // key -> {count, ev}
  const rows = [];
  for (const ev of events) {
    const key = `${ev.tool}:${ev.scene_id || ""}`;
    if (ev.event === "start") {
      const slot = open.get(key) || { count: 0, ev };
      slot.count += 1;
      slot.ev = ev;
      open.set(key, slot);
    } else {
      const slot = open.get(key);
      if (slot) {
        slot.count -= 1;
        if (slot.count <= 0) open.delete(key);
      }
      rows.push(ev);
    }
  }
  for (const slot of open.values()) rows.push(slot.ev);
  rows.sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
  for (const ev of rows.slice(-10).reverse()) {
    let statusEl;
    if (ev.event === "finish") {
      statusEl = el("span", { class: `status ${ev.success === false ? "err" : "ok"}` },
        `${ev.success === false ? "✕" : "✓"}${ev.duration_s != null ? ` ${ev.duration_s.toFixed ? ev.duration_s.toFixed(1) : ev.duration_s}s` : ""}${ev.cost_usd ? ` ${fmtMoney(ev.cost_usd)}` : ""}`);
    } else if (ev.event === "error") {
      statusEl = el("span", { class: "status err" }, "✕");
    } else {
      statusEl = el("span", { class: "status run" }, zh ? "● 运行中" : "● running");
    }
    body.append(el("div", { class: "act-row" },
      el("span", { class: "t" }, fmtClock(ev.ts)),
      el("span", { class: "tool" }, ev.tool || ""),
      el("span", { class: "target" }, ev.scene_id || ""),
      statusEl,
    ));
  }
  return el("div", { class: "panel" },
    el("div", { class: "panel-head" }, el("h2", {}, zh ? "制作动态" : "Activity"), el("span", { class: "meta" }, "events.jsonl")),
    body);
}

// ---------------------------------------------------------------------------
// storyboard filmstrip
// ---------------------------------------------------------------------------

function sceneLabel(id) {
  // "sc4" → "SC 04", "scene-11" → "SC 11", anything else → uppercased id
  const m = String(id).match(/(\d+)\s*$/);
  if (m) return `SC ${m[1].padStart(2, "0")}`;
  return String(id).toUpperCase().slice(0, 10);
}

function sceneCard(s, card) {
  const dur = card.duration_seconds;
  const width = Math.max(132, Math.min(300, 70 + (dur || 3) * 26));
  const wrap = el("div", { class: "scene-card", style: `width:${width}px` });

  const slate = el("div", { class: "sc-slate" },
    el("span", { class: "num" }, sceneLabel(card.id)),
    card.takes.length > 1 ? el("span", { class: "take" }, `T${card.takes.length}`) : null,
    card.hero_moment ? el("span", { class: "hero" }, "★ HERO") : null,
    el("span", { class: "dur" }, fmtDuration(dur)),
  );
  wrap.append(slate);

  // visual slot
  let thumb;
  if (card.generating) {
    thumb = el("div", { class: "thumb generating" },
      el("div", { class: "shimmer" }),
      el("div", { class: "gen-label" },
        el("span", {}, "◉ GENERATING"),
        el("span", { class: "sub" }, card.generating_tool || "")));
  } else if (card.visual && card.visual.exists) {
    const v = card.visual;
    const badge = [v.model || v.source_tool, v.cost_usd != null ? fmtMoney(v.cost_usd) : null,
      v.quality_score != null ? `q ${v.quality_score}` : null].filter(Boolean).join(" · ");
    if (v.type === "video") {
      thumb = el("div", { class: "thumb approved" },
        el("video", { src: mediaURL(s.project_id, v.path), muted: "", preload: "metadata", playsinline: "" }),
        el("span", { class: "play" }, "▶"),
        badge ? el("span", { class: "badge" }, badge) : null);
      thumb.onclick = () => {
        const vid = thumb.querySelector("video");
        if (vid.paused) vid.play(); else vid.pause();
      };
    } else {
      const img = el("img", { src: thumbURL(s.project_id, v.path, 640), loading: "lazy", alt: "" });
      // A thumbnail that fails to load must never show a broken-image icon —
      // fall back to the shot spec in place (F: broken links).
      img.onerror = () => {
        const t = img.closest(".thumb");
        if (!t) return;
        t.className = "thumb spec";
        t.innerHTML = "";
        t.append(el("div", { class: "spec-in" },
          el("div", { class: "spec-desc" }, card.description || "asset unavailable"),
          el("div", { class: "spec-shot" }, [card.framing, card.movement].filter(Boolean).join(" · ").slice(0, 70))));
      };
      thumb = el("div", { class: "thumb approved" }, img,
        v.snapshot ? el("span", { class: "badge" }, "snapshot") : (badge ? el("span", { class: "badge" }, badge) : null));
    }
  } else if (card.type === "animation") {
    // Bespoke/atelier scene with no snapshot yet — name it as such rather
    // than "no asset yet" (the composition IS the asset).
    thumb = el("div", { class: "thumb spec bespoke" },
      el("div", { class: "spec-in" },
        el("span", { class: "bespoke-tag" }, "◆ BESPOKE"),
        el("div", { class: "spec-desc" }, card.description || ""),
        el("div", { class: "spec-shot" }, "hand-authored composition")));
  } else if (card.visual && !card.visual.exists) {
    thumb = el("div", { class: "thumb missing" },
      el("div", { class: "spec-in" },
        el("span", { class: "warn-ic" }, "⚑"),
        el("div", { class: "spec-desc" }, "asset in manifest, file missing"),
        el("div", { class: "spec-shot" }, card.visual.path || "")));
  } else if (card.type === "text_card") {
    thumb = el("div", { class: "thumb textcard" },
      el("div", { class: "tc-copy" }, (card.narration || card.description || "").slice(0, 48)));
  } else if (card.required_assets.length) {
    thumb = el("div", { class: "thumb missing" },
      el("div", { class: "spec-in" },
        el("span", { class: "warn-ic" }, "⚑"),
        el("div", { class: "spec-desc" }, "no asset yet"),
        el("div", { class: "spec-shot" }, (card.required_assets[0].description || "").slice(0, 60))));
  } else {
    thumb = el("div", { class: "thumb spec" },
      el("div", { class: "spec-in" },
        el("div", { class: "spec-desc" }, card.description || ""),
        el("div", { class: "spec-shot" }, [card.framing, card.movement].filter(Boolean).join(" · ").slice(0, 70))));
  }
  wrap.append(thumb);

  // shot language chips
  const sl = card.shot_language;
  if (sl) {
    wrap.append(el("div", { class: "shotchips", style: "display:flex;flex-wrap:wrap;gap:4px;padding:7px 2px 0" },
      [sl.shot_size, sl.camera_movement, sl.lens_mm ? `${sl.lens_mm}mm` : null, sl.lighting_key]
        .filter(Boolean)
        .map((t) => el("span", { style: "font-family:var(--mono);font-size:calc(8.5px * var(--fs-scale));letter-spacing:.04em;color:#62626c;border:1px solid #212129;border-radius:3px;padding:1px 5px" }, String(t).replaceAll("_", " ")))));
  }

  // takes drawer
  if (card.takes.length > 1) {
    const takes = el("div", { class: "takes" });
    card.takes.forEach((t, i) => {
      const isActive = card.visual && (
        t === card.visual
        || (t.path && t.path === card.visual.path)
        || (t.id && t.id === card.visual.id)
      );
      const tk = el("span", { class: `tk${isActive ? " active" : ""}`, title: `take ${i + 1}` });
      if (t.exists && t.type === "image") tk.append(el("img", { src: thumbURL(s.project_id, t.path, 320), loading: "lazy", alt: "" }));
      takes.append(tk);
    });
    takes.append(el("span", { class: "tk-label" }, `${card.takes.length} TAKES`));
    wrap.append(takes);
  }

  // narration + audio — clickable to read in full (F: narration text cut off)
  if (card.narration) {
    const long = card.narration.length > 90;
    wrap.append(el("div", {
      class: `narr${long ? " clip" : ""}`,
      title: "Click to read the full narration",
      onclick: () => openNarrModal(card),
    }, card.narration, long ? el("span", { class: "narr-more" }, "⤢") : null));
  } else if (card.shot_intent || card.description) {
    wrap.append(el("div", { class: "narr tc-note" }, (card.shot_intent || card.description || "").slice(0, 110)));
  }
  const narrAudio = card.audio.find((a) => a.exists && (a.type === "narration" || a.type === "audio"));
  if (narrAudio) {
    const wave = el("div", { class: "wave", style: "cursor:pointer", title: "Play narration" });
    waveBars(wave, card.id + narrAudio.path);
    wave.append(el("span", { class: "wv-time" }, narrAudio.duration_seconds ? fmtDuration(narrAudio.duration_seconds) : "♪"));
    wave.onclick = () => {
      player.src = mediaURL(s.project_id, narrAudio.path);
      player.play();
    };
    wrap.append(wave);
  }
  return wrap;
}

function renderStoryboard(s) {
  const board = s.storyboard;
  if (!board) return null;
  const strip = el("div", { class: "filmstrip" });
  for (const card of board.scenes) strip.append(sceneCard(s, card));
  return el("div", {},
    el("div", { class: "section-title" }, "Storyboard",
      el("span", { class: "meta" },
        `${board.scenes.length} scenes${board.total_duration_seconds ? ` · ${fmtDuration(board.total_duration_seconds)}` : ""} · card width ∝ duration`)),
    el("div", { class: "strip-outer" }, strip));
}

// ---------------------------------------------------------------------------
// renders + degraded media
// ---------------------------------------------------------------------------

function renderRenders(s) {
  const renders = s.media.renders;
  if (!renders.length) return null;
  if (activeRender >= renders.length) activeRender = 0;
  const current = renders[activeRender];
  // Full re-renders (every SSE refresh) must not reset an in-progress
  // watch: carry playback position/state over to the recreated element.
  const prev = document.querySelector(".render-hero video");
  const src = mediaURL(s.project_id, current.path);
  // preload="metadata" gives the element its intrinsic aspect ratio (and a
  // poster frame) before playback — without it a portrait 9:16 render sits
  // in a letterboxed 100%-wide black box that reads as landscape.
  const video = el("video", { src, controls: "", preload: "metadata" });
  // Click the frame to start playback (controls handle pause/scrub) — the
  // big player was inert to a click on the picture itself.
  video.addEventListener("click", () => { if (video.paused) video.play().catch(() => {}); });
  if (prev && prev.getAttribute("src") === src && (prev.currentTime > 0 || !prev.paused)) {
    const t = prev.currentTime;
    const wasPlaying = !prev.paused && !prev.ended;
    video.addEventListener("loadedmetadata", () => { video.currentTime = t; }, { once: true });
    video.setAttribute("preload", "metadata");
    if (wasPlaying) video.autoplay = true;
  }
  const versions = el("div", { class: "render-meta" },
    renders.map((r, i) => el("span", {
      class: `v${i === activeRender ? " active" : ""}`,
      onclick: () => { activeRender = i; render(); },
    }, `${r.path.split("/").pop()}${r.at_root ? " · root" : ""}`)),
    el("span", { style: "margin-left:auto" }, `${(current.size / 1048576).toFixed(1)} MB`),
  );
  return el("div", {},
    el("div", { class: "section-title" }, "Renders",
      el("span", { class: "meta" }, `${renders.length} version${renders.length === 1 ? "" : "s"}`)),
    el("div", { class: "render-hero" }, video),
    versions);
}

function renderFoundMedia(s) {
  // Degraded view: show discovered snapshots when there's no storyboard.
  if (s.storyboard || !s.media.snapshots.length) return null;
  const grid = el("div", { class: "found-grid" });
  for (const snap of s.media.snapshots.slice(0, 12)) {
    grid.append(el("div", { class: "thumb" },
      el("img", { src: thumbURL(s.project_id, snap.path, 640), loading: "lazy", alt: "" })));
  }
  return el("div", {},
    el("div", { class: "section-title" }, "What the watcher found",
      el("span", { class: "meta" }, "snapshots / verification frames")),
    grid);
}

function renderNoState(s) {
  if (s.has_pipeline_state) return null;
  return el("div", { class: "notice", style: "border-color:#2b2b33;background:var(--surface-2);color:var(--text-3)" },
    el("span", { style: "font-size:calc(15px * var(--fs-scale))" }, "◌"),
    el("span", {},
      el("b", { style: "color:var(--text-2)" }, "No pipeline state. "),
      "This project has no checkpoints — Backlot is showing what it found on disk. ",
      "Runs that follow the checkpoint protocol get the full board."));
}

function renderAwaitingNotice(s) {
  const awaiting = s.stages.find((x) => x.status === "awaiting_human") ||
    (isCommercial(s) ? s.stages.find((x) => x.status === "in_progress" && x.metadata?.needs_user_decision === true) : null);
  if (!awaiting) return null;
  if (isCommercial(s)) {
    const dec = s.commercial?.decision;
    const prompt = dec?.prompt_zh || "请在聊天中回复以继续。";
    const examples = dec?.examples_zh;
    const options = Array.isArray(dec?.options) ? dec.options : [];
    const optionList = options.length ? el("div", { class: "commercial-decision-options" },
      options.map((option) => el("div", { class: `commercial-decision-option${option.recommended ? " recommended" : ""}` },
        el("div", { class: "commercial-decision-option-head" },
          el("b", {}, option.label_zh || option.label || option.id || "选项"),
          option.recommended ? el("span", { class: "commercial-recommend-badge" }, "推荐") : null),
        option.description_zh ? el("div", { class: "commercial-decision-option-copy" }, option.description_zh) : null,
        option.impact_zh ? el("div", { class: "commercial-decision-option-impact" }, `影响：${option.impact_zh}`) : null))) : null;
    return el("div", { class: "notice commercial-notice" },
      el("span", { style: "font-size:calc(16px * var(--fs-scale))" }, "◈"),
      el("div", { class: "commercial-decision-body" },
        el("b", {}, `【需要你决定】${dec?.title_zh || dec?.stage_label_zh || stageLabel(awaiting)}`),
        dec?.context_zh ? el("div", { class: "commercial-decision-context" }, dec.context_zh) : null,
        el("div", { class: "commercial-decision-prompt", style: "white-space:pre-line" }, prompt),
        optionList,
        dec?.recommendation_zh ? el("div", { class: "commercial-decision-recommendation" }, `建议：${dec.recommendation_zh}`) : null,
        examples ? el("div", { class: "commercial-decision-example" }, `回复示例：${examples}`) : null,
        el("div", { class: "commercial-chat-only" }, "请回到 ", el("b", {}, "聊天"), " 回复；本页只展示信息，不提交审批。")));
  }
  return el("div", { class: "notice" },
    el("span", { style: "font-size:calc(16px * var(--fs-scale))" }, "◈"),
    el("span", {},
      el("b", {}, `The ${awaiting.name} stage is waiting for your review. `),
      "The agent is paused at this gate — reply ", el("b", {}, "in chat"), " to approve or request changes."));
}

function renderCommercialDecisions(s) {
  const rows = s.commercial?.decisions || [];
  if (!rows.length) return null;
  const body = el("div", { class: "panel-body" });
  for (const d of rows.slice().reverse().slice(0, 12)) {
    body.append(el("div", { class: "decision commercial-decision" },
      el("div", { class: "d-cat" }, d.category_zh || d.category || "决定"),
      el("div", { class: "d-pick" },
        `${d.subject || ""} `,
        el("span", { class: "arrow" }, "→"),
        ` ${d.selected_label_zh || d.selected || ""}`),
      d.user_response_text
        ? el("div", { class: "d-why" }, `你的回复：${d.user_response_text}`)
        : (d.reason ? el("div", { class: "d-why" }, d.reason) : null)));
  }
  return el("div", { class: "panel" },
    el("div", { class: "panel-head" },
      el("h2", {}, "已确认决定"),
      el("span", { class: "meta" }, "decision_log")),
    body);
}

function renderCommercialPlanArchive(s) {
  const archive = s.commercial?.plan_archive || {};
  const b = s.commercial?.brief_summary || {};
  const view = commercialContentView(s);
  // Always keep prior plan evidence visible after leaving 方案确认.
  if (view === "plan" && !archive.overall_prompt_zh && !archive.has_video_plan) return null;
  const flags = [
    archive.has_brief ? "brief✓" : "brief✗",
    archive.has_video_plan ? "video_plan✓" : "video_plan✗",
    archive.has_segment_cards ? `分段×${archive.segment_count || 0}` : "segment_cards✗",
  ].join(" · ");
  const body = el("div", { class: "panel-body commercial-summary" });
  body.append(el("div", { class: "kv-row" },
    el("span", { class: "kv-k" }, "封板状态"),
    el("span", { class: "kv-v" }, archive.sealed_zh || "—")));
  body.append(el("div", { class: "kv-row" },
    el("span", { class: "kv-k" }, "落盘检查"),
    el("span", { class: "kv-v" }, flags)));
  if (b.theme) {
    body.append(el("div", { class: "kv-row" },
      el("span", { class: "kv-k" }, "主题"),
      el("span", { class: "kv-v" }, b.theme)));
  }
  if (archive.overall_prompt_zh) {
    body.append(el("details", { class: "tech-details", open: view !== "plan" ? true : undefined },
      el("summary", {}, "整体步骤方案"),
      el("div", { class: "tech-body", style: "white-space:pre-line" }, archive.overall_prompt_zh)));
  } else if (view !== "plan") {
    body.append(el("div", { class: "hint" },
      "尚未写入整体方案文案（segment_cards.overall_prompt_zh）。点顶栏「方案确认」可查看已有文案规划；若仍空，说明阶段封板未写全。"));
  }
  return el("div", { class: "panel commercial-plan-archive" },
    el("div", { class: "panel-head" },
      el("h2", {}, "已确认方案档案"),
      el("span", { class: "meta" }, "跨阶段保留")),
    body);
}

function renderCommercialSummary(s) {
  const c = s.commercial;
  if (!c) return null;
  const b = c.brief_summary || {};
  const rows = [
    ["主题", b.theme],
    ["时长", b.duration_seconds ? `${b.duration_seconds}s` : null],
    ["制作档位", b.production_tier],
    ["视频渠道", b.video_channel],
    ["评审模式", b.review_mode_zh],
    ["画面构成", b.motion_mix_zh],
    ["实验预算", b.budget_cny != null ? fmtMoneyCny(b.budget_cny) : null],
    ["候选策略", b.candidate_mode_zh],
    ["风格", b.style_label_zh],
  ].filter(([, v]) => v);
  const body = el("div", { class: "panel-body commercial-summary" });
  for (const [label, value] of rows) {
    body.append(el("div", { class: "kv-row" },
      el("span", { class: "kv-k" }, label),
      el("span", { class: "kv-v" }, value)));
  }
  const tech = el("details", { class: "tech-details" },
    el("summary", {}, "技术详情"),
    el("div", { class: "tech-body" },
      b.video_model ? el("div", {}, `模型 · ${b.video_model}`) : null,
      c.cost_cny?.spent_usd != null ? el("div", {}, `美元账本 · ${fmtMoney(c.cost_cny.spent_usd)}`) : null,
      el("div", {}, `管线 · ${s.pipeline.pipeline_type}`)));
  body.append(tech);
  return el("div", { class: "panel" },
    el("div", { class: "panel-head" }, el("h2", {}, "方案摘要"), el("span", { class: "meta" }, "brief.json")),
    body);
}

function renderCommercialAssets(s) {
  const assets = s.commercial?.assets || [];
  if (!assets.length) return null;
  const body = el("div", { class: "panel-body asset-grid" });
  for (const img of assets) {
    const card = el("div", { class: `asset-card${img.exists ? "" : " missing"}` });
    if (img.exists) {
      card.append(el("img", {
        src: thumbURL(s.project_id, img.path, 320),
        loading: "lazy",
        alt: img.file,
      }));
    } else {
      card.append(el("div", { class: "asset-missing" }, "缺失"));
    }
    card.append(
      el("div", { class: "asset-meta" },
        el("b", {}, img.role_zh),
        el("span", {}, img.file),
        img.hero_only_motion ? el("span", { class: "asset-hint" }, "仅运镜，不作 I2V 锚点") : null));
    body.append(card);
  }
  return el("div", { class: "panel" },
    el("div", { class: "panel-head" }, el("h2", {}, "素材检查"), el("span", { class: "meta" }, "身份与角度")),
    body);
}

function renderCommercialAssetPrecheck(s) {
  const view = commercialContentView(s);
  if (view !== "plan" && view !== "assets") return null;
  const precheck = s.commercial?.asset_precheck || {};
  const summary = precheck.summary || {};
  const entries = Array.isArray(precheck.entries) ? precheck.entries : [];
  if (!summary.total_images && !summary.needs_user_attention && !entries.length) return null;

  const rows = [
    ["已扫描图片", summary.total_images != null ? `${summary.total_images} 张` : null],
    ["低分辨率", summary.low_resolution_count ? `${summary.low_resolution_count} 张` : "无"],
    ["重复文件", summary.duplicate_group_count ? `${summary.duplicate_group_count} 组` : "无"],
    ["识图辅助", summary.vision_enriched ? `已启用${summary.vision_model ? ` · ${summary.vision_model}` : ""}` : null],
  ].filter(([, value]) => value != null);
  const body = el("div", { class: "panel-body commercial-summary" });
  for (const [label, value] of rows) {
    body.append(el("div", { class: "kv-row" },
      el("span", { class: "kv-k" }, label),
      el("span", { class: "kv-v" }, value)));
  }
  if (summary.needs_user_attention || entries.some((e) => e.vision_description_zh)) {
    body.append(el("details", { class: "tech-details", open: view === "assets" ? true : undefined },
      el("summary", {}, view === "assets" ? "素材清单与识图摘要" : "查看需确认的素材"),
      el("div", { class: "tech-body" },
        entries.map((entry) => {
          const hints = [
            entry.suggested_class ? `建议：${entry.suggested_class}` : "建议：待人工归类",
            entry.vision_description_zh ? `识图：${entry.vision_description_zh}` : "",
            ...(entry.issues || []),
            entry.duplicate_of ? `重复于 ${entry.duplicate_of}` : "",
          ].filter(Boolean);
          return el("div", {}, `${entry.file} · ${hints.join("；")}`);
        }))));
  }
  return el("div", { class: "panel commercial-precheck-panel" },
    el("div", { class: "panel-head" },
      el("h2", {}, view === "assets" ? "素材检查 · 预检" : "素材预检"),
      el("span", { class: "meta" }, view === "assets" ? "用户素材安排" : "方案确认前置")),
    body);
}

function renderCommercialCostPanel(s) {
  const cc = s.commercial?.cost_cny;
  if (!cc || cc.spent_cny == null) return null;
  const body = el("div", { class: "panel-body" },
    el("div", { class: "cost-line" }, "合计 API：", el("b", {}, fmtMoneyCny(cc.spent_cny))),
    cc.budget_cny != null ? el("div", { class: "cost-line" },
      "实验预算：", fmtMoneyCny(cc.budget_cny),
      cc.remaining_cny != null ? ` · 剩余约 ${fmtMoneyCny(cc.remaining_cny)}` : "") : null,
    el("div", { class: "cost-note" }, "人民币为主；美元见技术详情"));
  return el("div", { class: "panel" },
    el("div", { class: "panel-head" }, el("h2", {}, "费用卡"), el("span", { class: "meta" }, "cost_log")),
    body);
}

function formatCommercialMethod(beat) {
  const raw = beat.method || "";
  if (/Remotion|图片缩放|图片转场|静图/.test(raw)) {
    if (/转场/.test(raw)) return "图片转场-非AI生成（Remotion）";
    return "图片缩放-非AI生成（Remotion）";
  }
  if (/Agnes|视频生成/.test(raw)) {
    if (/佩戴/.test(raw)) return "视频生成-AI（Agnes）·佩戴微动";
    if (/双候选/.test(raw)) return "视频生成-AI（Agnes）·双候选";
    return "视频生成-AI（Agnes）";
  }
  return raw || "—";
}

function beatOrdinalZh(beatId, index) {
  const nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
  const n = nums[index] || String(index + 1);
  return `第${n}段（${beatId || `beat_${index + 1}`}）`;
}

/** Stage → evidence view. Full image+video mix only at 终稿/交付. */
const STAGE_CONTENT_VIEW = {
  brief_locked: "plan",
  assets_gate: "assets",
  sample_review: "sample",
  segment_build: "segment",
  draft_review: "draft",
  final_compose: "compose",
  delivery_signoff: "delivery",
};

const CONTENT_VIEW_LABEL = {
  plan: "方案确认 · 仅文案规划",
  assets: "素材检查 · 用户素材与扩展安排",
  sample: "试片确认 · 仅入片视频",
  segment: "分段制作 · 入片视频",
  draft: "初稿审查 · 问题与修改清单",
  compose: "合成终稿 · 技术检查",
  delivery: "交付确认 · 终稿与签收",
};

function commercialFocusStage(s) {
  if (selectedStage) return selectedStage;
  const awaiting = s.stages.find((x) => x.status === "awaiting_human");
  if (awaiting) return awaiting.name;
  const active = s.stages.find((x) => x.status === "in_progress");
  if (active) return active.name;
  // 全完成：默认不揉合集，落到分段制作视图；点终稿/交付才看合集
  const known = s.stages.filter((x) => !x.undeclared);
  if (known.length && known.every((x) => x.status === "completed")) {
    return "segment_build";
  }
  for (const name of Object.keys(STAGE_CONTENT_VIEW)) {
    const st = s.stages.find((x) => x.name === name);
    if (st && ["pending", "in_progress", "failed"].includes(st.status)) return name;
  }
  return "brief_locked";
}

function commercialContentView(s) {
  const stage = commercialFocusStage(s);
  return STAGE_CONTENT_VIEW[stage] || "plan";
}

function renderCommercialMediaStack(s, beat, view) {
  const stack = el("div", { class: "beat-media-stack" });
  const ledger = beat.ledger || [];
  const images = ledger.filter((x) => x.kind === "image" && x.path && x.exists === true);
  const videos = ledger.filter((x) => x.kind === "video" && x.path && x.exists === true);
  const selectedVideo = videos.find((v) => v.selected) || videos[0];
  const missingVideo = ledger.find((x) =>
    x.kind === "video" && x.path && x.exists === false)?.path || beat.asset_missing_path;

  if (view === "plan") {
    return null; // 方案确认：不放媒体
  }

  if (view === "assets") {
    if (!images.length) {
      stack.append(el("div", { class: "beat-media empty" }, "用户素材确认后将显示图片"));
    } else {
      for (const img of images) {
        const isExpand = /扩展|i2i|AI/i.test(`${img.label_zh || ""}${img.note_zh || ""}`);
        stack.append(el("div", { class: `beat-media image${img.selected ? " selected" : ""}${isExpand ? " expand" : ""}` },
          el("img", {
            src: thumbURL(s.project_id, img.path, 480),
            loading: "lazy",
            alt: img.file || "",
          }),
          el("span", { class: "media-cap" }, img.label_zh || (isExpand ? "AI扩展" : "用户素材"))));
      }
    }
    const pendingExpand = (beat.need_detail_zh || beat.gap_status === "不足");
    if (pendingExpand) {
      stack.append(el("div", { class: "beat-media empty expand-slot" },
        beat.need_detail_zh || "AI 扩展占位（待补图/确认）"));
    }
    return stack;
  }

  // sample / segment / draft：只准入片视频，不出图片大图、不出候选2大预览
  if (view === "sample" || view === "segment" || view === "draft") {
    const vid = selectedVideo || (beat.asset_path
      ? { path: beat.asset_path, label_zh: "入片视频", selected: true }
      : null);
    if (!vid) {
      stack.append(el("div", { class: "beat-media empty" },
        missingVideo ? `媒体文件不存在：${missingVideo}` : "试片/分段后将显示入片视频"));
      return stack;
    }
    const box = el("div", { class: "beat-media video selected" },
      el("video", {
        src: mediaURL(s.project_id, vid.path),
        muted: "", preload: "metadata", playsinline: "",
      }),
      el("span", { class: "play" }, "▶"),
      el("span", { class: "media-cap" }, vid.label_zh || "入片视频"));
    box.onclick = () => {
      const node = box.querySelector("video");
      if (!node) return;
      if (node.paused) node.play(); else node.pause();
    };
    stack.append(box);
    if ((view === "segment" || view === "draft") && beat.reference_path) {
      stack.append(el("details", { class: "beat-reference" },
        el("summary", {}, "查看参考素材"),
        el("img", {
          src: thumbURL(s.project_id, beat.reference_path, 240),
          loading: "lazy",
          alt: beat.ref || "参考素材",
        }),
        el("span", { class: "media-cap" }, beat.ref || "参考素材")));
    }
    return stack;
  }

  // draft / compose / delivery：保留已选素材与入片视频作为审计关联。
  for (const img of images.filter((i) => i.selected || images.length === 1)) {
    stack.append(el("div", { class: `beat-media image${img.selected ? " selected" : ""}` },
      el("img", {
        src: thumbURL(s.project_id, img.path, 480),
        loading: "lazy",
        alt: img.file || "",
      }),
      el("span", { class: "media-cap" }, img.label_zh || "图片")));
  }
  const vid = selectedVideo || (beat.asset_path
    ? { path: beat.asset_path, label_zh: "入片视频", selected: true }
    : null);
  if (vid) {
    const box = el("div", { class: "beat-media video selected" },
      el("video", {
        src: mediaURL(s.project_id, vid.path),
        muted: "", preload: "metadata", playsinline: "",
      }),
      el("span", { class: "play" }, "▶"),
      el("span", { class: "media-cap" }, vid.label_zh || "入片视频"));
    box.onclick = () => {
      const node = box.querySelector("video");
      if (!node) return;
      if (node.paused) node.play(); else node.pause();
    };
    stack.append(box);
  }
  if (!stack.childNodes.length) {
    stack.append(el("div", { class: "beat-media empty" }, "暂无成片素材"));
  }
  return stack;
}

function renderCommercialLedgerStrip(beat, view) {
  const ledger = beat.ledger || [];
  if (!ledger.length) return null;
  let items = ledger;
  if (view === "plan") return null;
  if (view === "assets") items = ledger.filter((x) => x.kind === "image");
  if (view === "sample" || view === "segment") {
    items = ledger.filter((x) => x.kind === "video" && x.selected);
  }
  // full: 全部标注
  if (!items.length) return null;
  const strip = el("div", { class: "asset-label-strip" });
  for (const item of items) {
    const cls = `asset-label${item.selected ? " selected" : ""}${item.exists === false ? " missing" : ""}`;
    const title = [item.note_zh, item.path].filter(Boolean).join(" · ");
    strip.append(el("span", { class: cls, title: title || item.file },
      `${item.label_zh || item.label}${item.selected ? " · 已选" : ""}`,
      item.file ? el("i", {}, ` · ${item.file}`) : null));
  }
  return strip;
}

function renderCommercialBeatCard(s, beat, index = 0) {
  const view = commercialContentView(s);
  const wrap = el("div", {
    class: `commercial-beat-card mode-${view}`,
    "data-beat": beat.beat || "",
  });

  wrap.append(el("div", { class: "cbc-head" },
    el("div", { class: "cbc-title" }, beatOrdinalZh(beat.beat, index)),
    el("span", {
      class: `status-chip ${(beat.status === "可以" || beat.gap_status === "足够") ? "ok" : beat.gap_status === "不足" ? "warn" : ""}`,
    }, view === "assets" ? (beat.gap_status || beat.status || "") : (beat.status || "—"))));

  wrap.append(el("div", { class: "cbc-time" }, `时间段：${beat.time || "—"}`));

  const media = renderCommercialMediaStack(s, beat, view);
  if (media) wrap.append(media);

  const body = el("div", { class: "cbc-body" });
  if (view === "plan") {
    body.append(
      el("div", { class: "beat-field" }, el("b", {}, "文案规划"), el("div", {}, beat.copy_plan_zh || "—")),
      el("div", { class: "beat-field" }, el("b", {}, "镜头规划"), el("div", {}, beat.shot_plan_zh || "—")),
      el("div", { class: "beat-field" }, el("b", {}, "素材初步规划"), el("div", {}, beat.asset_plan_zh || "—")));
  } else if (view === "assets") {
    body.append(
      el("div", { class: "beat-field" }, el("b", {}, "素材安排"), el("div", {}, beat.asset_plan_zh || "—")),
      el("div", { class: "beat-field" }, el("b", {}, "所需素材"), el("div", {}, beat.need_count != null ? `${beat.need_count} 张` : "—")),
      el("div", { class: "beat-field" }, el("b", {}, "现有"), el("div", {}, beat.have_count != null ? `${beat.have_count} 张` : "—")),
      el("div", { class: "beat-field" }, el("b", {}, "状况"), el("div", {}, beat.gap_status || "—")),
      beat.need_detail_zh
        ? el("div", { class: "beat-field warn-text" }, el("b", {}, "AI扩展/缺口"), el("div", {}, beat.need_detail_zh))
        : null);
    if (beat.copy_plan_zh || beat.shot_plan_zh) {
      body.append(el("details", { class: "beat-plan-fold" },
        el("summary", {}, "回顾：该段文案/镜头（方案确认）"),
        beat.copy_plan_zh ? el("div", {}, beat.copy_plan_zh) : null,
        beat.shot_plan_zh ? el("div", {}, beat.shot_plan_zh) : null));
    }
  } else {
    body.append(
      el("div", { class: "cbc-method" }, formatCommercialMethod(beat)),
      beat.angle_use ? el("div", { class: "cbc-sub" }, beat.angle_use) : null,
      beat.ref ? el("div", { class: "cbc-sub" }, `参考 · ${beat.ref}`) : null);
    if (["compose", "delivery"].includes(view) && (beat.copy_plan_zh || beat.shot_plan_zh)) {
      body.append(el("details", { class: "beat-plan-fold" },
        el("summary", {}, "规划摘要"),
        beat.copy_plan_zh ? el("div", {}, beat.copy_plan_zh) : null,
        beat.shot_plan_zh ? el("div", {}, beat.shot_plan_zh) : null));
    }
  }
  wrap.append(body);

  const strip = renderCommercialLedgerStrip(beat, view);
  if (strip) wrap.append(strip);
  return wrap;
}

function renderCommercialTimeline(s) {
  const tl = s.commercial?.timeline;
  if (!tl || !tl.duration_seconds) return null;
  const dur = Number(tl.duration_seconds) || 0;
  if (dur <= 0) return null;
  const track = el("div", { class: "tl-track" });
  const endLabel = Number.isInteger(dur) ? `${dur}s` : `${dur.toFixed(1)}s`;

  const bySec = new Map();
  const put = (m) => {
    const sec = Number(m.seconds);
    if (!Number.isFinite(sec)) return;
    const prev = bySec.get(sec);
    if (!prev) {
      bySec.set(sec, { ...m, seconds: sec });
      return;
    }
    if (m.kind === "batch") {
      bySec.set(sec, { ...m, seconds: sec, beat: prev.beat || m.beat });
    } else if (prev.kind !== "batch" && m.kind === "end") {
      bySec.set(sec, { ...m, seconds: sec });
    }
  };
  put({ seconds: 0, kind: "end", label: "0s" });
  for (const m of tl.beat_marks || []) put(m);
  for (const m of tl.batch_marks || []) put(m);
  put({ seconds: dur, kind: "end", label: endLabel });

  const marks = [...bySec.values()].sort((a, b) => a.seconds - b.seconds);
  for (const m of marks) {
    const pct = Math.max(0, Math.min(100, (m.seconds / dur) * 100));
    const isBatch = m.kind === "batch";
    const mark = el("button", {
      type: "button",
      class: `tl-mark ${m.kind}${isBatch ? " bold" : ""}`,
      style: `left:${pct}%`,
      title: isBatch ? `批次界 ${m.label}` : `切分 ${m.label}`,
      onclick: () => {
        if (m.beat) {
          const card = document.querySelector(`.commercial-beat-card[data-beat="${m.beat}"]`);
          if (card) card.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
        }
      },
    }, el("span", { class: "tl-tick" }), el("span", { class: "tl-label" }, m.label));
    track.append(mark);
  }
  return el("div", { class: "commercial-timeline" },
    el("div", { class: "tl-legend" },
      el("span", { class: "lg-beat" }, "细刻度 · beat 界"),
      s.commercial?.review_mode === "pro" ? el("span", { class: "lg-batch" }, "粗刻度 · 批次界") : null),
    track);
}

function renderCommercialBeats(s) {
  const beats = s.commercial?.beats || [];
  if (!beats.length) return null;
  const view = commercialContentView(s);
  if (view === "compose" || view === "delivery") return null;
  const focus = commercialFocusStage(s);
  const focusLabel = (s.stages.find((x) => x.name === focus) || {}).label_zh || focus;
  const grid = el("div", { class: "beat-card-grid" });
  beats.forEach((beat, i) => grid.append(renderCommercialBeatCard(s, beat, i)));
  const batches = s.commercial?.batches || [];
  const batchMeta = el("span", { class: "meta" },
    ` · ${CONTENT_VIEW_LABEL[view] || view}`,
    selectedStage ? ` · 已选：${focusLabel}` : "",
    batches.length && s.commercial?.review_mode === "pro" ? ` · ${batches.length} 批` : "");
  const timeline = renderCommercialTimeline(s);
  const hint = el("div", { class: "content-view-hint" },
    "证据按阶段递进：方案确认看文案 → 素材检查看用户图与扩展安排 → 试片/分段看入片视频 → 初稿看问题与修改 → 终稿看技术检查 → 交付看签收。",
    el("b", {}, " 点击顶栏阶段"), " 可切换该阶段视图。");
  return el("div", { class: "commercial-film-block" },
    el("div", { class: "section-title" }, "Beat 胶片条 / 时间线", batchMeta),
    hint,
    timeline,
    grid);
}

function renderCommercialPlayers(s) {
  const view = commercialContentView(s);
  // 试片确认起才显示下方成片播放器；方案/素材阶段不出现
  if (view === "plan" || view === "assets") return null;
  const evidence = s.commercial?.stage_evidence || {};
  const stagePlayer = {
    sample: evidence.sample?.path && evidence.sample?.exists === true
      ? { label: "试片", path: evidence.sample.path } : null,
    draft: evidence.draft?.path && evidence.draft?.exists === true
      ? { label: "完整初稿", path: evidence.draft.path } : null,
    compose: evidence.compose?.path && evidence.compose?.exists === true
      ? { label: "终稿候选", path: evidence.compose.path } : null,
    delivery: evidence.delivery?.path && evidence.delivery?.exists === true
      ? { label: "终稿", path: evidence.delivery.path } : null,
  }[view];
  if ((view === "sample" || view === "segment") && !stagePlayer) return null;
  const players = stagePlayer
    ? [stagePlayer]
    : (s.commercial?.players || []).filter((player) =>
      !["试片", "完整初稿", "终稿", "终稿候选"].includes(player.label));
  if (!players.length) return null;
  const tabs = el("div", { class: "render-meta" });
  players.forEach((p, i) => {
    tabs.append(el("span", {
      class: `v${i === activeRender ? " active" : ""}`,
      onclick: () => { activeRender = i; render(); },
    }, p.label));
  });
  if (activeRender >= players.length) activeRender = 0;
  const current = players[activeRender];
  const video = el("video", {
    src: mediaURL(s.project_id, current.path),
    controls: "", preload: "metadata",
  });
  return el("div", {},
    el("div", { class: "section-title" }, "成片预览",
      el("span", { class: "meta" }, current.path.split("/").pop())),
    el("div", { class: "render-hero" }, video),
    tabs);
}

function renderCommercialStageEvidence(s) {
  const view = commercialContentView(s);
  const evidence = s.commercial?.stage_evidence || {};
  if (view === "sample") {
    const sample = evidence.sample || {};
    const body = el("div", { class: "panel-body commercial-summary" },
      el("div", { class: "kv-row" }, el("span", { class: "kv-k" }, "试片状态"),
        el("span", { class: "kv-v" }, sample.status || "待生成")),
      el("div", { class: "kv-row" }, el("span", { class: "kv-k" }, "时长"),
        el("span", { class: "kv-v" }, sample.duration_seconds != null ? `${sample.duration_seconds}s` : "待探测")),
      sample.user_confirmation_text
        ? el("div", { class: "commercial-evidence-list" }, el("b", {}, "用户确认"), el("div", {}, sample.user_confirmation_text))
        : el("div", { class: "hint" }, "尚未记录用户对试片的确认。"),
      sample.exists === false && sample.missing_path
        ? el("div", { class: "hint warn-text" }, `媒体文件不存在：${sample.missing_path}`)
        : null);
    return el("div", { class: "panel commercial-stage-evidence" },
      el("div", { class: "panel-head" }, el("h2", {}, "试片确认"), el("span", { class: "meta" }, "sample_reel")),
      body);
  }
  if (view === "draft") {
    const draft = evidence.draft || {};
    const issues = draft.issue_segments || [];
    const modifications = draft.modification_list || [];
    const body = el("div", { class: "panel-body" },
      issues.length
        ? el("div", { class: "commercial-evidence-list" },
          el("b", {}, "问题片段"),
          issues.map((item) => el("div", {}, `${item.beat || "片段"} · ${item.time || "时间待补"} · ${item.issue_zh || item.issue || "待说明"}`)))
        : el("div", { class: "hint" }, "尚未写入问题片段；初稿通过前应记录审查结论。"),
      modifications.length
        ? el("div", { class: "commercial-evidence-list" },
          el("b", {}, "修改清单"),
          modifications.map((item, index) => el("div", {}, `${index + 1}. ${item}`)))
        : el("div", { class: "hint" }, "尚未写入修改清单。"));
    return el("div", { class: "panel commercial-stage-evidence" },
      el("div", { class: "panel-head" }, el("h2", {}, "初稿审查"), el("span", { class: "meta" }, "full_draft_pro")),
      body);
  }
  if (view === "compose") {
    const compose = evidence.compose || {};
    const probe = compose.technical_probe || {};
    const rows = [
      ["审查结论", compose.status],
      ["时长", probe.duration_seconds != null ? `${probe.duration_seconds}s` : null],
      ["分辨率", probe.resolution],
      ["帧率", probe.fps != null ? `${probe.fps} fps` : null],
      ["音频", probe.has_audio == null ? null : (probe.has_audio ? "存在" : "缺失")],
    ].filter(([, value]) => value != null);
    const body = el("div", { class: "panel-body commercial-summary" });
    rows.forEach(([label, value]) => body.append(el("div", { class: "kv-row" },
      el("span", { class: "kv-k" }, label), el("span", { class: "kv-v" }, String(value)))));
    const issues = [...(probe.issues || []), ...(compose.issues_found || [])];
    body.append(issues.length
      ? el("div", { class: "commercial-evidence-list" }, el("b", {}, "技术问题"), issues.map((issue) => el("div", {}, issue)))
      : el("div", { class: "hint" }, "技术检查未发现问题。"));
    return el("div", { class: "panel commercial-stage-evidence" },
      el("div", { class: "panel-head" }, el("h2", {}, "合成终稿 · 技术检查"), el("span", { class: "meta" }, "final_review")),
      body);
  }
  if (view === "delivery") {
    const delivery = evidence.delivery || {};
    const body = el("div", { class: "panel-body commercial-summary" },
      el("div", { class: "kv-row" }, el("span", { class: "kv-k" }, "质量结论"),
        el("span", { class: "kv-v" }, delivery.quality_status || "待技术检查")),
      el("div", { class: "kv-row" }, el("span", { class: "kv-k" }, "签收状态"),
        el("span", { class: "kv-v" }, delivery.decision_label_zh || delivery.decision || "等待聊天确认")),
      delivery.decision_response_zh
        ? el("div", { class: "commercial-evidence-list" }, el("b", {}, "用户回复"), el("div", {}, delivery.decision_response_zh))
        : null);
    return el("div", { class: "panel commercial-stage-evidence" },
      el("div", { class: "panel-head" }, el("h2", {}, "交付确认"), el("span", { class: "meta" }, "decision_log")),
      body);
  }
  return null;
}

function renderCommercialLegacyNotice(s) {
  const records = s.commercial?.legacy_checkpoints || [];
  if (!records.length) return null;
  return el("div", { class: "notice commercial-legacy-notice" },
    el("span", {}, "⚠"),
    el("span", {}, "发现历史 checkpoint：", el("b", {}, records.map((item) => item.stage).join("、")),
      "。它们不属于商品片七阶段，已从主进度栏隔离，且没有改写项目磁盘。"));
}

function renderSseBanner(s) {
  if (!isCommercial(s)) return null;
  if (sseStatus === "live") return null;
  const text = sseStatus === "disconnected"
    ? "看板实时连接已断开，内容可能未刷新。请手动刷新页面，或等待自动重连。"
    : "正在连接看板实时更新…";
  return el("div", { class: `notice sse-banner ${sseStatus}` },
    el("span", {}, "⟳"),
    el("span", {}, text),
    el("button", {
      class: "sse-refresh-btn",
      onclick: () => refresh().catch(console.error),
    }, "刷新"));
}

function renderCommercialBoard(s) {
  const aside = el("aside", { class: "commercial-aside" });
  const summary = renderCommercialSummary(s);
  const planArchive = renderCommercialPlanArchive(s);
  const decisions = renderCommercialDecisions(s);
  const costPanel = renderCommercialCostPanel(s);
  const activity = renderActivity(s);
  if (summary) aside.append(summary);
  if (planArchive) aside.append(planArchive);
  if (decisions) aside.append(decisions);
  if (costPanel) aside.append(costPanel);
  if (activity) aside.append(activity);

  const main = el("div", { class: "main-col" });
  const sseBanner = renderSseBanner(s);
  if (sseBanner) main.append(sseBanner);
  const legacyNotice = renderCommercialLegacyNotice(s);
  if (legacyNotice) main.append(legacyNotice);
  const allDone = s.stages.filter((x) => !x.undeclared).every((x) => x.status === "completed");
  const focus = commercialFocusStage(s);
  const focusLabel = (s.stages.find((x) => x.name === focus) || {}).label_zh || focus;
  if (allDone) {
    main.append(el("div", { class: "notice commercial-done-notice" },
      el("span", {}, "✓"),
      el("span", {}, "七阶段已完成。胶片条默认显示「分段」视图（不揉合集）；点顶栏「合成终稿/交付确认」可看图文视频合集。「需要你决定」仅在 ", el("code", {}, "awaiting_human"), " 时出现。")));
  } else {
    const view = commercialContentView(s);
    main.append(el("div", { class: "notice commercial-done-notice" },
      el("span", {}, "◈"),
      el("span", {}, "当前阶段：", el("b", {}, focusLabel),
        " · 证据视图：", el("b", {}, CONTENT_VIEW_LABEL[view] || view),
        "。点击顶栏阶段可切换，避免各阶段产物混在一起。")));
  }
  const view = commercialContentView(s);
  const precheck = renderCommercialAssetPrecheck(s);
  const assetPool = view === "assets" ? renderCommercialAssets(s) : null;
  const beats = renderCommercialBeats(s);
  const players = renderCommercialPlayers(s);
  const stageEvidence = renderCommercialStageEvidence(s);
  if (precheck) main.append(precheck);
  if (assetPool) main.append(assetPool);
  if (beats) main.append(beats);
  if (stageEvidence) main.append(stageEvidence);
  if (players) main.append(players);
  if (!beats && !players && !summary && !precheck && !assetPool) {
    main.append(el("div", { class: "hint" },
      "中文证据区数据未加载。请 ", el("b", {}, "重启 Backlot 服务"), " 后刷新页面（", el("code", {}, "python -m backlot serve"), "）。"));
  }
  return el("div", { class: "board commercial-board" }, main, aside);
}

// ---------------------------------------------------------------------------
// replay — scrub a completed run from its timestamps
// ---------------------------------------------------------------------------

// Python writers emit tz-aware UTC isoformat, but treat tz-naive strings as
// UTC too — mixing local-parsed and UTC-parsed timestamps would skew replay
// ordering by the user's UTC offset.
const ts = (iso) => {
  if (!iso) return null;
  let s = String(iso);
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(s)) s += "Z";
  const t = Date.parse(s);
  return Number.isFinite(t) ? t : null;
};

function replayBounds(s) {
  const moments = [];
  for (const st of s.stages) {
    for (const h of st.history_entries || []) {
      const t = ts(h.timestamp);
      if (t) moments.push(t);
    }
  }
  for (const ev of s.events || []) {
    const t = ts(ev.ts);
    if (t) moments.push(t);
  }
  if (moments.length < 2) return null;
  return { t0: Math.min(...moments), t1: Math.max(...moments) };
}

function stateAt(s, T) {
  const view = structuredClone(s);
  for (const st of view.stages) {
    const past = (st.history_entries || []).filter((h) => ts(h.timestamp) != null && ts(h.timestamp) <= T);
    if (!past.length) {
      st.status = "pending"; st.review = null; st.timestamp = null;
      st.gate_skipped = false; st.partial_progress = null;
    } else {
      const cur = past[past.length - 1];
      st.status = cur.status || "pending";
      st.timestamp = cur.timestamp;
    }
  }
  view.events = (view.events || []).filter((ev) => ts(ev.ts) != null && ts(ev.ts) <= T);

  // Storyboard: visuals appear as their scene finishes (events) or when the
  // assets stage has completed as of T (legacy runs without events).
  if (view.storyboard) {
    const assetsStage = view.stages.find((x) => x.name === "assets");
    const assetsDone = assetsStage && assetsStage.status === "completed";
    const finished = new Set();
    const startedNow = new Map();
    for (const ev of view.events) {
      if (!ev.scene_id) continue;
      if (ev.event === "finish") { finished.add(ev.scene_id); startedNow.delete(ev.scene_id); }
      else if (ev.event === "start") startedNow.set(ev.scene_id, ev);
      else if (ev.event === "error") startedNow.delete(ev.scene_id);
    }
    const scenePlanStage = view.stages.find((x) => x.name === "scene_plan");
    const scenePlanDone = scenePlanStage && ["completed", "awaiting_human"].includes(scenePlanStage.status);
    if (!scenePlanDone) {
      view.storyboard = null;
    } else {
      for (const card of view.storyboard.scenes) {
        const visible = assetsDone || finished.has(card.id);
        if (!visible) { card.visual = null; card.takes = []; card.audio = []; }
        card.generating = startedNow.has(card.id);
        card.generating_tool = (startedNow.get(card.id) || {}).tool;
      }
    }
  }
  // Final artifacts hide until their stage happened — for every project
  // shape, storyboard or not (a degraded run must not show the finished
  // movie before its stages ran).
  const scriptStage = view.stages.find((x) => x.name === "script");
  if (!(scriptStage && ["completed", "awaiting_human"].includes(scriptStage.status))) {
    delete view.artifacts.script;
  }
  const composeStage = view.stages.find((x) => x.name === "compose");
  if (!(composeStage && composeStage.status === "completed")) {
    view.media.renders = [];
  }
  return view;
}

function renderReplayBar(s) {
  const bounds = replayBounds(s);
  if (!bounds) return null;
  if (!replay) {
    // collapsed: just the entry button
    return el("div", { class: "replay-bar", style: "justify-content:flex-end" },
      el("span", { class: "rp-time" }, "scrub the whole run"),
      el("span", { class: "rp-btn", onclick: startReplay }, "▶ REPLAY RUN"));
  }
  const pos = (replay.t - replay.t0) / Math.max(1, replay.t1 - replay.t0);
  const timeLabel = el("span", { class: "rp-time" },
    new Date(replay.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  const setT = (value) => {
    replay.t = replay.t0 + (Number(value) / 1000) * (replay.t1 - replay.t0);
    timeLabel.textContent = new Date(replay.t)
      .toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };
  return el("div", { class: "replay-bar" },
    el("span", { class: "rp-btn", onclick: toggleReplayPlay }, replay.playing ? "❚❚" : "▶"),
    el("input", {
      type: "range", min: "0", max: "1000", value: String(Math.round(pos * 1000)),
      // A full render() would destroy this slider mid-drag: while dragging,
      // only pause + track the time label; re-render the board on release.
      onpointerdown: () => { replay.playing = false; },
      oninput: (e) => setT(e.target.value),
      onchange: (e) => { setT(e.target.value); render(); },
    }),
    timeLabel,
    el("span", { class: "rp-btn", onclick: stopReplay }, "✕ LIVE"),
  );
}

let replayTimer = null;

function startReplay() {
  const bounds = replayBounds(state);
  if (!bounds) return;
  replay = { ...bounds, t: bounds.t0, playing: true };
  document.body.classList.add("replaying");
  scheduleTick();
  render();
}

function stopReplay() {
  replay = null;
  clearTimeout(replayTimer);
  document.body.classList.remove("replaying");
  render();
}

function toggleReplayPlay() {
  if (!replay) return;
  replay.playing = !replay.playing;
  if (replay.playing) scheduleTick();
  render();
}

function scheduleTick() {
  // Single pending tick, ever — rapid pause/play must not stack chains.
  clearTimeout(replayTimer);
  replayTimer = setTimeout(tickReplay, 100);
}

function tickReplay() {
  if (!replay || !replay.playing) return;
  // A full run replays in ~20 seconds regardless of real duration
  // (10 renders/second — full re-render per tick, keep it modest).
  const step = (replay.t1 - replay.t0) / 200;
  replay.t = Math.min(replay.t1, replay.t + step);
  if (replay.t >= replay.t1) replay.playing = false;
  render();
  if (replay.playing) scheduleTick();
}

// ---------------------------------------------------------------------------
// page assembly
// ---------------------------------------------------------------------------

function render() {
  if (!state) return;
  const s = replay ? stateAt(state, replay.t) : state;
  document.title = `Backlot — ${s.title}`;
  document.body.classList.toggle("first", firstPaint);
  firstPaint = false;
  app.innerHTML = "";
  app.append(renderSlate(s));
  app.append(renderRail(s));
  if (!isCommercial(s)) {
    const replayBar = renderReplayBar(state);
    if (replayBar) app.append(replayBar);
  }
  const drawer = renderDrawer(s);
  if (drawer) app.append(drawer);
  const awaitingNotice = renderAwaitingNotice(s);
  if (awaitingNotice) app.append(awaitingNotice);
  const noState = renderNoState(s);
  if (noState) app.append(noState);

  if (isCommercial(s)) {
    app.append(renderCommercialBoard(s));
    return;
  }

  const main = el("div", { class: "main-col" });
  const script = renderScriptCard(s);
  if (script) main.append(script);
  const aside = el("aside", {});
  const decisions = renderDecisions(s);
  const activity = renderActivity(s);
  if (decisions) aside.append(decisions);
  if (activity) aside.append(activity);

  // Media sections live INSIDE the main column so a tall decisions rail
  // never pushes them below the fold — the column flows beside the rail.
  const storyboard = renderStoryboard(s);
  const found = renderFoundMedia(s);
  const renders = renderRenders(s);

  if (script || decisions || activity) {
    for (const section of [storyboard, found, renders]) {
      if (section) main.append(section);
    }
    app.append(el("div", { class: "board" }, main, aside));
  } else {
    for (const section of [storyboard, found, renders]) {
      if (section) app.append(section);
    }
  }
}

// Defensive normalization (F-02): the server contract guarantees these
// fields, but a sparse/legacy payload must degrade, never crash the board.
function normalize(s) {
  s.pipeline = s.pipeline || { pipeline_type: "unknown", stages: [], known: false };
  s.stages = Array.isArray(s.stages) ? s.stages : [];
  s.artifacts = s.artifacts || {};
  s.media = s.media || {};
  s.media.renders = Array.isArray(s.media.renders) ? s.media.renders : [];
  s.media.snapshots = Array.isArray(s.media.snapshots) ? s.media.snapshots : [];
  s.media.music = Array.isArray(s.media.music) ? s.media.music : [];
  s.events = Array.isArray(s.events) ? s.events : [];
  s.commercial = s.commercial || null;
  s.locale = s.locale || "en";
  if (s.storyboard && Array.isArray(s.storyboard.scenes)) {
    for (const c of s.storyboard.scenes) {
      c.takes = Array.isArray(c.takes) ? c.takes : [];
      c.audio = Array.isArray(c.audio) ? c.audio : [];
      c.required_assets = Array.isArray(c.required_assets) ? c.required_assets : [];
    }
  } else {
    s.storyboard = null;
  }
  return s;
}

async function refresh() {
  state = normalize(await getJSON(`/api/project/${encodeURIComponent(projectId)}/state`));
  if (isCommercial(state)) {
    document.documentElement.lang = "zh-CN";
    document.title = `Backlot — ${state.title}`;
  }
  render();
}

refresh().catch((err) => {
  app.innerHTML = "";
  app.append(el("div", { class: "empty", style: "margin-top:80px" },
    el("div", { class: "big" }, "PROJECT NOT FOUND"),
    el("div", {}, String(err))));
});
// ?static=1 disables the live feed (screenshots, static exports).
if (!new URLSearchParams(location.search).has("static")) {
  subscribe(
    `/api/project/${encodeURIComponent(projectId)}/events`,
    () => refresh().catch(console.error),
    (status) => {
      sseStatus = status;
      if (state) render();
    },
  );
}
