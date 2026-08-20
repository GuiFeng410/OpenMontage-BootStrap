import { ThemeToggle } from "../library/ThemeToggle";
import { QuitButton } from "../library/QuitButton";
import { ExportButton } from "./ExportButton";
import { InterruptButton } from "./InterruptButton";
import { fmtAgo, fmtMoney, fmtMoneyCny, libraryHref } from "./format";
import { isCommercial, isProduceBusy } from "./model";
import type { BoardState } from "./types";

type Props = {
  state: BoardState;
  editOpen?: boolean;
  onToggleEdit?: () => void;
};

export function HeaderSlate({ state, editOpen = false, onToggleEdit }: Props) {
  const commercial = isCommercial(state);
  const chips = commercialChips(state);
  return (
    <header className="slate">
      <div className="clapper" />
      <div>
        <a className="wordmark" href={libraryHref()} style={{ textDecoration: "none" }}>
          Backlot
        </a>
        <h1>
          {commercial ? (
            <a href={libraryHref()} style={{ color: "inherit", textDecoration: "none" }} title="返回项目库切换其它项目">
              {state.title}
            </a>
          ) : (
            state.title
          )}
        </h1>
        {commercial ? (
          <div className="project-switch-hint">
            <a href={libraryHref()} style={{ color: "var(--text-3)", fontSize: "calc(10.5px * var(--fs-scale))" }}>
              ← 所有项目
            </a>
          </div>
        ) : null}
      </div>
      {chips}
      <div className="spacer" />
      {onToggleEdit ? (
        <EditTabButton state={state} editOpen={editOpen} onToggleEdit={onToggleEdit} />
      ) : null}
      <ExportButton state={state} />
      <InterruptButton state={state} />
      <QuitButton produceBusy={isProduceBusy(state)} />
      <ThemeToggle />
      <LiveBadge state={state} />
      <CostBlock state={state} />
    </header>
  );
}

function commercialChips(state: BoardState) {
  if (!isCommercial(state)) {
    return (
      <>
        <span className="chip">{`${state.pipeline.pipeline_type} pipeline`}</span>
        {state.commercial?.brief_summary?.style_label_zh ? (
          <span className="chip">{state.commercial.brief_summary.style_label_zh}</span>
        ) : null}
      </>
    );
  }
  const b = state.commercial?.brief_summary || {};
  return (
    <>
      <span className="chip">商品片 · bootstrap-commercial</span>
      {b.duration_seconds ? (
        <span className="chip">{`${b.duration_seconds}s · ${b.review_mode_zh || ""}`}</span>
      ) : b.review_mode_zh ? (
        <span className="chip">{b.review_mode_zh}</span>
      ) : null}
      {state.commercial?.user_stage_zh ? <span className="chip">{state.commercial.user_stage_zh}</span> : null}
      {b.production_tier ? <span className="chip">{`制作档 ${b.production_tier}`}</span> : null}
      {b.imported_asset_count ? <span className="chip">{`已导入 ${b.imported_asset_count} 个文件`}</span> : null}
      {b.style_label_zh ? <span className="chip">{b.style_label_zh}</span> : null}
    </>
  );
}

function LiveBadge({ state }: Props) {
  const commercial = isCommercial(state);
  const awaiting = state.stages.find((x) => x.status === "awaiting_human");
  const inProgress = state.stages.find((x) => x.status === "in_progress");
  const stalled = state.stages.find((x) => x.stalled);
  if (awaiting) {
    return (
      <span className="live">
        <span className="dot" />
        {commercial ? "◈ 需要你决定" : "◈ AWAITING YOU"}
      </span>
    );
  }
  if (stalled) {
    return (
      <span className="live" style={{ color: "var(--red)" }}>
        <span className="dot" style={{ background: "var(--red)", animation: "none" }} />
        {commercial ? "⚠ 可能卡住" : "⚠ STALLED?"}
      </span>
    );
  }
  if (state.live || inProgress) {
    return (
      <span className="live">
        <span className="dot" />
        {commercial ? "进行中" : "LIVE"}
      </span>
    );
  }
  return (
    <span className="live idle">
      <span className="dot" />
      {commercial
        ? `空闲${state.last_activity ? " · " + fmtAgo(state.last_activity) : ""}`
        : `IDLE${state.last_activity ? " · " + fmtAgo(state.last_activity) : ""}`}
    </span>
  );
}

function CostBlock({ state }: Props) {
  if (isCommercial(state) && state.commercial?.cost_cny?.spent_cny != null) {
    const cc = state.commercial.cost_cny;
    const spent = cc.spent_cny;
    const budget = cc.budget_cny;
    const hasBudget = budget != null;
    const pct = hasBudget && budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;
    return (
      <div className="cost">
        <div className="nums">
          <b>{fmtMoneyCny(spent)}</b>
          {hasBudget ? <span>{` / ${fmtMoneyCny(budget)}`}</span> : null}
        </div>
        {hasBudget ? (
          <div className="bar">
            <i className={pct > 90 ? "crit" : pct > 75 ? "warn" : ""} style={{ width: `${pct}%` }} />
          </div>
        ) : null}
        <div className="label">本任务 API（非售价）</div>
      </div>
    );
  }
  if (!state.cost) return null;
  const spent = state.cost.total_spent_usd ?? 0;
  const budget = spent + (state.cost.budget_remaining_usd ?? 0);
  const hasBudget = state.cost.budget_remaining_usd != null;
  const pct = hasBudget && budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;
  return (
    <div className="cost">
      <div className="nums">
        <b>{fmtMoney(spent)}</b>
        {hasBudget ? <span>{` / ${fmtMoney(budget)}`}</span> : null}
      </div>
      {hasBudget ? (
        <div className="bar">
          <i className={pct > 90 ? "crit" : pct > 75 ? "warn" : ""} style={{ width: `${pct}%` }} />
        </div>
      ) : null}
      <div className="label">generation spend</div>
    </div>
  );
}

function EditTabButton({
  state,
  editOpen,
  onToggleEdit,
}: {
  state: BoardState;
  editOpen: boolean;
  onToggleEdit: () => void;
}) {
  const gate = state.editing_gate || state.commercial?.editing_gate;
  const locked = gate?.enabled === false;
  return (
    <button
      type="button"
      className={`edit-tab-btn${editOpen ? " on" : ""}${locked ? " locked" : ""}`}
      title={locked ? gate?.friendly_zh : "剪辑标签：对成片做轻量标记（Agent 确认后出片）"}
      onClick={onToggleEdit}
    >
      ✂ 剪辑
    </button>
  );
}

