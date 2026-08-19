import { el } from "./lib.js";
import {
  clearDraft,
  createDraft,
  decisionRevision,
  gapPlanReady,
  inspectStoredDraft,
  saveDraft,
  selectOption,
  selectedOptionId,
  setDraftNote,
  summarizeDraft,
} from "./board-intent-state.js";
import {
  buildDecisionIntent,
  submitDecisionIntent,
} from "./board-intent-submit.js";
import { RUNNER_GONE_ZH } from "./board-runtime.js";

const locallySubmitted = new Map();

function primarySubmitLabel(stage) {
  return stage === "assets_gate" ? "开始出片" : "进入下一步";
}

function submittedFeedback(stage) {
  if (stage === "assets_gate") {
    return "已点开始出片，请留在本页等待本机处理。";
  }
  return "已进入下一步，请留在本页等待本机处理。";
}

const GAP_ACTIONS = [
  { id: "upload", label_zh: "补传", description_zh: "稍后在素材检查页上传。" },
  { id: "i2i", label_zh: "图生图", description_zh: "锁定生图模型；同意方案后才生成。" },
  { id: "reuse", label_zh: "复用", description_zh: "用已有图片覆盖这一段。" },
  { id: "skip", label_zh: "不补", description_zh: "本段不补图，改为概念表达。" },
];

function currentDecision(decision, stage) {
  const options = Array.isArray(decision?.options) ? decision.options : [];
  return {
    key: `${stage}::current`,
    title: decision?.title_zh || decision?.stage_label_zh || stage,
    options,
  };
}

function bindOptionButton(button, { draftRef, storage, onDraftChange, itemKey, option }) {
  button.addEventListener("click", () => {
    draftRef.draft = selectOption(draftRef.draft, itemKey, option);
    saveDraft(storage, draftRef.draft);
    if (typeof onDraftChange === "function") onDraftChange(draftRef.draft);
  });
}

function renderChoiceRow({
  draftRef,
  storage,
  onDraftChange,
  decisionKey,
  options,
  stale,
  locked,
}) {
  const row = el("div", { class: "gap-choice-row" });
  for (const option of options) {
    const selected = !stale && selectedOptionId(draftRef.draft, decisionKey) === option.id;
    const button = el("button", {
      type: "button",
      class: [
        "commercial-decision-option",
        selected ? "selected" : "",
        option.disabled ? "disabled" : "",
      ].filter(Boolean).join(" "),
      "data-option-id": option.id,
      "aria-pressed": selected ? "true" : "false",
      disabled: stale || locked || option.disabled ? "" : null,
    },
    el("span", { class: "commercial-decision-option-head" },
      el("b", {}, option.label_zh)),
    option.description_zh
      ? el("span", { class: "commercial-decision-option-copy" }, option.description_zh)
      : null);
    if (!stale && !locked && !option.disabled) {
      bindOptionButton(button, {
        draftRef,
        storage,
        onDraftChange,
        itemKey: decisionKey,
        option,
      });
    }
    row.append(button);
  }
  return row;
}

function renderGapPlan({
  gapPlan,
  draftRef,
  storage,
  onDraftChange,
  stale,
  locked,
}) {
  if (!gapPlan || typeof gapPlan !== "object") return null;
  const block = el("div", { class: "gap-plan" });
  const covered = Array.isArray(gapPlan.covered) ? gapPlan.covered : [];
  const gaps = Array.isArray(gapPlan.gaps) ? gapPlan.gaps : [];
  if (covered.length) {
    block.append(el("div", { class: "gap-plan-label" }, "已有画面"));
    for (const item of covered) {
      block.append(el("div", { class: "gap-covered-row" },
        el("b", {}, item.beat_id || ""),
        el("span", {}, `${item.need_zh || ""} · ${item.path || ""}`)));
    }
  }
  if (!gaps.length) {
    block.append(el("div", { class: "gap-plan-enough" }, "图已够，确认方案后进入素材检查。"));
    return block;
  }
  block.append(el("div", { class: "gap-plan-label" }, "缺口四选（每段一项）"));
  const reusePaths = Array.isArray(gapPlan.reuse_paths) ? gapPlan.reuse_paths : [];
  const models = Array.isArray(gapPlan.image_models) ? gapPlan.image_models : [];
  let anyI2i = false;
  for (const gap of gaps) {
    const beatId = gap.beat_id;
    const choice = selectedOptionId(draftRef.draft, `gap::${beatId}`);
    if (choice === "i2i") anyI2i = true;
    const card = el("div", { class: "gap-beat-card" },
      el("div", { class: "gap-beat-head" },
        el("b", {}, gap.beat_id || ""),
        el("span", {}, gap.need_zh || "所需画面")));
    card.append(renderChoiceRow({
      draftRef,
      storage,
      onDraftChange,
      decisionKey: `gap::${beatId}`,
      stale,
      options: GAP_ACTIONS.map((action) => ({
        ...action,
        disabled: (action.id === "i2i" && !gapPlan.image_key_present)
          || (action.id === "reuse" && !reusePaths.length),
        description_zh: action.id === "i2i" && !gapPlan.image_key_present
          ? "未检测到生图 Key，不可执行。"
          : action.id === "reuse" && !reusePaths.length
            ? "还没有可复用的已有图。"
            : action.description_zh,
      })),
      locked,
    }));
    if (choice === "reuse" && reusePaths.length) {
      card.append(el("div", { class: "gap-plan-sublabel" }, "复用哪张"));
      card.append(renderChoiceRow({
        draftRef,
        storage,
        onDraftChange,
        decisionKey: `gap_reuse::${beatId}`,
        stale,
        options: reusePaths.map((path) => ({
          id: path,
          label_zh: path,
        })),
        locked,
      }));
    }
    block.append(card);
  }
  if (anyI2i && gapPlan.image_key_present) {
    ensureDefaultImageModel(draftRef, storage, gapPlan, models);
    const availableCount = models.filter((item) => item.available).length;
    block.append(el("div", { class: "gap-image-model" },
      el("div", { class: "gap-plan-label" }, "生图模型（全片共用）"),
      el("div", { class: "gap-plan-sublabel" },
        availableCount > 1
          ? "检测到多个可用 Key，请点选一个。不标推荐，锁定后不静默更换。"
          : "锁定后各段图生图都用这一模型。"),
      renderChoiceRow({
        draftRef,
        storage,
        onDraftChange,
        decisionKey: "image_model::project",
        stale,
        options: models.map((item) => ({
          id: item.id,
          label_zh: item.label_zh || item.id,
          disabled: !item.available,
          description_zh: item.available ? "" : "未填入 Key",
        })),
        locked,
      })));
  }
  return block;
}

function ensureDefaultImageModel(draftRef, storage, gapPlan, models) {
  if (selectedOptionId(draftRef.draft, "image_model::project")) return;
  const defaultId = gapPlan.default_image_model
    || (models.find((item) => item.available) || {}).id;
  const spec = models.find((item) => item.id === defaultId && item.available);
  if (!spec) return;
  draftRef.draft = selectOption(draftRef.draft, "image_model::project", {
    id: spec.id,
    label_zh: spec.label_zh || spec.id,
  });
  saveDraft(storage, draftRef.draft);
}

function revisionFor({ projectId, stage, decision }) {
  const { timestamp, ...payload } = decision || {};
  return decisionRevision({
    projectId,
    stage,
    timestamp,
    decision: payload,
  });
}

export function renderDecisionIntentPanel({
  projectId,
  projectTitle,
  stage,
  decision,
  storage,
  interactionIntents = [],
  onDraftChange,
  runnerBound = true,
}) {
  const item = currentDecision(decision, stage);
  const revision = revisionFor({ projectId, stage, decision });
  const identity = { projectId, stage, revision };
  const inspection = inspectStoredDraft(storage, identity);
  let draft = inspection.draft || createDraft(identity);
  const stale = ["stale", "corrupt"].includes(inspection.status);
  const panelId = `commercial-intent-panel:${projectId}:${stage}`;
  const submissionKey = `${projectId}:${stage}`;
  const activeIntent = (Array.isArray(interactionIntents) ? interactionIntents : [])
    .find((entry) => entry?.stage === stage
      && entry?.revision === revision
      && ["pending", "planned", "approved", "applied"].includes(entry?.status));
  const submissionLocked = Boolean(activeIntent) || locallySubmitted.has(submissionKey);
  const localSubmissionCopy = locallySubmitted.get(submissionKey) || "";
  const submissionCopy = activeIntent?.status === "planned"
    ? "选择已汇总，本机正在应用，请留在本页。"
    : activeIntent?.status === "applied"
      ? "选择已应用，正在进入下一步，请留在本页。"
      : localSubmissionCopy || (submissionLocked
        ? "选择已提交，等待本机处理，请留在本页。"
        : "");
  const feedback = el("div", {
    class: "commercial-intent-feedback",
    role: "status",
    "aria-live": "polite",
  });
  feedback.textContent = submissionCopy;
  let summary = null;

  const updateSummary = () => {
    if (summary) summary.value = summarizeDraft(draft);
  };

  const optionList = el("div", { class: "commercial-decision-options" });
  for (const option of item.options) {
    const selected = !stale && draft.selections.some(
      (selection) => (
        selection.decision_key === item.key
        && selection.option_id === (option.id ?? option.option_id)
      ),
    );
    const classNames = [
      "commercial-decision-option",
      selected ? "selected" : "",
    ].filter(Boolean).join(" ");
    const button = el("button", {
      type: "button",
      class: classNames,
      "data-option-id": option.id ?? option.option_id ?? "",
      "aria-pressed": selected ? "true" : "false",
      disabled: stale || submissionLocked ? "" : null,
    },
    el("span", { class: "commercial-decision-option-head" },
      el("b", {}, option.label_zh || option.label || option.id || "选项")),
    option.description_zh
      ? el("span", { class: "commercial-decision-option-copy" }, option.description_zh)
      : null,
    option.impact_zh
      ? el("span", { class: "commercial-decision-option-impact" }, `影响：${option.impact_zh}`)
      : null);
    if (!submissionLocked) {
      button.addEventListener("click", () => {
        draft = selectOption(draft, item.key, option);
        saveDraft(storage, draft);
        if (typeof onDraftChange === "function") onDraftChange(draft);
        const optionId = String(option.id ?? option.option_id ?? "");
        const panelRoot = document.getElementById(panelId);
        const replacement = [...(panelRoot?.querySelectorAll(".commercial-decision-option") || [])]
          .find((node) => node.dataset.optionId === optionId);
        if (replacement) replacement.focus();
      });
    }
    optionList.append(button);
  }

  const draftRef = { draft };
  const handleDraftChange = (next) => {
    draft = next;
    draftRef.draft = next;
    if (typeof onDraftChange === "function") onDraftChange(next);
  };
  const gapPlanBlock = renderGapPlan({
    gapPlan: decision?.gap_plan,
    draftRef,
    storage,
    onDraftChange: handleDraftChange,
    stale,
    locked: submissionLocked,
  });
  draft = draftRef.draft;

  const body = el("div", { class: "commercial-decision-body" },
    el("b", {}, `【需要你决定】${item.title}`),
    decision?.context_zh
      ? el("div", { class: "commercial-decision-context" }, decision.context_zh)
      : null,
    el("div", {
      class: "commercial-decision-prompt",
      style: "white-space:pre-line",
    }, decision?.prompt_zh || "请在本页确认后进入下一步。"),
    gapPlanBlock,
    optionList,
    decision?.examples_zh
      ? el("div", { class: "commercial-decision-example" }, `回复示例：${decision.examples_zh}`)
      : null);

  if (stale) {
    body.append(el("div", { class: "intent-basket-stale" },
      el("b", {}, "待确认内容已更新"),
      el("div", {}, inspection.status === "corrupt"
        ? "之前保存的选择无法读取，旧草稿未应用。"
        : "之前保存的选择与当前版本不一致，旧草稿未应用。"),
      el("button", {
        type: "button",
        class: "commercial-intent-submit",
        disabled: "",
      }, primarySubmitLabel(stage)),
      el("button", {
        type: "button",
        onclick: () => {
          clearDraft(storage, { projectId, stage });
          if (typeof onDraftChange === "function") onDraftChange(null);
        },
      }, "清空并重选")));
  } else {
    summary = el("textarea", {
      class: "commercial-intent-summary",
      readonly: "",
      rows: "8",
      "aria-label": "待确认摘要（退路）",
    });
    const note = el("textarea", {
      class: "commercial-intent-note",
      rows: "3",
      placeholder: `选填意见。不填也可以直接${primarySubmitLabel(stage)}。`,
      "aria-label": "选填意见",
      disabled: submissionLocked ? "" : null,
      oninput: (event) => {
        draft = setDraftNote(draft, event.currentTarget.value);
        saveDraft(storage, draft);
        updateSummary();
      },
    });
    note.value = draft.note;
    updateSummary();
    const copyButton = el("button", {
      type: "button",
      class: "commercial-intent-copy",
      onclick: async () => {
        try {
          if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
          await navigator.clipboard.writeText(summary.value);
          feedback.textContent = "摘要已复制。请留在本页。";
        } catch {
          summary.focus();
          summary.select();
          feedback.textContent = "复制失败，请手动选择上方摘要。";
        }
      },
    }, "复制聊天摘要");
    const ready = gapPlanReady(draft, decision?.gap_plan);
    const submitButton = el("button", {
      type: "button",
      class: "commercial-intent-submit",
      disabled: ready && !submissionLocked ? null : "",
      onclick: async () => {
        if (!gapPlanReady(draft, decision?.gap_plan)) {
          feedback.textContent = "请先选择本步处理方式；如有素材缺口，还要逐项选择补齐方式。";
          return;
        }
        submitButton.disabled = true;
        try {
          if (!runnerBound) {
            feedback.textContent = RUNNER_GONE_ZH;
            return;
          }
          const intent = await buildDecisionIntent({
            projectId,
            stage,
            draft,
            summary: summary.value,
          });
          const result = await submitDecisionIntent({ intent });
          if (result.ok) {
            const successCopy = submittedFeedback(stage);
            locallySubmitted.set(submissionKey, successCopy);
            feedback.textContent = successCopy;
            submitButton.textContent = "已提交，等待处理";
            if (typeof onDraftChange === "function") onDraftChange(draft);
          } else {
            feedback.textContent = "提交失败，请留在本页重试。";
          }
        } catch {
          feedback.textContent = "提交失败，请留在本页重试。";
        } finally {
          submitButton.disabled = locallySubmitted.has(submissionKey);
        }
      },
    }, submissionLocked
      ? "已提交，等待处理"
      : ready ? primarySubmitLabel(stage) : "请先完成本步选择");
    body.append(el("div", { class: "commercial-intent-basket" },
      el("div", { class: "commercial-intent-basket-head" },
        el("b", {}, "本步确认"),
        el("span", {}, projectTitle || projectId)),
      summary,
      note,
      el("div", { class: "commercial-intent-actions" }, submitButton, copyButton),
      feedback));
  }

  body.append(el("div", { class: "commercial-chat-only" },
    stale
      ? "选择已过期，请先清空并重选。"
      : `点「${primarySubmitLabel(stage)}」后请留在本页。意见可不填。`));
  return el("div", { id: panelId, class: "notice commercial-notice" },
    el("span", {
      class: "commercial-intent-icon",
      style: "font-size:calc(16px * var(--fs-scale))",
      "aria-hidden": "true",
    }, "◈"),
    body);
}
