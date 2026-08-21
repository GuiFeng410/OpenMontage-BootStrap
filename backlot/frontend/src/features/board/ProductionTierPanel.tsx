import { useEffect, useState } from "react";
import { friendlyFromPayload, getJSON } from "../library/api";
import { isCommercial } from "./model";
import {
  AI_MAX,
  AI_MIN,
  AI_PRESETS,
  AI_STEP,
  TIERS,
  blockMessage,
  firstAvailableModelId,
  initialAiPct,
  lockedTierId,
  videoModels,
  type KeyFlags,
} from "./productionTier";
import type { BoardState } from "./types";

type Props = {
  state: BoardState;
  onRefresh: () => void;
};

export function ProductionTierPanel({ state, onRefresh }: Props) {
  const brief = state.commercial?.brief_summary || {};
  const lockedLabel = brief.production_tier;
  const locked = lockedTierId(lockedLabel);
  const [keyFlags, setKeyFlags] = useState<KeyFlags | null>(null);
  const [selectedTier, setSelectedTier] = useState(locked || "light");
  const [selectedAiPct, setSelectedAiPct] = useState(() =>
    initialAiPct(brief.ai_share_pct, brief.motion_mix),
  );
  const [selectedModelId, setSelectedModelId] = useState(String(brief.video_model || "").trim());
  const [capOpen, setCapOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState("");

  useEffect(() => {
    setKeyFlags(null);
    setSelectedTier(lockedTierId(brief.production_tier) || "light");
    setSelectedAiPct(initialAiPct(brief.ai_share_pct, brief.motion_mix));
    setSelectedModelId(String(brief.video_model || "").trim());
    setCapOpen(false);
    setStatusText("");
  }, [state.project_id]);

  useEffect(() => {
    if (locked && selectedTier !== locked && !busy) setSelectedTier(locked);
  }, [locked, selectedTier, busy]);

  useEffect(() => {
    if (keyFlags) return;
    let cancelled = false;
    getJSON<KeyFlags>("/api/health")
      .then((flags) => {
        if (cancelled) return;
        const next = flags || {};
        setKeyFlags(next);
        setSelectedModelId((curr) => curr || firstAvailableModelId(next));
      })
      .catch(() => {
        if (cancelled) return;
        setKeyFlags({ video_key_present: false, stock_key_present: false });
      });
    return () => {
      cancelled = true;
    };
  }, [keyFlags, state.project_id]);

  if (!isCommercial(state)) return null;

  const flagsReady = keyFlags !== null;
  const blocked = flagsReady ? blockMessage(selectedTier, keyFlags, selectedModelId) : "";
  const feedback = blocked && !statusText ? blocked : statusText;
  const startDisabled = busy || (selectedTier === "heavy" && !flagsReady) || Boolean(blocked);

  const applyFlags = (flags: KeyFlags) => {
    setKeyFlags(flags || keyFlags || {});
    setSelectedModelId((curr) => curr || firstAvailableModelId(flags || keyFlags));
  };

  const panel = (
    <div className="notice commercial-tier-panel">
      <div className="tier-panel-head">
        <b>制作档位</b>
      </div>
      <div className="tier-picker-options">
        {TIERS.map((tier) => {
          const selected = selectedTier === tier.id;
          return (
            <button
              key={tier.id}
              type="button"
              className={`tier-picker-option${selected ? " selected" : ""}`}
              data-tier={tier.id}
              aria-pressed={selected}
              onClick={() => {
                setSelectedTier(tier.id);
                setStatusText("");
                if (tier.id === "heavy") {
                  setSelectedModelId((curr) => curr || firstAvailableModelId(keyFlags));
                }
              }}
            >
              <b>{tier.label_zh}</b>
              <span>{tier.hint}</span>
            </button>
          );
        })}
      </div>
      {selectedTier === "heavy" ? (
        <div className="tier-heavy-tools">
          <ModelPicker
            keyFlags={keyFlags}
            selectedModelId={selectedModelId}
            capOpen={capOpen}
            onSelect={(id) => {
              setSelectedModelId(id);
              setStatusText("");
            }}
            onToggleCap={setCapOpen}
          />
          <AiMix
            selectedAiPct={selectedAiPct}
            onChange={(pct) => {
              setSelectedAiPct(pct);
              setStatusText("");
            }}
          />
        </div>
      ) : null}
      <div className="tier-panel-actions">
        <button
          type="button"
          className="tier-refresh-btn"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setStatusText("正在刷新…");
            try {
              const response = await fetch("/api/keys/refresh", { method: "POST" });
              const payload = (await response.json()) as KeyFlags;
              applyFlags(payload);
              setStatusText(payload.friendly_zh || "已刷新。");
            } catch {
              setStatusText("刷新失败。请确认本机看板仍在运行，然后重试。");
            } finally {
              setBusy(false);
              onRefresh();
            }
          }}
        >
          已填入 Key，刷新可用性
        </button>
        <button
          type="button"
          className="tier-start-btn"
          disabled={startDisabled}
          title={blocked || "锁定制作档。本页不会直接调付费接口。"}
          onClick={async () => {
            const message = blockMessage(selectedTier, keyFlags, selectedModelId);
            if (message) {
              setStatusText(message);
              window.alert(message);
              return;
            }
            setBusy(true);
            setStatusText("正在锁定制作档…");
            try {
              const body: Record<string, unknown> = { production_tier: selectedTier };
              if (selectedTier === "heavy") {
                body.ai_share_pct = selectedAiPct;
                body.video_model = selectedModelId;
              }
              const response = await fetch(
                `/api/project/${encodeURIComponent(state.project_id)}/start-production`,
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(body),
                },
              );
              const payload = await response.json().catch(() => ({}));
              if (!response.ok) {
                const text = friendlyFromPayload(payload, "无法开始出片。");
                setStatusText(text);
                window.alert(text);
                return;
              }
              applyFlags(payload as KeyFlags);
              setStatusText(
                typeof (payload as KeyFlags).friendly_zh === "string"
                  ? (payload as KeyFlags).friendly_zh || "已锁定制作档。"
                  : "已锁定制作档。",
              );
            } catch {
              setStatusText("开始失败。请留在本页重试。");
            } finally {
              setBusy(false);
              onRefresh();
            }
          }}
        >
          确认开始出片
        </button>
      </div>
      {feedback ? (
        <div className="tier-panel-feedback" role="status">
          {feedback}
        </div>
      ) : null}
    </div>
  );

  if (lockedLabel) {
    return (
      <details className="commercial-fold commercial-tier-fold">
        <summary>{`制作档位（已锁定：${lockedLabel}）`}</summary>
        {panel}
      </details>
    );
  }
  return panel;
}

function ModelPicker({
  keyFlags,
  selectedModelId,
  capOpen,
  onSelect,
  onToggleCap,
}: {
  keyFlags: KeyFlags | null;
  selectedModelId: string;
  capOpen: boolean;
  onSelect: (id: string) => void;
  onToggleCap: (open: boolean) => void;
}) {
  const models = videoModels(keyFlags);
  const selected = models.find((item) => item.id === selectedModelId) || models.find((item) => item.available);
  return (
    <div className="tier-model-picker">
      <div className="tier-ai-label">视频模型</div>
      <div className="tier-model-options">
        {models.map((item) => {
          const isSelected = selectedModelId === item.id;
          const canSelect = Boolean(item.available);
          return (
            <button
              key={item.id}
              type="button"
              className={`tier-model-option${isSelected ? " selected" : ""}${canSelect ? "" : " disabled"}`}
              disabled={!canSelect}
              aria-pressed={isSelected}
              onClick={() => {
                if (canSelect) onSelect(item.id);
              }}
            >
              {item.board_generate === false ? `${item.label_zh}（看板暂不能开烧）` : item.label_zh}
            </button>
          );
        })}
        {models.some((item) => item.available) ? null : (
          <div className="tier-model-empty">
            没有看板能开烧的模型。请写入 Agnes Key 后刷新。混元 / Pixverse 暂不能在看板开烧。
          </div>
        )}
      </div>
      <details
        className="tier-model-cap"
        open={capOpen}
        onToggle={(event) => onToggleCap((event.currentTarget as HTMLDetailsElement).open)}
      >
        <summary>能力说明</summary>
        <div>
          {selected?.capability_zh || "请先选择已填入 Key 的模型。"}
          {" 具体生成情况视模型能力而定。"}
        </div>
      </details>
    </div>
  );
}

function AiMix({
  selectedAiPct,
  onChange,
}: {
  selectedAiPct: number;
  onChange: (pct: number) => void;
}) {
  return (
    <div className="tier-ai-mix">
      <div className="tier-ai-label">AI 占比</div>
      <div className="tier-ai-row">
        <button
          type="button"
          className="tier-ai-step"
          aria-label="降低 AI 占比"
          onClick={() => onChange(Math.max(AI_MIN, selectedAiPct - AI_STEP))}
        >
          ←
        </button>
        <div className="tier-ai-value">{`AI ${selectedAiPct}%`}</div>
        <button
          type="button"
          className="tier-ai-step"
          aria-label="提高 AI 占比"
          onClick={() => onChange(Math.min(AI_MAX, selectedAiPct + AI_STEP))}
        >
          →
        </button>
      </div>
      <div className="tier-ai-presets">
        {AI_PRESETS.map((pct) => (
          <button
            key={pct}
            type="button"
            className={`tier-ai-preset${selectedAiPct === pct ? " selected" : ""}`}
            onClick={() => onChange(pct)}
          >
            {pct === 100 ? `${pct}% 默认` : `${pct}%`}
          </button>
        ))}
      </div>
      <div className="tier-ai-hint">{`运镜约 ${100 - selectedAiPct}% · 具体生成情况视模型能力而定`}</div>
    </div>
  );
}
