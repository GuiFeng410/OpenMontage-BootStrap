import { useCallback, useEffect, useState } from "react";
import {
  getJSON,
  LABELS,
  occupantFromHealth,
  subscribe,
  type Health,
  type Occupant,
  type ProjectSummary,
} from "./api";
import { OccupantBar } from "./OccupantBar";
import { OnboardingForm } from "./OnboardingForm";
import { ProjectCard } from "./ProjectCard";
import { QuitButton } from "./QuitButton";
import { ThemeToggle } from "./ThemeToggle";

export function LibraryPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [health, setHealth] = useState<Health>({ projects_dir: "未提供" });
  const [occupant, setOccupant] = useState<Occupant>({ project_id: "", title: "" });

  const load = useCallback(async () => {
    const [nextProjects, nextHealth] = await Promise.all([
      getJSON<ProjectSummary[]>("/api/projects"),
      getJSON<Health>("/api/health").catch(() => ({ projects_dir: "未提供" })),
    ]);
    setProjects(nextProjects);
    setHealth(nextHealth || { projects_dir: "未提供" });
    setOccupant(occupantFromHealth(nextHealth));
  }, []);

  useEffect(() => {
    void load().catch(console.error);
    if (new URLSearchParams(window.location.search).has("static")) return;
    const sub = subscribe("/api/library/events", () => {
      void load().catch(console.error);
    });
    return () => sub.close();
  }, [load]);

  const liveCount = projects.filter((p) => p.live).length;

  return (
    <div className="wrap" data-backlot-next="library">
      <header className="slate">
        <div className="clapper" />
        <div>
          <span className="wordmark">Backlot</span>
          <h1>项目库</h1>
        </div>
        <span className="chip" id="count">
          {`${projects.length} ${LABELS.projects}`}
        </span>
        <div className="spacer" />
        <QuitButton />
        <ThemeToggle />
        <span className={`live${liveCount === 0 ? " idle" : ""}`} id="liveBadge">
          <span className="dot" />
          <span id="liveText">
            {liveCount ? `${liveCount} ${LABELS.LIVE}` : LABELS.IDLE}
          </span>
        </span>
      </header>
      <OccupantBar occupant={occupant} onReleased={load} />
      <OnboardingForm health={health} projectCount={projects.length} occupant={occupant} />
      <div className="lib-grid" id="grid">
        {projects.map((p) => (
          <ProjectCard key={p.project_id} project={p} occupant={occupant} />
        ))}
      </div>
      <p className="hint" id="empty" style={{ display: projects.length ? "none" : "block" }}>
        暂无项目。填写上方主题并点「开始创建项目」。环境未就绪时请先回聊天完成安装。
      </p>
    </div>
  );
}
