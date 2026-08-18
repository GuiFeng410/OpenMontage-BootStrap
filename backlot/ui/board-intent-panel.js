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
      disabled: stale || option.disabled ? "" : null,
    },
    el("span", { class: "commercial-decision-option-head" },
      el("b", {}, option.label_zh)),
    option.description_zh
      ? el("span", { class: "commercial-decision-option-copy" }, option.description_zh)
      : null);
    if (!stale && !option.disabled) {
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
    block.append(el("div", { class: "gap-plan-enough" }, "图已够，确认即可进入下一步。"));
    return block;
  }
  block.append(el("div", { class: "gap-plan-label" }, "缺口四选（每段一项）"));
  const reusePaths = Array.isArray(gapPlan.reuse_paths) ? gapPlan.reuse_paths : [];
  const models = Array.isArray(gapPlan.image_models) ? gapPlan.image_models : [];
  for (const gap of gaps) {
    const beatId = gap.beat_id;
    const choice = selectedOptionId(draftRef.draft, `gap::${beatId}`);
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
    }));
    if (choice === "i2i" && gapPlan.image_key_present) {
      card.append(el("div", { class: "gap-plan-sublabel" }, "生图模型"));
      card.append(renderChoiceRow({
        draftRef,
        storage,
        onDraftChange,
        decisionKey: `gap_model::${beatId}`,
        stale,
        options: models.map((item) => ({
          id: item.id,
          label_zh: item.label_zh || item.id,
          disabled: !item.available,
          description_zh: item.available ? "" : "未填入 Key",
        })),
      }));
    }
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
      }));
    }
    block.append(card);
  }
  return block;
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
  onDraftChange,
}) {
  const item = currentDecision(decision, stage);
  const revision = revisionFor({ projectId, stage, decision });
  const identity = { projectId, stage, revision };
  const inspection = inspectStoredDraft(storage, identity);
  let draft = inspection.draft || createDraft(identity);
  const stale = ["stale", "corrupt"].includes(inspection.status);
  const panelId = `commercial-intent-panel:${projectId}:${stage}`;
  const feedback = el("div", {
    class: "commercial-intent-feedback",
    role: "status",
    "aria-live": "polite",
  });
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
      disabled: stale ? "" : null,
    },
    el("span", { class: "commercial-decision-option-head" },
      el("b", {}, option.label_zh || option.label || option.id || "选项")),
    option.description_zh
      ? el("span", { class: "commercial-decision-option-copy" }, option.description_zh)
      : null,
    option.impact_zh
      ? el("span", { class: "commercial-decision-option-impact" }, `影响：${option.impact_zh}`)
      : null);
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
    optionList.append(button);
  }

  const gapPlanBlock = renderGapPlan({
    gapPlan: decision?.gap_plan,
    draftRef: { draft },
    storage,
    onDraftChange,
    stale,
  });

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
      }, "进入下一步"),
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
      placeholder: "选填意见。不填也可以直接进入下一步。",
      "aria-label": "选填意见",
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
      disabled: ready ? null : "",
      onclick: async () => {
        if (!gapPlanReady(draft, decision?.gap_plan)) {
          feedback.textContent = "请为每个缺口选一项；图生图还要选模型。";
          return;
        }
        submitButton.disabled = true;
        try {
          const intent = await buildDecisionIntent({
            projectId,
            stage,
            draft,
            summary: summary.value,
          });
          const result = await submitDecisionIntent({ intent });
          feedback.textContent = result.ok
            ? "已进入下一步，请留在本页等待本机处理。"
            : "提交失败，请留在本页重试。";
        } catch {
          feedback.textContent = "提交失败，请留在本页重试。";
        } finally {
          submitButton.disabled = false;
        }
      },
    }, ready ? "进入下一步" : "请先完成缺口选择");
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
      : "点「进入下一步」后请留在本页。意见可不填。"));
  return el("div", { id: panelId, class: "notice commercial-notice" },
    el("span", {
      class: "commercial-intent-icon",
      style: "font-size:calc(16px * var(--fs-scale))",
      "aria-hidden": "true",
    }, "◈"),
    body);
}
