# 渲染记录

## 环境

- 目录：`remotion-composer/`
- 依赖：已存在 `node_modules`，无需额外安装
- 平台：Windows PowerShell，相对路径 `..\projects\...` 可用

## 使用的命令

```powershell
cd f:\small_work\vedio_github_project\OpenMontage\remotion-composer

# 分段 1 — hero_title + text_card + comparison + stat_card (~18s)
npx remotion render src/index.tsx Explainer `
  "..\projects\remotion-light-showcase\renders\segment-01-intro-comparison.mp4" `
  --props="..\projects\remotion-light-showcase\segment-01-intro-comparison.json"

# 分段 2 — bar_chart + line_chart + pie_chart + kpi_grid (~24s)
npx remotion render src/index.tsx Explainer `
  "..\projects\remotion-light-showcase\renders\segment-02-charts.mp4" `
  --props="..\projects\remotion-light-showcase\segment-02-charts.json"

# 分段 3 — terminal_scene + callout + progress_bar + text_card + hero_title (~21s)
npx remotion render src/index.tsx Explainer `
  "..\projects\remotion-light-showcase\renders\segment-03-terminal-close.mp4" `
  --props="..\projects\remotion-light-showcase\segment-03-terminal-close.json"

# 完整 60s
npx remotion render src/index.tsx Explainer `
  "..\projects\remotion-light-showcase\renders\showcase-60s.mp4" `
  --props="..\projects\remotion-light-showcase\explainer-props-60s.json"

# C+B 扩展 demo — line_chart 点标签 + comparison 三栏 (~10s)
npx remotion render src/index.tsx Explainer `
  "..\projects\remotion-light-showcase\renders\segment-cb-demo-10s.mp4" `
  --props="..\projects\remotion-light-showcase\segment-cb-demo-10s.json"

# 阶段 A data_table MVP demo (~10s)
npx remotion render src/index.tsx Explainer `
  "..\projects\remotion-light-showcase\renders\segment-datatable-demo-10s.mp4" `
  --props="..\projects\remotion-light-showcase\segment-datatable-demo-10s.json"
```

## 渲染结果

| 文件 | 时长 | 大小 | 耗时 |
|------|------|------|------|
| segment-01-intro-comparison.mp4 | ~18s | 3.2 MB | ~91s |
| segment-02-charts.mp4 | ~24s | 4.3 MB | ~117s |
| segment-03-terminal-close.mp4 | ~21s | 2.9 MB | ~119s |
| showcase-60s.mp4 | ~61s | 10.4 MB | ~368s |
| segment-cb-demo-10s.mp4 | ~11s（10s cuts +1s pad） | 1.9 MB | ~101s |
| segment-datatable-demo-10s.mp4 | ~11s（10s cuts +1s pad） | 1.7 MB | ~99s |

**总渲染时间**：约 12.8 分钟（前 4 个文件）；C+B / data_table demo 另渲。

## 修复说明

- **Phase A（图表深色主题）**：`Explainer` 已向 `BarChart` / `LineChart` / `PieChart` / `KPIGrid` 传递 `theme.textColor`（可由 `cut.color` 覆盖）；`segment-02-charts` 已按此重渲验证。
- **Phase B（Agent 参考）**：规划与能力边界见 `openmontage/skills/openmontage-bootstrap-03-usercheck/references/light-remotion-showcase.md`；demo props 已同步至 `remotion-composer/public/demo-props/light-showcase-*.json`。
- **阶段 1C + 2B**：`showPointLabels`（折线点数值，MVP 仅首系列）；`comparison.columns`（最多 4 栏）。验证片：`segment-cb-demo-10s`。
- **阶段 A（data_table）**：`headers` + `rows`，上限 5 列 × 5 行数据；Explainer / TalkingHead 已接线。验证片：`segment-datatable-demo-10s`。
- `calculateMetadata` 自动根据 `cuts[].out_seconds` 计算时长（末帧 +1s padding）。
