import { useMemo, useRef, useState } from "react";
import {
  boardSuffix,
  friendlyFromPayload,
  occupantFromHealth,
  type Health,
  type Occupant,
} from "./api";
import {
  buildCreateProductVideoPrompt,
  copyCreatePrompt,
  formatServiceInfo,
  getReviewModeRoute,
  listReviewModes,
  readStoredReviewMode,
  writeStoredReviewMode,
  type ReviewModeId,
} from "./onboarding";

export function OnboardingForm({
  health,
  projectCount,
  occupant,
}: {
  health: Health;
  projectCount: number;
  occupant: Occupant;
}) {
  const [mode, setMode] = useState<ReviewModeId>(() =>
    readStoredReviewMode(window.sessionStorage),
  );
  const [title, setTitle] = useState("");
  const [duration, setDuration] = useState("");
  const [assetLocation, setAssetLocation] = useState("");
  const [feedback, setFeedback] = useState("填写主题后点开始创建，进入对应确认步骤。");
  const [creating, setCreating] = useState(false);
  const [fileTick, setFileTick] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);

  const route = getReviewModeRoute(mode);
  const prompt = buildCreateProductVideoPrompt(mode);
  const [serviceLine, countLine, rootLine] = formatServiceInfo({
    host: window.location.host,
    projectsDir: health.projects_dir,
    projectCount,
  });
  const files = useMemo(() => {
    void fileTick;
    return [...(fileRef.current?.files || []), ...(folderRef.current?.files || [])];
  }, [fileTick]);

  function selectMode(next: ReviewModeId) {
    setMode(writeStoredReviewMode(window.sessionStorage, next));
  }

  async function onCreate() {
    const trimmed = title.trim();
    if (!trimmed) {
      setFeedback("请先填写商品主题");
      return;
    }
    const occ = occupantFromHealth(health);
    if (occ.project_id) {
      setFeedback(`本机正在做「${occ.title}」。请先点「中断并做别的」。`);
      return;
    }
    setCreating(true);
    setFeedback("正在创建项目…");
    try {
      let response: Response;
      if (files.length) {
        const form = new FormData();
        form.append("title", trimmed);
        form.append("review_mode", mode);
        if (duration !== "") form.append("duration_seconds", duration);
        if (assetLocation.trim()) form.append("asset_location", assetLocation.trim());
        for (const file of files) {
          form.append("files", file, file.webkitRelativePath || file.name);
        }
        response = await fetch("/api/library/create-project", { method: "POST", body: form });
      } else {
        response = await fetch("/api/library/create-project", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: trimmed,
            asset_location: assetLocation.trim(),
            duration_seconds: duration === "" ? null : Number(duration),
            review_mode: mode,
          }),
        });
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setFeedback(friendlyFromPayload(data, "创建失败"));
        return;
      }
      if (data.imported_count) {
        setFeedback(`已导入 ${data.imported_count} 个文件，正在进入流程页…`);
      }
      window.location.href = `${data.board_path}${boardSuffix()}`;
    } catch {
      setFeedback("创建失败。请回聊天，让 Agent 创建项目并打开看板。");
    } finally {
      setCreating(false);
    }
  }

  const occupied = Boolean(occupant.project_id);

  return (
    <section className="library-onboarding" id="onboarding" aria-labelledby="onboardingTitle">
      <div className="library-onboarding-head">
        <div>
          <h2 id="onboardingTitle">创建新商品片</h2>
          <p>选评审方式、填主题，点开始创建后进入流程页按步确认。复制到聊天是退路。</p>
        </div>
        <button
          className="library-onboarding-copy"
          type="button"
          disabled={creating || occupied}
          title={occupied ? "请先点「中断并做别的」，再创建新项目" : "填写主题后点开始创建"}
          onClick={() => void onCreate()}
        >
          开始创建项目
        </button>
      </div>
      <div className="library-mode-route">
        <p className="library-mode-kicker">评审方式</p>
        <div className="library-mode-picker" role="radiogroup" aria-label="评审方式">
          {listReviewModes().map((item) => {
            const selected = item.id === route.id;
            return (
              <button
                key={item.id}
                type="button"
                className={"library-mode-btn" + (selected ? " selected" : "")}
                role="radio"
                aria-checked={selected}
                data-mode={item.id}
                onClick={() => {
                  if (item.id !== route.id) selectMode(item.id);
                }}
              >
                {item.label_zh}
              </button>
            );
          })}
        </div>
        <p className="library-mode-summary">{route.summary_zh}</p>
        <ol className="library-mode-steps">
          {route.confirm_steps.map((step) => (
            <li key={step.id} className="library-mode-step stop">
              <span className="library-mode-step-index">{step.index}</span>
              <span className="library-mode-step-name">{step.label_zh}</span>
              <span className="library-mode-step-action">{step.action_zh}</span>
            </li>
          ))}
        </ol>
        <p className="library-mode-note">
          只列出需要你确认的步骤。其余本机接着走。轻度/中度/重度在进入流程页后选择。
        </p>
      </div>
      <div className="library-create-fields">
        <input
          className="library-create-input"
          type="text"
          required
          placeholder="商品主题（必填）"
          aria-label="商品主题"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <input
          className="library-create-input"
          type="number"
          min={1}
          max={75}
          placeholder="时长秒数（可选，上限 75）"
          aria-label="时长秒数"
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
        />
        <div className="library-asset-row">
          <input
            className="library-create-input"
            type="text"
            placeholder="素材网址（可选）"
            aria-label="素材网址"
            value={assetLocation}
            onChange={(e) => setAssetLocation(e.target.value)}
          />
          <label className="library-file-btn">
            选择文件
            <input
              ref={fileRef}
              className="library-file-input"
              type="file"
              multiple
              accept="image/*,video/*"
              aria-label="选择本地文件"
              onChange={() => setFileTick((n) => n + 1)}
            />
          </label>
          <label className="library-file-btn">
            选择文件夹
            <input
              ref={folderRef}
              className="library-file-input"
              type="file"
              multiple
              aria-label="选择本地文件夹"
              // @ts-expect-error non-standard folder picker attributes
              webkitdirectory=""
              onChange={() => setFileTick((n) => n + 1)}
            />
          </label>
        </div>
        <span className="library-asset-hint">
          {files.length
            ? `已选 ${files.length} 个本地文件，创建时导入项目；能否使用仍在「素材检查」确认。`
            : "也可选本机文件或文件夹"}
        </span>
        <ul className="library-asset-list" aria-live="polite">
          {files.slice(0, 12).map((file) => (
            <li key={file.webkitRelativePath || file.name}>
              {file.webkitRelativePath || file.name}
            </li>
          ))}
          {files.length > 12 ? <li>……还有 {files.length - 12} 个</li> : null}
        </ul>
      </div>
      <div className="library-create-actions">
        <button
          className="library-copy-chat"
          type="button"
          onClick={async () => {
            const nextPrompt = buildCreateProductVideoPrompt(mode);
            if (promptRef.current) promptRef.current.value = nextPrompt;
            const result = await copyCreatePrompt({
              clipboard: navigator.clipboard,
              prompt: nextPrompt,
            });
            if (result.ok) {
              setFeedback("已复制，请回聊天粘贴并发送。");
              return;
            }
            setFeedback("无法自动复制，请选中下方文本并手动复制到聊天。");
            promptRef.current?.focus();
            promptRef.current?.select();
          }}
        >
          复制到聊天
        </button>
      </div>
      <textarea
        ref={promptRef}
        className="library-onboarding-prompt"
        readOnly
        rows={3}
        aria-label="创建商品片请求"
        value={prompt}
      />
      <p className="library-onboarding-feedback" aria-live="polite">
        {feedback}
      </p>
      <div className="library-service-list" aria-label="服务信息">
        <span>{serviceLine}</span>
        <span>{countLine}</span>
      </div>
      <details className="library-service-details">
        <summary>技术信息</summary>
        <p>{rootLine}</p>
      </details>
    </section>
  );
}
