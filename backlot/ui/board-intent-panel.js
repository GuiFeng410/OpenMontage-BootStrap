import { el } from "./lib.js";
import {
  clearDraft,
  createDraft,
  decisionRevision,
  inspectStoredDraft,
  saveDraft,
  selectOption,
  setDraftNote,
  summarizeDraft,
} from "./board-intent-state.js";
import {
  buildDecisionIntent,
  CONFIRM_PHRASE,
  submitDecisionIntent,
} from "./board-intent-submit.js";

function currentDecision(decision, stage) {
  const options = Array.isArray(decision?.options) ? decision.options : [];
  return {
    key: `${stage}::current`,
    title: decision?.title_zh || decision?.stage_label_zh || stage,
    options,
  };
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
      option.recommended ? "recommended" : "",
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
      el("b", {}, option.label_zh || option.label || option.id || "选项"),
      option.recommended
        ? el("span", { class: "commercial-recommend-badge" }, "推荐")
        : null),
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

  const body = el("div", { class: "commercial-decision-body" },
    el("b", {}, `【需要你决定】${item.title}`),
    decision?.context_zh
      ? el("div", { class: "commercial-decision-context" }, decision.context_zh)
      : null,
    el("div", {
      class: "commercial-decision-prompt",
      style: "white-space:pre-line",
    }, decision?.prompt_zh || "请在聊天中回复以继续。"),
    optionList,
    decision?.recommendation_zh
      ? el("div", { class: "commercial-decision-recommendation" }, `建议：${decision.recommendation_zh}`)
      : null,
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
      }, "提交待确认"),
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
      "aria-label": "待确认聊天摘要",
    });
    const note = el("textarea", {
      class: "commercial-intent-note",
      rows: "3",
      placeholder: "可选备注（例如：保留片尾品牌标识）",
      "aria-label": "待确认备注",
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
          feedback.textContent = "摘要已复制，请回聊天发送。";
        } catch {
          summary.focus();
          summary.select();
          feedback.textContent = "复制失败，请手动选择上方摘要并复制。";
        }
      },
    }, "复制聊天摘要");
    const submitButton = el("button", {
      type: "button",
      class: "commercial-intent-submit",
      onclick: async () => {
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
            ? `已提交。请回聊天发送：${CONFIRM_PHRASE}`
            : "提交失败，请复制上方摘要并回聊天发送。";
        } catch {
          feedback.textContent = "提交失败，请复制上方摘要并回聊天发送。";
        } finally {
          submitButton.disabled = false;
        }
      },
    }, "提交待确认");
    body.append(el("div", { class: "commercial-intent-basket" },
      el("div", { class: "commercial-intent-basket-head" },
        el("b", {}, "待确认篮子"),
        el("span", {}, projectTitle || projectId)),
      summary,
      note,
      el("div", { class: "commercial-intent-actions" }, copyButton, submitButton),
      feedback));
  }

  body.append(el("div", { class: "commercial-chat-only" },
    stale
      ? "选择已过期，请先清空并重选。"
      : "面板选择尚未正式执行；复制摘要后回聊天发送“确认面板选择”。"));
  return el("div", { id: panelId, class: "notice commercial-notice" },
    el("span", {
      class: "commercial-intent-icon",
      style: "font-size:calc(16px * var(--fs-scale))",
      "aria-hidden": "true",
    }, "◈"),
    body);
}
