import { RUNNER_GONE_ZH } from "./model";
import {
  clearDraft,
  createDraft,
  gapPlanReady,
  inspectStoredDraft,
  primarySubmitLabel,
  revisionForDecision,
  saveDraft,
  selectOption,
  selectedOptionId,
  setDraftNote,
  submittedFeedback,
  summarizeDraft,
  type IntentDraft,
} from "./intentState";
import { buildDecisionIntent, submitDecisionIntent } from "./intentSubmit";
import type {
  CommercialDecision,
  DecisionOption,
  GapPlan,
  InteractionIntent,
} from "./types";
import { useMemo, useState } from "react";

const locallySubmitted = new Map<string, string>();

const GAP_ACTIONS: DecisionOption[] = [
  { id: "upload", label_zh: "补传", description_zh: "稍后在素材检查页上传。" },
  { id: "i2i", label_zh: "图生图", description_zh: "锁定生图模型；同意方案后才生成。" },
  { id: "reuse", label_zh: "复用", description_zh: "用已有图片覆盖这一段。" },
  { id: "skip", label_zh: "不补", description_zh: "本段不补图，改为概念表达。" },
];

type Props = {
  projectId: string;
  projectTitle?: string;
  stage: string;
  decision: CommercialDecision;
  interactionIntents?: InteractionIntent[];
  runnerBound?: boolean;
  storage?: Storage;
};

export function DecisionPanel({
  projectId,
  projectTitle,
  stage,
  decision,
  interactionIntents = [],
  runnerBound = true,
  storage = window.sessionStorage,
}: Props) {
  const revision = useMemo(
    () => revisionForDecision({ projectId, stage, decision }),
    [projectId, stage, decision],
  );
  const identity = { projectId, stage, revision };
  const inspection = inspectStoredDraft(storage, identity);
  const [draft, setDraft] = useState<IntentDraft>(
    () => inspection.draft || createDraft(identity),
  );
  const stale = ["stale", "corrupt"].includes(inspection.status);
  const submissionKey = `${projectId}:${stage}`;
  const activeIntent = interactionIntents.find(
    (entry) =>
      entry?.stage === stage &&
      entry?.revision === revision &&
      ["pending", "planned", "approved", "applied"].includes(entry?.status || ""),
  );
  const submissionLocked = Boolean(activeIntent) || locallySubmitted.has(submissionKey);
  const localCopy = locallySubmitted.get(submissionKey) || "";
  const [feedback, setFeedback] = useState(() =>
    activeIntent?.status === "planned"
      ? "选择已汇总，本机正在应用，请留在本页。"
      : activeIntent?.status === "applied"
        ? "选择已应用，正在进入下一步，请留在本页。"
        : localCopy || (submissionLocked ? "选择已提交，等待本机处理，请留在本页。" : ""),
  );
  const itemKey = `${stage}::current`;
  const options = Array.isArray(decision.options) ? decision.options : [];
  const ready = gapPlanReady(draft, decision.gap_plan);
  const summary = summarizeDraft(draft);

  const applyDraft = (next: IntentDraft) => {
    setDraft(next);
    saveDraft(storage, next);
  };

  return (
    <div id={`commercial-intent-panel:${projectId}:${stage}`} className="notice commercial-notice">
      <span className="commercial-intent-icon" style={{ fontSize: "calc(16px * var(--fs-scale))" }} aria-hidden="true">
        ◈
      </span>
      <div className="commercial-decision-body">
        <b>{`【需要你决定】${decision.title_zh || decision.stage_label_zh || stage}`}</b>
        {decision.context_zh ? <div className="commercial-decision-context">{decision.context_zh}</div> : null}
        <div className="commercial-decision-prompt" style={{ whiteSpace: "pre-line" }}>
          {decision.prompt_zh || "请在本页确认后进入下一步。"}
        </div>
        <GapPlanBlock
          gapPlan={decision.gap_plan}
          draft={draft}
          stale={stale}
          locked={submissionLocked}
          onChange={applyDraft}
        />
        <div className="commercial-decision-options">
          {options.map((option) => {
            const optionId = String(option.id ?? option.option_id ?? "");
            const selected = !stale && draft.selections.some(
              (selection) => selection.decision_key === itemKey && selection.option_id === optionId,
            );
            return (
              <button
                key={optionId}
                type="button"
                className={`commercial-decision-option${selected ? " selected" : ""}`}
                data-option-id={optionId}
                aria-pressed={selected}
                disabled={stale || submissionLocked}
                onClick={() => {
                  if (submissionLocked) return;
                  applyDraft(selectOption(draft, itemKey, option));
                }}
              >
                <span className="commercial-decision-option-head">
                  <b>{option.label_zh || option.label || option.id || "选项"}</b>
                </span>
                {option.description_zh ? (
                  <span className="commercial-decision-option-copy">{option.description_zh}</span>
                ) : null}
                {option.impact_zh ? (
                  <span className="commercial-decision-option-impact">{`影响：${option.impact_zh}`}</span>
                ) : null}
              </button>
            );
          })}
        </div>
        {decision.examples_zh ? (
          <div className="commercial-decision-example">{`回复示例：${decision.examples_zh}`}</div>
        ) : null}
        {stale ? (
          <div className="intent-basket-stale">
            <b>待确认内容已更新</b>
            <div>
              {inspection.status === "corrupt"
                ? "之前保存的选择无法读取，旧草稿未应用。"
                : "之前保存的选择与当前版本不一致，旧草稿未应用。"}
            </div>
            <button type="button" className="commercial-intent-submit" disabled>
              {primarySubmitLabel(stage)}
            </button>
            <button
              type="button"
              onClick={() => {
                clearDraft(storage, { projectId, stage });
                setDraft(createDraft(identity));
              }}
            >
              清空并重选
            </button>
          </div>
        ) : (
          <div className="commercial-intent-basket">
            <div className="commercial-intent-basket-head">
              <b>本步确认</b>
              <span>{projectTitle || projectId}</span>
            </div>
            <textarea
              className="commercial-intent-summary"
              readOnly
              rows={8}
              aria-label="待确认摘要（退路）"
              value={summary}
            />
            <textarea
              className="commercial-intent-note"
              rows={3}
              placeholder={`选填意见。不填也可以直接${primarySubmitLabel(stage)}。`}
              aria-label="选填意见"
              disabled={submissionLocked}
              value={draft.note}
              onChange={(event) => applyDraft(setDraftNote(draft, event.currentTarget.value))}
            />
            <div className="commercial-intent-actions">
              <button
                type="button"
                className="commercial-intent-submit"
                disabled={!ready || submissionLocked}
                onClick={async (event) => {
                  const button = event.currentTarget;
                  if (!gapPlanReady(draft, decision.gap_plan)) {
                    setFeedback("请先选择本步处理方式；如有素材缺口，还要逐项选择补齐方式。");
                    return;
                  }
                  button.disabled = true;
                  try {
                    if (!runnerBound) {
                      setFeedback(RUNNER_GONE_ZH);
                      return;
                    }
                    const intent = await buildDecisionIntent({
                      projectId,
                      stage,
                      draft,
                      summary,
                    });
                    const result = await submitDecisionIntent({ intent });
                    if (result.ok) {
                      const successCopy = submittedFeedback(stage);
                      locallySubmitted.set(submissionKey, successCopy);
                      setFeedback(successCopy);
                      button.textContent = "已提交，等待处理";
                    } else {
                      setFeedback("提交失败，请留在本页重试。");
                    }
                  } catch {
                    setFeedback("提交失败，请留在本页重试。");
                  } finally {
                    button.disabled = locallySubmitted.has(submissionKey);
                  }
                }}
              >
                {submissionLocked ? "已提交，等待处理" : ready ? primarySubmitLabel(stage) : "请先完成本步选择"}
              </button>
              <button
                type="button"
                className="commercial-intent-copy"
                onClick={async () => {
                  try {
                    if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
                    await navigator.clipboard.writeText(summary);
                    setFeedback("摘要已复制。请留在本页。");
                  } catch {
                    setFeedback("复制失败，请手动选择上方摘要。");
                  }
                }}
              >
                复制聊天摘要
              </button>
            </div>
            <div className="commercial-intent-feedback" role="status" aria-live="polite">
              {feedback}
            </div>
          </div>
        )}
        <div className="commercial-chat-only">
          {stale
            ? "选择已过期，请先清空并重选。"
            : `点「${primarySubmitLabel(stage)}」后请留在本页。意见可不填。`}
        </div>
      </div>
    </div>
  );
}

function GapPlanBlock({
  gapPlan,
  draft,
  stale,
  locked,
  onChange,
}: {
  gapPlan?: GapPlan;
  draft: IntentDraft;
  stale: boolean;
  locked: boolean;
  onChange: (draft: IntentDraft) => void;
}) {
  if (!gapPlan || typeof gapPlan !== "object") return null;
  const covered = Array.isArray(gapPlan.covered) ? gapPlan.covered : [];
  const gaps = Array.isArray(gapPlan.gaps) ? gapPlan.gaps : [];
  const reusePaths = Array.isArray(gapPlan.reuse_paths) ? gapPlan.reuse_paths : [];
  const models = Array.isArray(gapPlan.image_models) ? gapPlan.image_models : [];
  const anyI2i = gaps.some((gap) => selectedOptionId(draft, `gap::${gap.beat_id}`) === "i2i");

  return (
    <div className="gap-plan">
      {covered.length ? <div className="gap-plan-label">已有画面</div> : null}
      {covered.map((item) => (
        <div className="gap-covered-row" key={item.beat_id || item.path}>
          <b>{item.beat_id || ""}</b>
          <span>{`${item.need_zh || ""} · ${item.path || ""}`}</span>
        </div>
      ))}
      {!gaps.length ? <div className="gap-plan-enough">图已够，确认方案后进入素材检查。</div> : null}
      {gaps.length ? <div className="gap-plan-label">缺口四选（每段一项）</div> : null}
      {gaps.map((gap) => {
        const beatId = gap.beat_id || "";
        const choice = selectedOptionId(draft, `gap::${beatId}`);
        return (
          <div className="gap-beat-card" key={beatId}>
            <div className="gap-beat-head">
              <b>{gap.beat_id || ""}</b>
              <span>{gap.need_zh || "所需画面"}</span>
            </div>
            <ChoiceRow
              draft={draft}
              decisionKey={`gap::${beatId}`}
              stale={stale}
              locked={locked}
              options={GAP_ACTIONS.map((action) => ({
                ...action,
                disabled:
                  (action.id === "i2i" && !gapPlan.image_key_present) ||
                  (action.id === "reuse" && !reusePaths.length),
                description_zh:
                  action.id === "i2i" && !gapPlan.image_key_present
                    ? "未检测到生图 Key，不可执行。"
                    : action.id === "reuse" && !reusePaths.length
                      ? "还没有可复用的已有图。"
                      : action.description_zh,
              }))}
              onChange={onChange}
            />
            {choice === "reuse" && reusePaths.length ? (
              <>
                <div className="gap-plan-sublabel">复用哪张</div>
                <ChoiceRow
                  draft={draft}
                  decisionKey={`gap_reuse::${beatId}`}
                  stale={stale}
                  locked={locked}
                  options={reusePaths.map((path) => ({ id: path, label_zh: path }))}
                  onChange={onChange}
                />
              </>
            ) : null}
          </div>
        );
      })}
      {anyI2i && gapPlan.image_key_present ? (
        <div className="gap-image-model">
          <div className="gap-plan-label">生图模型（全片共用）</div>
          <ChoiceRow
            draft={draft}
            decisionKey="image_model::project"
            stale={stale}
            locked={locked}
            options={models.map((item) => ({
              id: item.id,
              label_zh: item.label_zh || item.id,
              disabled: !item.available,
              description_zh: item.available ? "" : "未填入 Key",
            }))}
            onChange={onChange}
          />
        </div>
      ) : null}
    </div>
  );
}

function ChoiceRow({
  draft,
  decisionKey,
  options,
  stale,
  locked,
  onChange,
}: {
  draft: IntentDraft;
  decisionKey: string;
  options: DecisionOption[];
  stale: boolean;
  locked: boolean;
  onChange: (draft: IntentDraft) => void;
}) {
  return (
    <div className="gap-choice-row">
      {options.map((option) => {
        const optionId = String(option.id ?? option.option_id ?? "");
        const selected = !stale && selectedOptionId(draft, decisionKey) === optionId;
        return (
          <button
            key={optionId}
            type="button"
            className={[
              "commercial-decision-option",
              selected ? "selected" : "",
              option.disabled ? "disabled" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            data-option-id={optionId}
            aria-pressed={selected}
            disabled={stale || locked || option.disabled}
            onClick={() => {
              if (stale || locked || option.disabled) return;
              onChange(selectOption(draft, decisionKey, option));
            }}
          >
            <span className="commercial-decision-option-head">
              <b>{option.label_zh}</b>
            </span>
            {option.description_zh ? (
              <span className="commercial-decision-option-copy">{option.description_zh}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
