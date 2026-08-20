import { commercialContentView } from "./model";
import type { BoardState, StageEvidenceItem } from "./types";

type Props = { state: BoardState; selectedStage: string | null };

export function StageEvidence({ state, selectedStage }: Props) {
  const view = commercialContentView(state, selectedStage);
  const evidence = state.commercial?.stage_evidence || {};
  if (view === "sample") return <SamplePanel sample={evidence.sample || {}} />;
  if (view === "draft") return <DraftPanel draft={evidence.draft || {}} />;
  if (view === "compose") return <ComposePanel compose={evidence.compose || {}} />;
  if (view === "delivery") return <DeliveryPanel delivery={evidence.delivery || {}} />;
  return null;
}

function MediaWarning({ item }: { item: StageEvidenceItem }) {
  if (item.exists !== false || !item.missing_path) return null;
  return <div className="hint warn-text">{item.missing_reason_zh || `媒体文件不存在：${item.missing_path}`}</div>;
}

function SamplePanel({ sample }: { sample: StageEvidenceItem }) {
  return (
    <div className="panel commercial-stage-evidence">
      <div className="panel-head">
        <h2>试片确认</h2>
        <span className="meta">sample_reel</span>
      </div>
      <div className="panel-body commercial-summary">
        <div className="kv-row">
          <span className="kv-k">试片状态</span>
          <span className="kv-v">{sample.status || "待生成"}</span>
        </div>
        <div className="kv-row">
          <span className="kv-k">时长</span>
          <span className="kv-v">{sample.duration_seconds != null ? `${sample.duration_seconds}s` : "待探测"}</span>
        </div>
        {sample.path ? (
          <div className="kv-row">
            <span className="kv-k">项目相对路径</span>
            <span className="kv-v evidence-path">{sample.path}</span>
          </div>
        ) : null}
        {sample.user_confirmation_text ? (
          <div className="commercial-evidence-list">
            <b>用户确认</b>
            <div>{sample.user_confirmation_text}</div>
          </div>
        ) : (
          <div className="hint">尚未记录用户对试片的确认。</div>
        )}
        <MediaWarning item={sample} />
      </div>
    </div>
  );
}

function DraftPanel({ draft }: { draft: StageEvidenceItem }) {
  const issues = draft.issue_segments || [];
  const modifications = draft.modification_list || [];
  return (
    <div className="panel commercial-stage-evidence">
      <div className="panel-head">
        <h2>初稿审查</h2>
        <span className="meta">full_draft_pro</span>
      </div>
      <div className="panel-body commercial-summary">
        {draft.path ? (
          <div className="kv-row">
            <span className="kv-k">项目相对路径</span>
            <span className="kv-v evidence-path">{draft.path}</span>
          </div>
        ) : null}
        <MediaWarning item={draft} />
        {issues.length ? (
          <div className="commercial-evidence-list">
            <b>问题片段</b>
            {issues.map((item, i) => (
              <div key={i}>{`${item.beat || "片段"} · ${item.time || "时间待补"} · ${item.issue_zh || item.issue || "待说明"}`}</div>
            ))}
          </div>
        ) : (
          <div className="hint">尚未写入问题片段；初稿通过前应记录审查结论。</div>
        )}
        {modifications.length ? (
          <div className="commercial-evidence-list">
            <b>修改清单</b>
            {modifications.map((item, i) => (
              <div key={i}>{`${i + 1}. ${item}`}</div>
            ))}
          </div>
        ) : (
          <div className="hint">尚未写入修改清单。</div>
        )}
      </div>
    </div>
  );
}

function ComposePanel({ compose }: { compose: StageEvidenceItem }) {
  const probe = compose.technical_probe || {};
  const rows: [string, string | number | null | undefined][] = [
    ["审查结论", compose.status],
    ["时长", probe.duration_seconds != null ? `${probe.duration_seconds}s` : null],
    ["分辨率", probe.resolution],
    ["帧率", probe.fps != null ? `${probe.fps} fps` : null],
    ["音频", probe.has_audio == null ? null : probe.has_audio ? "存在" : "缺失"],
  ];
  const issues = [...(probe.issues || []), ...(compose.issues_found || [])];
  return (
    <div className="panel commercial-stage-evidence">
      <div className="panel-head">
        <h2>合成终稿 · 技术检查</h2>
        <span className="meta">final_review</span>
      </div>
      <div className="panel-body commercial-summary">
        {rows
          .filter(([, value]) => value != null)
          .map(([label, value]) => (
            <div className="kv-row" key={label}>
              <span className="kv-k">{label}</span>
              <span className="kv-v">{String(value)}</span>
            </div>
          ))}
        <MediaWarning item={compose} />
        {issues.length ? (
          <div className="commercial-evidence-list">
            <b>技术问题</b>
            {issues.map((issue) => (
              <div key={issue}>{issue}</div>
            ))}
          </div>
        ) : (
          <div className="hint">技术检查未发现问题。</div>
        )}
      </div>
    </div>
  );
}

function DeliveryPanel({ delivery }: { delivery: StageEvidenceItem }) {
  return (
    <div className="panel commercial-stage-evidence">
      <div className="panel-head">
        <h2>交付确认</h2>
        <span className="meta">decision_log</span>
      </div>
      <div className="panel-body commercial-summary">
        <div className="kv-row">
          <span className="kv-k">质量结论</span>
          <span className="kv-v">{delivery.quality_status || "待技术检查"}</span>
        </div>
        <div className="kv-row">
          <span className="kv-k">签收状态</span>
          <span className="kv-v">{delivery.decision_label_zh || delivery.decision || "等待聊天确认"}</span>
        </div>
        {delivery.decision_response_zh ? (
          <div className="commercial-evidence-list">
            <b>用户回复</b>
            <div>{delivery.decision_response_zh}</div>
          </div>
        ) : null}
        <MediaWarning item={delivery} />
      </div>
    </div>
  );
}
