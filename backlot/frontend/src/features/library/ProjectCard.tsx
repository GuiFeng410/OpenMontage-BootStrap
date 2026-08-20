import {
  boardSuffix,
  fmtAgo,
  friendlyFromPayload,
  LABELS,
  mediaURL,
  thumbURL,
  type Occupant,
  type ProjectSummary,
} from "./api";

function MiniRail({ states }: { states: { name: string; status: string }[] }) {
  return (
    <div className="mini-rail">
      {states.map((s) => {
        const cls =
          s.status === "completed"
            ? "d"
            : s.status === "in_progress"
              ? "a"
              : s.status === "awaiting_human"
                ? "w"
                : "";
        return <i key={s.name} className={cls} title={`${s.name}: ${s.status}`} />;
      })}
    </div>
  );
}

export function ProjectCard({
  project: p,
  occupant,
}: {
  project: ProjectSummary;
  occupant: Occupant;
}) {
  const completed = Boolean(p.completed || p.lifecycle_status === "completed");
  const stopLine = p.user_stage_zh
    ? completed
      ? "已结束并导出"
      : `当前停点：${p.user_stage_zh}`
    : completed
      ? "已结束并导出"
      : `编号 ${p.project_id}`;
  const href = `/p/${p.project_id}${boardSuffix()}`;

  async function onClick() {
    if (completed) {
      window.location.href = href;
      return;
    }
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
      if (!response.ok) {
        window.alert(friendlyFromPayload(data, "无法继续这个项目"));
        return;
      }
      window.location.href = `${data.board_path || href}`;
    } catch {
      window.alert("无法继续这个项目。请回聊天让 Agent 停 runner 后再试。");
    }
  }

  return (
    <div
      className={`lib-card${p.live ? " live-card" : ""}`}
      style={{ textDecoration: "none", color: "inherit", cursor: "pointer" }}
      onClick={() => void onClick()}
    >
      <div className="lib-poster">
        {p.poster ? (
          <img src={thumbURL(p.project_id, p.poster, 640)} loading="lazy" alt="" />
        ) : (
          <span className="lp-txt">{LABELS["NO MEDIA YET"]}</span>
        )}
        {p.live && p.active_stage ? (
          <span className="lp-live">
            <span className="dot" />
            {p.awaiting_human
              ? `◈ ${LABELS["AWAITING YOU"]}`
              : `${LABELS.LIVE} · ${p.active_stage.toUpperCase()}`}
          </span>
        ) : p.awaiting_human ? (
          <span className="lp-live">{`◈ ${LABELS["AWAITING YOU"]}`}</span>
        ) : null}
      </div>
      <div className="lib-body">
        <h3>{p.title || p.project_id}</h3>
        <div className="lb-meta">
          <span className="chip">{p.pipeline_type || LABELS.unknown}</span>
          {p.review_mode_zh ? <span className="chip">{p.review_mode_zh}</span> : null}
          <span className="chip">{stopLine}</span>
          {p.production_tier_zh ? (
            <span className="chip">{`制作档 ${p.production_tier_zh}`}</span>
          ) : null}
          {p.imported_asset_count ? (
            <span className="chip">{`${p.imported_asset_count} 个素材`}</span>
          ) : null}
          {p.scene_count ? (
            <span className="chip">{`${p.scene_count} ${LABELS.scenes}`}</span>
          ) : null}
          {p.render_count ? (
            <span className="chip">{`${p.render_count} ${LABELS.renders}`}</span>
          ) : null}
          <span className="when">{p.last_activity ? fmtAgo(p.last_activity) : "刚刚"}</span>
        </div>
        {p.stage_states?.length ? <MiniRail states={p.stage_states} /> : null}
      </div>
      {completed && p.export_path ? (
        <a
          className="chip"
          href={mediaURL(p.project_id, p.export_path)}
          download="final.mp4"
          style={{ margin: "8px 12px 12px", display: "inline-block" }}
          onClick={(event) => event.stopPropagation()}
        >
          下载成片
        </a>
      ) : null}
    </div>
  );
}
