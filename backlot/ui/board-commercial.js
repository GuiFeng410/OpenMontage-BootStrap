import { el, fmtMoney, fmtMoneyCny, mediaURL, thumbURL } from "./lib.js";
import { stageNeedsDecision } from "./board-rail.js";
import { renderDecisionIntentPanel } from "./board-intent-panel.js";
import { renderProductionTierPanel } from "./board-tier.js";

export function isCommercial(state) {
  return state?.pipeline?.pipeline_type === "bootstrap-commercial";
}

export const INTENT_STATUS_ZH = {
  pending: "待确认",
  planned: "已汇总",
  approved: "聊天已确认",
  applied: "已执行",
  superseded: "已作废",
  rejected: "已拒绝",
  failed: "失败",
};

export function intentStatusZh(status) {
  return INTENT_STATUS_ZH[status] || "";
}

export function formatIntentStatusLine(item) {
  const summary = item?.summary || "";
  return `${intentStatusZh(item?.status)} · ${summary}`;
}

function renderIntentStatus(list) {
  if (!Array.isArray(list) || !list.length) return null;
  const body = el("div", { class: "commercial-intent-status-list" });
  for (const item of list) {
    body.append(el("div", { class: "commercial-intent-status-row" }, formatIntentStatusLine(item)));
  }
  return el("div", { class: "notice commercial-intent-status" }, body);
}

function renderFastTrackPause(pause) {
  if (!pause || typeof pause !== "object") return null;
  return el("div", { class: "notice commercial-fast-track-pause" },
    el("div", { class: "commercial-pause-friendly" }, pause.friendly_zh || ""),
    pause.current_question
      ? el("div", { class: "commercial-pause-question" }, pause.current_question)
      : null,
    el("div", { class: "commercial-chat-only" }, "暂停原因写在本页；可在看板继续选。"));
}

function renderRunnerStatus(status) {
  if (!status || typeof status !== "object") return null;
  const phase = status.phase || "idle";
  const label = {
    queued: "排队",
    applying: "进行中",
    producing: "进行中",
    paused: "暂停，要你选",
    ready: "已出片",
    exported: "已导出",
    needs_chat: "请在本页刷新或补 Key 后继续",
    idle: "本机空闲",
  }[phase] || phase;
  return el("div", { class: "notice commercial-runner-status" },
    el("div", { class: "commercial-runner-phase" }, label),
    status.friendly_zh
      ? el("div", { class: "commercial-runner-copy" }, status.friendly_zh)
      : null,
    status.current_question
      ? el("div", { class: "commercial-pause-question" }, status.current_question)
      : null);
}

function renderFinalVideo(projectId, finalVideo) {
  if (!finalVideo?.exists || !finalVideo.path) return null;
  const src = mediaURL(projectId, finalVideo.path);
  return el("div", { class: "notice commercial-final-video" },
    el("video", { controls: "", src, preload: "metadata", playsinline: "" }),
    el("a", {
      class: "commercial-final-download",
      href: src,
      download: "",
    }, "下载终稿"));
}

export function renderAwaitingNotice(s, context) {
  const awaiting = s.stages.find((x) => x.status === "awaiting_human") ||
    (isCommercial(s) ? s.stages.find(stageNeedsDecision) : null);
  if (!awaiting) return null;
  if (isCommercial(s)) {
    const dec = s.commercial?.decision;
    const prompt = dec?.prompt_zh || "请在聊天中回复以继续。";
    const examples = dec?.examples_zh;
    const options = Array.isArray(dec?.options) ? dec.options : [];
    if (options.length) {
      return renderDecisionIntentPanel({
        projectId: s.project_id,
        projectTitle: s.title,
        stage: dec?.stage || awaiting.name,
        decision: {
          ...dec,
          timestamp: awaiting.timestamp,
        },
        storage: window.sessionStorage,
        onDraftChange: context.requestRender,
      });
    }
    return el("div", { class: "notice commercial-notice" },
      el("span", { style: "font-size:calc(16px * var(--fs-scale))" }, "◈"),
      el("div", { class: "commercial-decision-body" },
        el("b", {}, `【需要你决定】${dec?.title_zh || dec?.stage_label_zh || (awaiting.label_zh || awaiting.name)}`),
        dec?.context_zh ? el("div", { class: "commercial-decision-context" }, dec.context_zh) : null,
        el("div", { class: "commercial-decision-prompt", style: "white-space:pre-line" }, prompt),
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

function renderCommercialPlanArchive(s, context) {
  const archive = s.commercial?.plan_archive || {};
  const b = s.commercial?.brief_summary || {};
  const view = commercialContentView(s, context.selectedStage);
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
  const roleCounts = new Map();
  for (const img of assets) {
    roleCounts.set(img.role_zh || "素材", (roleCounts.get(img.role_zh || "素材") || 0) + 1);
  }
  const body = el("div", { class: "panel-body commercial-summary" },
    el("div", { class: "kv-row" },
      el("span", { class: "kv-k" }, "素材总数"),
      el("span", { class: "kv-v" }, `共 ${assets.length} 张`)),
    el("div", { class: "kv-row" },
      el("span", { class: "kv-k" }, "用途"),
      el("span", { class: "kv-v" },
        [...roleCounts.entries()].map(([role, count]) => `${role}×${count}`).join(" · "))));
  const grid = el("div", { class: "asset-grid" });
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
    grid.append(card);
  }
  body.append(el("details", { class: "tech-details commercial-assets-details" },
    el("summary", {}, "展开图片清单"),
    grid));
  return el("div", { class: "panel commercial-assets-panel" },
    el("div", { class: "panel-head" }, el("h2", {}, "素材检查"), el("span", { class: "meta" }, "身份与角度")),
    body);
}

function renderCommercialUnusedAssets(s) {
  const assets = Array.isArray(s.commercial?.unused_assets)
    ? s.commercial.unused_assets
    : [];
  if (!assets.length) return null;
  return el("details", { class: "panel commercial-unused-assets" },
    el("summary", {},
      `未使用素材（${assets.length}）`,
      el("span", { class: "meta" }, " · 展开核对")),
    el("div", { class: "panel-body commercial-unused-assets-list" },
      assets.map((item) => el("div", {
        class: "commercial-unused-asset",
        "data-path": item.path || "",
      },
      el("b", {}, item.file || (item.path || "").split("/").pop() || "未命名素材"),
      el("span", {}, item.reason || "未分配到任何 canonical Beat"),
      el("code", {}, item.path || "项目内路径待补齐"),
      el("span", { class: "status-chip" }, item.status || "unassigned")))));
}

function renderCommercialAssetPrecheck(s, context) {
  const view = commercialContentView(s, context.selectedStage);
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
    body.append(el("details", { class: "tech-details" },
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
  const engine = [beat.provider, beat.model].filter(Boolean).join(" / ");
  if (/AI|视频生成|Agnes/i.test(raw) || engine) {
    const detail = engine ? `（${engine}）` : "";
    const qualifier = raw && !/^视频生成$/i.test(raw) ? ` · ${raw}` : "";
    return `视频生成-AI${detail}${qualifier}`;
  }
  return raw || "—";
}

function renderBeatGenerationDetails(beat) {
  const rows = [
    ["文案", beat.copy_plan_zh],
    ["镜头", beat.shot_plan_zh],
    ["生成说明", beat.generation_prompt_zh],
    ["制作方式", formatCommercialMethod(beat)],
    ["Provider", beat.provider],
    ["Model", beat.model],
  ];
  return el("details", { class: "beat-plan-fold" },
    el("summary", {}, "文案、镜头与生成说明"),
    el("div", { class: "beat-generation-grid" },
      rows.map(([label, value]) => el("div", { class: "beat-generation-row" },
        el("b", {}, label),
        el("span", {}, value || "—")))));
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

export function commercialFocusStage(s, selectedStage = null) {
  const allowed = Array.isArray(s.commercial?.confirm_stop_ids) && s.commercial.confirm_stop_ids.length
    ? new Set(s.commercial.confirm_stop_ids)
    : null;
  const stages = allowed
    ? (s.stages || []).filter((x) => allowed.has(x.name))
    : (s.stages || []);
  if (selectedStage && (!allowed || allowed.has(selectedStage))) return selectedStage;
  const awaiting = stages.find((x) => x.status === "awaiting_human");
  if (awaiting) return awaiting.name;
  const active = stages.find((x) => x.status === "in_progress");
  if (active) return active.name;
  const known = stages.filter((x) => !x.undeclared);
  if (known.length && known.every((x) => x.status === "completed")) {
    return allowed ? "delivery_signoff" : "segment_build";
  }
  for (const name of Object.keys(STAGE_CONTENT_VIEW)) {
    if (allowed && !allowed.has(name)) continue;
    const st = stages.find((x) => x.name === name);
    if (st && ["pending", "in_progress", "failed"].includes(st.status)) return name;
  }
  return "brief_locked";
}

export function commercialContentView(s, selectedStage = null) {
  const stage = commercialFocusStage(s, selectedStage);
  return STAGE_CONTENT_VIEW[stage] || "plan";
}

const COMMERCIAL_ASSIGNMENT_STATUS_ZH = {
  user_asset: "用户素材",
  reuse_pending: "复用待确认",
  reuse_approved: "复用已确认",
  missing: "缺少素材",
  i2i_planned: "I2I 待生成",
  generating: "I2I 生成中",
  review_pending: "I2I 待审",
  approved: "I2I 已批准",
  failed: "I2I 失败",
  assignment_conflict: "素材冲突",
};

function commercialAssignmentStatusZh(beat) {
  return beat.assignment_status_zh
    || COMMERCIAL_ASSIGNMENT_STATUS_ZH[beat.assignment_status]
    || "缺少素材";
}

function commercialAssignmentReason(beat) {
  return beat.assignment_reason
    || "没有可核对的闭环素材，请补齐账本分配或生成计划。";
}

function renderCommercialMediaStack(s, beat, view, context) {
  const stack = el("div", { class: "beat-media-stack" });
  const ledger = beat.ledger || [];
  const images = ledger.filter((x) =>
    x.kind === "image"
    && x.path
    && x.exists === true
    && x.preview_kind !== "candidate");
  const candidatePreviews = Array.isArray(beat.candidate_previews)
    ? beat.candidate_previews.filter((item) => item?.path)
    : [];
  const approvedPlanned = Array.isArray(beat.planned_entries)
    ? beat.planned_entries.filter((item) =>
        item?.kind === "image"
        && item?.path
        && item?.exists === true
        && item?.preview_kind === "approved")
    : [];
  const videos = ledger.filter((x) => x.kind === "video" && x.path && x.exists === true);
  const selectedVideo = videos.find((v) => v.selected) || videos[0];
  const segmentItem = (s.commercial?.stage_evidence?.segment || []).find((item) =>
    (item.beat || item.id) === beat.beat);
  const segmentVideo = segmentItem?.path && segmentItem?.exists === true
    ? segmentItem
    : null;
  const missingVideo = ledger.find((x) =>
    x.kind === "video" && x.missing_path && x.exists === false)?.missing_path
    || beat.asset_missing_path;

  if (view === "plan") {
    return null; // 方案确认：不放媒体
  }

  if (view === "assets") {
    for (const img of images) {
      const isExpand = /扩展|i2i|AI/i.test(`${img.label_zh || ""}${img.note_zh || ""}`);
      stack.append(el("div", { class: `beat-media image${img.selected ? " selected" : ""}${isExpand ? " expand" : ""}` },
        el("img", {
          src: thumbURL(s.project_id, img.path, 480),
          loading: "lazy",
          alt: img.file || "",
        }),
        el("span", { class: "media-cap" }, img.label_zh || (isExpand ? "AI扩展 · 已批准" : "用户素材"))));
    }
    for (const img of approvedPlanned) {
      stack.append(el("div", { class: "beat-media image selected approved" },
        el("img", {
          src: thumbURL(s.project_id, img.path, 480),
          loading: "lazy",
          alt: img.file || img.label_zh || "",
        }),
        el("span", { class: "media-cap" }, img.label_zh || "I2I 已批准")));
    }
    for (const img of candidatePreviews) {
      stack.append(el("div", {
        class: "beat-media image candidate",
        "data-candidate-status": img.status || "review_pending",
      },
      el("img", {
        src: thumbURL(s.project_id, img.path, 480),
        loading: "lazy",
        alt: img.file || img.label_zh || "I2I 候选",
      }),
      el("span", { class: "media-cap" },
        `${img.label_zh || "I2I 候选"} · 候选/待审`)));
    }
    if (!images.length && !approvedPlanned.length && !candidatePreviews.length && beat.reference_path) {
      stack.append(el("div", { class: "beat-media image reference-unmapped" },
        el("img", {
          src: thumbURL(s.project_id, beat.reference_path, 480),
          loading: "lazy",
          alt: beat.ref || "参考素材",
        }),
        el("span", { class: "media-cap" }, "参考素材 · 未闭环")));
    }
    if (!stack.childNodes.length) {
      stack.append(el("div", { class: "beat-media empty" },
        commercialAssignmentReason(beat)));
    }
    const pendingExpand = (
      beat.assignment_status === "i2i_planned"
      || beat.assignment_status === "generating"
    );
    if (pendingExpand) {
      stack.append(el("div", { class: "beat-media empty expand-slot" },
        beat.assignment_status === "generating"
          ? "I2I 生成中"
          : (beat.need_detail_zh || "I2I 待生成")));
    }
    return stack;
  }

  // 试片只在 hero 显示 sample_reel；初稿只在 hero 显示 full_draft_pro。
  if (view === "sample" || view === "draft") return null;

  // 分段只认 review_overview/batch review 挂接到当前 Beat 的实际输出。
  if (view === "segment") {
    const vid = segmentVideo;
    if (!vid) {
      stack.append(el("div", { class: "beat-media empty" },
        segmentItem?.missing_reason_zh
          || (missingVideo
            ? `媒体文件不存在：${missingVideo}`
            : "该 Beat 尚无已挂接分段视频")));
      return stack;
    }
    const src = mediaURL(s.project_id, vid.path);
    const video = el("video", {
      src, muted: "", preload: "metadata", playsinline: "",
    });
    context.restorePlaybackState(video, src);
    const box = el("div", { class: "beat-media video selected" },
      video,
      el("span", { class: "play" }, "▶"),
      el("span", { class: "media-cap" }, vid.label_zh || "分段视频"));
    box.onclick = () => {
      const node = box.querySelector("video");
      if (!node) return;
      if (node.paused) node.play(); else node.pause();
    };
    stack.append(box);
    if (beat.reference_path) {
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
    const src = mediaURL(s.project_id, vid.path);
    const video = el("video", {
      src, muted: "", preload: "metadata", playsinline: "",
    });
    context.restorePlaybackState(video, src);
    const box = el("div", { class: "beat-media video selected" },
      video,
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
  if (view === "sample" || view === "segment" || view === "draft") return null;
  // full: 全部标注
  if (!items.length) return null;
  const strip = el("div", { class: "asset-label-strip" });
  for (const item of items) {
    const cls = `asset-label${item.selected ? " selected" : ""}${item.exists === false ? " missing" : ""}`;
    const title = [item.note_zh, item.path || item.missing_path].filter(Boolean).join(" · ");
    const label = item.label_zh || item.label || (item.kind === "image" ? "用户素材" : "素材");
    const missingHint = item.exists === false && item.missing_path
      ? ` · 文件不存在：${item.missing_path}`
      : "";
    strip.append(el("span", { class: cls, title: title || item.file },
      `${label}${item.selected ? " · 已选" : ""}`,
      item.file ? el("i", {}, ` · ${item.file}`) : null,
      missingHint ? el("i", {}, missingHint) : null));
  }
  return strip;
}

function renderCommercialPlannedEntries(s, beat, view) {
  const entries = Array.isArray(beat.planned_entries)
    ? beat.planned_entries.filter((item) => item?.kind === "image")
    : [];
  if (!entries.length || view !== "assets") return null;
  const statusLabels = {
    planned: "待生成",
    i2i_planned: "待生成",
    generating: "生成中",
    generated: "候选/待审",
    review_pending: "候选/待审",
    i2i_review_pending: "候选/待审",
    ready: "候选/待审",
    approved: "已批准",
    failed: "生成失败",
    rejected: "生成失败",
  };
  const group = el("div", {
    class: "asset-label-strip planned-entry-strip",
    style: "gap:8px",
  });
  for (const item of entries) {
    const reportedStatus = item.status || "planned";
    const unavailableReady = (
      ["ready", "approved", "review_pending", "generated"].includes(reportedStatus)
      && (!item.path || item.exists === false)
    );
    const status = unavailableReady
      ? "failed"
      : item.preview_kind === "candidate"
      ? "review_pending"
      : reportedStatus;
    const card = el("div", {
      class: `beat-field planned-entry-card status-${status}`,
      "data-status": status,
      style: "display:grid;gap:6px",
    });
    card.append(el("div", {
      style: "display:flex;justify-content:space-between;gap:8px;align-items:center",
    },
      el("b", {}, item.label_zh || (item.kind === "video" ? "计划视频" : "计划图片")),
      el("span", {
        class: `status-chip ${status === "approved" ? "ok" : ["failed", "review_pending"].includes(status) ? "warn" : ""}`,
      }, statusLabels[status] || status)));
    if (["review_pending", "generated", "approved"].includes(status) && item.path && item.exists !== false) {
      card.append(el("img", {
        src: thumbURL(s.project_id, item.path, 480),
        loading: "lazy",
        alt: item.label_zh || item.prompt_zh || "",
        style: "width:100%;max-height:160px;object-fit:contain;border-radius:6px;background:var(--media-bg)",
      }));
      if (status !== "approved") {
        card.append(el("span", { class: "commercial-candidate-label" }, "候选/待审 · 尚未批准"));
      }
    }
    if (item.prompt_zh) card.append(el("div", {}, item.prompt_zh));
    const engine = [item.provider, item.model].filter(Boolean).join(" / ");
    if (engine) card.append(el("span", { class: "cbc-sub" }, engine));
    if (item.planned_output_path) {
      card.append(el("span", { class: "cbc-sub" }, `计划输出 · ${item.planned_output_path}`));
    }
    const missingOutputPath = item.missing_output_path
      || (unavailableReady ? item.output_path : "");
    if (missingOutputPath) {
      card.append(el("span", { class: "warn-text" }, `缺失输出 · ${missingOutputPath}`));
    }
    const error = item.error_zh || (unavailableReady ? "输出文件不存在" : "");
    if (error) card.append(el("div", { class: "warn-text" }, error));
    group.append(card);
  }
  return group;
}

function renderCommercialBeatCard(s, beat, index = 0, context) {
  const view = commercialContentView(s, context.selectedStage);
  const assignmentStatus = beat.assignment_status || "missing";
  const assignmentLabel = commercialAssignmentStatusZh(beat);
  const statusClass = ["user_asset", "reuse_approved", "approved"].includes(assignmentStatus)
    ? "ok"
    : [
        "missing",
        "reuse_pending",
        "failed",
        "review_pending",
        "assignment_conflict",
      ].includes(assignmentStatus)
    ? "warn"
    : "";
  const wrap = el("div", {
    class: `commercial-beat-card mode-${view}`,
    "data-beat": beat.beat || "",
    "data-assignment-status": assignmentStatus,
  });

  wrap.append(el("div", { class: "cbc-head" },
    el("div", { class: "cbc-title" }, beatOrdinalZh(beat.beat, index)),
    el("span", {
      class: `status-chip ${statusClass}`,
    }, assignmentLabel)));

  wrap.append(el("div", { class: "cbc-time" }, `时间段：${beat.time || "未填写"}`));

  const media = renderCommercialMediaStack(s, beat, view, context);
  if (media) wrap.append(media);
  const plannedEntries = renderCommercialPlannedEntries(s, beat, view);
  if (plannedEntries) wrap.append(plannedEntries);

  const body = el("div", { class: "cbc-body" });
  body.append(el("div", { class: "commercial-assignment-summary" },
    el("div", { class: "beat-field" },
      el("b", {}, "素材安排"),
      el("div", {}, beat.asset_plan_zh || "尚未写入具体素材安排")),
    el("div", { class: "beat-field assignment-counts" },
      el("b", {}, "所需 / 现有"),
      el("div", {},
        `${beat.required_count ?? beat.need_count ?? 1} 张 / ${beat.available_count ?? beat.have_count ?? 0} 张`)),
    el("div", { class: "beat-field" },
      el("b", {}, "状态"),
      el("div", {}, assignmentLabel)),
    el("div", { class: "beat-field assignment-reason" },
      el("b", {}, "原因"),
      el("div", {}, commercialAssignmentReason(beat)))));
  const warnings = Array.isArray(beat.assignment_warnings)
    ? beat.assignment_warnings.filter(Boolean)
    : [];
  if (beat.assignment_warning && !warnings.includes(beat.assignment_warning)) {
    warnings.unshift(beat.assignment_warning);
  }
  for (const warning of warnings) {
    body.append(el("div", { class: "commercial-assignment-warning" }, warning));
  }
  if (view === "plan") {
    body.append(
      el("div", { class: "beat-field" }, el("b", {}, "文案规划"), el("div", {}, beat.copy_plan_zh || "—")),
      el("div", { class: "beat-field" }, el("b", {}, "镜头规划"), el("div", {}, beat.shot_plan_zh || "—")));
  } else if (view === "assets") {
    if (beat.need_detail_zh) {
      body.append(el("div", { class: "beat-field warn-text" },
        el("b", {}, "I2I 扩展/缺口"),
        el("div", {}, beat.need_detail_zh)));
    }
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
    if (["sample", "segment", "draft"].includes(view)) {
      body.append(renderBeatGenerationDetails(beat));
    }
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

function renderCommercialTimeline(s, context) {
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
          const card = context.app.querySelector(`.commercial-beat-card[data-beat="${m.beat}"]`);
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

function renderCommercialBeats(s, context) {
  const allBeats = s.commercial?.beats || [];
  if (!allBeats.length) return null;
  const view = commercialContentView(s, context.selectedStage);
  if (view === "compose" || view === "delivery") return null;
  const sampleBeatIds = Array.isArray(s.commercial?.stage_evidence?.sample?.beat_ids)
    ? s.commercial.stage_evidence.sample.beat_ids
    : [];
  const beats = view === "sample"
    ? allBeats.filter((beat) => sampleBeatIds.includes(beat.beat))
    : allBeats;
  if (!beats.length) return null;
  const focus = commercialFocusStage(s, context.selectedStage);
  const focusLabel = (s.stages.find((x) => x.name === focus) || {}).label_zh || focus;
  const grid = el("div", { class: "beat-card-grid" });
  beats.forEach((beat, i) => grid.append(renderCommercialBeatCard(s, beat, i, context)));
  const batches = s.commercial?.batches || [];
  const batchMeta = el("span", { class: "meta" },
    ` · ${CONTENT_VIEW_LABEL[view] || view}`,
    context.selectedStage ? ` · 已选：${focusLabel}` : "",
    batches.length && s.commercial?.review_mode === "pro" ? ` · ${batches.length} 批` : "");
  const timeline = renderCommercialTimeline(s, context);
  const hint = el("div", { class: "content-view-hint" },
    "证据按阶段递进：方案确认看文案 → 素材检查看用户图与扩展安排 → 试片/分段看入片视频 → 初稿看问题与修改 → 终稿看技术检查 → 交付看签收。",
    el("b", {}, " 点击顶栏阶段"), " 可切换该阶段视图。");
  return el("div", { class: "commercial-film-block" },
    el("div", { class: "section-title" }, "Beat 胶片条 / 时间线", batchMeta),
    hint,
    timeline,
    grid);
}

function renderCommercialPlayers(s, context) {
  const view = commercialContentView(s, context.selectedStage);
  // 方案/素材无播放器；分段视频只进对应 Beat 卡，不创建 hero。
  if (view === "plan" || view === "assets" || view === "segment") return null;
  const evidence = s.commercial?.stage_evidence || {};
  const stageEvidence = {
    sample: evidence.sample,
    draft: evidence.draft,
    compose: evidence.compose,
    delivery: evidence.delivery,
  }[view] || {};
  const canonical = stageEvidence?.path && stageEvidence?.exists === true
    ? { path: stageEvidence.path }
    : null;
  const stagePlayer = {
    sample: canonical ? { label: "试片", ...canonical } : null,
    draft: canonical ? { label: "完整初稿", ...canonical } : null,
    compose: evidence.compose?.path && evidence.compose?.exists === true
      ? { label: "终稿候选", path: evidence.compose.path } : null,
    delivery: evidence.delivery?.path && evidence.delivery?.exists === true
      ? { label: "终稿", path: evidence.delivery.path } : null,
  }[view];
  if (!stagePlayer) return null;
  const players = [stagePlayer];
  const tabs = el("div", { class: "render-meta" });
  players.forEach((p, i) => {
    tabs.append(el("span", {
      class: `v${i === context.activeRender ? " active" : ""}`,
      onclick: () => context.setActiveRender(i),
    }, p.label));
  });
  if (context.activeRender >= players.length) context.setActiveRender(0, false);
  const current = players[context.activeRender];
  const src = mediaURL(s.project_id, current.path);
  const video = el("video", {
    src,
    controls: "", preload: "metadata",
  });
  video.addEventListener("click", () => { if (video.paused) video.play().catch(() => {}); });
  context.restorePlaybackState(video, src);
  return el("div", {},
    el("div", { class: "section-title" }, "成片预览",
      el("span", { class: "meta" }, current.path.split("/").pop())),
    el("div", { class: "render-hero" }, video),
    tabs);
}

function renderCommercialStageEvidence(s, context) {
  const view = commercialContentView(s, context.selectedStage);
  const evidence = s.commercial?.stage_evidence || {};
  const mediaWarning = (item) => (
    item?.exists === false && item?.missing_path
      ? el("div", { class: "hint warn-text" },
        item.missing_reason_zh || `媒体文件不存在：${item.missing_path}`)
      : null
  );
  if (view === "sample") {
    const sample = evidence.sample || {};
    const body = el("div", { class: "panel-body commercial-summary" },
      el("div", { class: "kv-row" }, el("span", { class: "kv-k" }, "试片状态"),
        el("span", { class: "kv-v" }, sample.status || "待生成")),
      el("div", { class: "kv-row" }, el("span", { class: "kv-k" }, "时长"),
        el("span", { class: "kv-v" }, sample.duration_seconds != null ? `${sample.duration_seconds}s` : "待探测")),
      sample.path
        ? el("div", { class: "kv-row" }, el("span", { class: "kv-k" }, "项目相对路径"),
          el("span", { class: "kv-v evidence-path" }, sample.path))
        : null,
      sample.artifact_path
        ? el("div", { class: "kv-row" }, el("span", { class: "kv-k" }, "阶段 artifact"),
          el("span", { class: "kv-v evidence-path" }, sample.artifact_path))
        : null,
      sample.user_confirmation_text
        ? el("div", { class: "commercial-evidence-list" }, el("b", {}, "用户确认"), el("div", {}, sample.user_confirmation_text))
        : el("div", { class: "hint" }, "尚未记录用户对试片的确认。"),
      mediaWarning(sample),
      sample.candidate?.path
        ? el("div", { class: "hint warn-text" },
          `未挂接阶段证据：发现候选 ${sample.candidate.path}；补写 sample_reel artifact 后才会显示。`)
        : null);
    return el("div", { class: "panel commercial-stage-evidence" },
      el("div", { class: "panel-head" }, el("h2", {}, "试片确认"), el("span", { class: "meta" }, "sample_reel")),
      body);
  }
  if (view === "draft") {
    const draft = evidence.draft || {};
    const issues = draft.issue_segments || [];
    const modifications = draft.modification_list || [];
    const body = el("div", { class: "panel-body commercial-summary" },
      draft.path
        ? el("div", { class: "kv-row" }, el("span", { class: "kv-k" }, "项目相对路径"),
          el("span", { class: "kv-v evidence-path" }, draft.path))
        : null,
      draft.artifact_path
        ? el("div", { class: "kv-row" }, el("span", { class: "kv-k" }, "阶段 artifact"),
          el("span", { class: "kv-v evidence-path" }, draft.artifact_path))
        : null,
      mediaWarning(draft),
      draft.candidate?.path
        ? el("div", { class: "hint warn-text" },
          `未挂接阶段证据：发现候选 ${draft.candidate.path}；补写 full_draft_pro artifact 后才会显示。`)
        : null,
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
    const warning = mediaWarning(compose);
    if (warning) body.append(warning);
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
        : null,
      mediaWarning(delivery));
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

function renderSseBanner(s, context) {
  if (!isCommercial(s)) return null;
  if (context.sseStatus === "live") return null;
  const text = context.sseStatus === "disconnected"
    ? "看板实时连接已断开，已启用低频自动轮询；SSE 恢复后会自动停止轮询。"
    : "正在连接看板实时更新…";
  return el("div", { class: `notice sse-banner ${context.sseStatus}` },
    el("span", {}, "⟳"),
    el("span", {}, text),
    el("button", {
      class: "sse-refresh-btn",
      onclick: () => context.requestRefresh(),
    }, "刷新"));
}

export function renderCommercialBoard(s, context) {
  const aside = el("aside", { class: "commercial-aside" });
  const summary = renderCommercialSummary(s);
  const planArchive = renderCommercialPlanArchive(s, context);
  const decisions = renderCommercialDecisions(s);
  const costPanel = renderCommercialCostPanel(s);
  const activity = context.renderActivity(s);
  if (summary) aside.append(summary);
  if (planArchive) aside.append(planArchive);
  if (decisions) aside.append(decisions);
  if (costPanel) aside.append(costPanel);
  if (activity) aside.append(activity);

  const main = el("div", { class: "main-col" });
  const tierPanel = renderProductionTierPanel({
    projectId: s.project_id,
    lockedTier: s.commercial?.brief_summary?.production_tier,
    requestRender: () => {
      if (typeof context.requestRefresh === "function") {
        context.requestRefresh();
        return;
      }
      if (typeof context.requestRender === "function") context.requestRender();
    },
  });
  if (tierPanel) main.append(tierPanel);
  const intentStatus = renderIntentStatus(s.commercial?.interaction_intents);
  if (intentStatus) main.append(intentStatus);
  const runner = renderRunnerStatus(s.commercial?.runner_status);
  if (runner) main.append(runner);
  const pause = renderFastTrackPause(s.commercial?.fast_track_pause);
  if (pause) main.append(pause);
  const finalVideo = renderFinalVideo(s.project_id, s.commercial?.final_video);
  if (finalVideo) main.append(finalVideo);
  const sseBanner = renderSseBanner(s, context);
  if (sseBanner) main.append(sseBanner);
  const legacyNotice = renderCommercialLegacyNotice(s);
  if (legacyNotice) main.append(legacyNotice);
  const allDone = s.stages.filter((x) => !x.undeclared).every((x) => x.status === "completed");
  const focus = commercialFocusStage(s, context.selectedStage);
  const focusLabel = (s.stages.find((x) => x.name === focus) || {}).label_zh || focus;
  if (allDone) {
    main.append(el("div", { class: "notice commercial-done-notice" },
      el("span", {}, "✓"),
      el("span", {}, "七阶段已完成。胶片条默认显示「分段」视图（不揉合集）；点顶栏「合成终稿/交付确认」可看图文视频合集。「需要你决定」仅在 ", el("code", {}, "awaiting_human"), " 时出现。")));
  } else {
    const view = commercialContentView(s, context.selectedStage);
    main.append(el("div", { class: "notice commercial-done-notice" },
      el("span", {}, "◈"),
      el("span", {}, "当前阶段：", el("b", {}, focusLabel),
        " · 证据视图：", el("b", {}, CONTENT_VIEW_LABEL[view] || view),
        "。点击顶栏阶段可切换，避免各阶段产物混在一起。")));
  }
  const view = commercialContentView(s, context.selectedStage);
  const precheck = renderCommercialAssetPrecheck(s, context);
  const assetPool = view === "assets" ? renderCommercialAssets(s) : null;
  const unusedAssets = view === "assets" ? renderCommercialUnusedAssets(s) : null;
  const beats = renderCommercialBeats(s, context);
  const players = renderCommercialPlayers(s, context);
  const stageEvidence = renderCommercialStageEvidence(s, context);
  if (precheck) main.append(precheck);
  if (assetPool) main.append(assetPool);
  if (unusedAssets) main.append(unusedAssets);
  if (beats) main.append(beats);
  if (stageEvidence) main.append(stageEvidence);
  if (players) main.append(players);
  if (!beats && !players && !summary && !precheck && !assetPool) {
    main.append(el("div", { class: "hint" },
      "中文证据区数据未加载。请 ", el("b", {}, "重启 Backlot 服务"), " 后刷新页面（", el("code", {}, "python -m backlot serve"), "）。"));
  }
  return el("div", { class: "board commercial-board" }, main, aside);
}

