# Remotion 可渲染能力边界

> 以代码为准：`cut.type` / `overlay.type` 必须能在 `Explainer.tsx` 分发到组件。  
> 权威字段表：`remotion-composer/SCENE_TYPES.md`  
> 轻度样板：`projects/remotion-light-showcase/`  
> Agent 参照（本版不改）：`openmontage/skills/openmontage-bootstrap-03-usercheck/references/light-remotion-showcase.md`

---

## 1. 总览

### Remotion 在本仓的定位

`remotion-composer` 是 **模板化 Composition 引擎**：用 JSON props（cuts / overlays / captions / audio）驱动 React 场景，本地渲染，不依赖外部视频生成 API。

轻度出片选 **Remotion 动画**（BootStrap 表 2.1，`light_presentation=remotion`）时，默认走 **`Explainer` Composition**：按 `cut.type` 拼文字卡、对比、图表、终端演示等，适合技术讲解 / 数据叙事 / 产品概念片。

### 与 BootStrap 轻度 Remotion

| 项 | 说明 |
|----|------|
| 确认入口 | `03-usercheck` 表 2.1 第 4 项「Remotion 动画」 |
| 规划参照 | `references/light-remotion-showcase.md`（60s 三幕、11 种样板 cut） |
| 仓内样板 | `projects/remotion-light-showcase/` |
| 本文件职责 | 说清「能渲什么 / 边界在哪 / 样片在哪」；**不替代** 03 Skill 与 showcase 参照链接 |

### 与 HyperFrames / AI 视频的分工（直白）

| 路径 | 擅长 | 不适合硬扛 |
|------|------|------------|
| **Remotion · Explainer** | 结构化讲解、图表动画、合成终端/截图演示、主题色统一 | 逐帧手绘动效、复杂 GSAP 时间轴、品牌定制 atelier 片（另走 atelier 模式） |
| **HyperFrames** | HTML/CSS/GSAP 手写合成、细粒度动效、数据可视化定制布局 | 与 Explainer 同一套 `cut.type` 目录（两套作者路径） |
| **AI 视频（重度）** | 实拍感镜头、角色/场景生成 | 精确数字图表、可复现的数据叙事（应用 Remotion/HF） |

---

## 2. 主表：Explainer 的 cut / overlay

列说明：

| 列 | 含义 |
|----|------|
| 效果场景 | 用户口头说法（中文） |
| cut/overlay 类型 | 技术名（英文，写 props 用） |
| 适合内容 | 什么素材/文案塞进去 |
| 具体方式 | 怎么写 props / 走哪条分发 |
| 能力边界 | 做不到或易踩坑 |
| 样片参照 | showcase 段或说明 |

分发实现：`remotion-composer/src/Explainer.tsx` → `SceneRenderer` / `OverlayRenderer`。

### 2.1 文字章节

| 效果场景 | cut/overlay 类型 | 适合内容 | 具体方式 | 能力边界 | 样片参照 |
|----------|------------------|----------|----------|----------|----------|
| 开场大标题 / 片尾标题 | `hero_title`（cut） | 主标题 + 可选副标题 | cut 顶层 `text`、`heroSubtitle`（或 `subtitle`）；可配 `backgroundVideo` / `backgroundImage` | 不是多行富文本编辑器；长文案请拆 `text_card` | 段1 hook；段3 end；完整片 `0:00–0:04` / `0:58–1:00` |
| 一句话陈述 / 过渡文案 | `text_card` | 短句、收束语 | `text`；可选 `fontSize`、`color`、`backgroundColor` | 大字排版，不宜塞整段 PPT | 段1 intro；段3 takeaway |
| 提示框 / 警告 / 引用 | `callout` | tip / warning / info / quote | `text` + `callout_type`；可选 `title` | 框内条目式文案；非表格 | 段3 hybrid-tip |

### 2.2 对照指标

| 效果场景 | cut/overlay 类型 | 适合内容 | 具体方式 | 能力边界 | 样片参照 |
|----------|------------------|----------|----------|----------|----------|
| 左右两边比一比 / 最多四栏对比 | `comparison` | 双栏标签+数值，或 2–4 栏 | 双栏：`leftLabel`/`leftValue`/`rightLabel`/`rightValue`；多栏：`columns: [{label,value,color?}]`（≥2 时覆盖双栏；**上限 4**）；可选 `title` | 超过 4 栏会 slice 并 console 警告；更大矩阵改 `bar_chart` / `kpi_grid` | 段1 compare（双栏）；`segment-cb-demo-10s` 三栏 |
| 一个超大数字 | `stat_card` | KPI 亮点、百分比 | `stat` + 可选 `subtitle`、`accentColor` | 单值；多指标用 `kpi_grid` | 段1 recall-stat |
| 完成度 / 采用率条 | `progress_bar` | 0–1 进度 | `progress`；可选 `progressLabel`、`progressColor`、`progressSegments`、`title` | 不是甘特图；无多任务并行时间轴 | 段3 adoption |

### 2.3 图表

| 效果场景 | cut/overlay 类型 | 适合内容 | 具体方式 | 能力边界 | 样片参照 |
|----------|------------------|----------|----------|----------|----------|
| 分类对比柱状图 | `bar_chart` | 分类名 + 数值数组 | `chartData`；可选 `chartAnimation`、`showValues`、`showGrid`、`title`、`chartColors` | 深色主题须依赖 Explainer 传入的 `textColor`/`gridColor`（见 [01](./01-Remotion图表深色主题可读性优化.md)） | 段2 recall-bars → `renders/segment-02-charts.mp4` |
| 趋势折线 | `line_chart` | 多系列时序 | `chartSeries`；可选 `xLabel`/`yLabel`、`showMarkers`、`showLegend`、**`showPointLabels`** | 点标签默认关；开启时 **MVP 只标第一条 series**（避重叠） | 段2 latency-line；`segment-cb-demo-10s` 点标签 |
| 占比饼/环图 | `pie_chart` | 份额分布 | `chartData`；可选 `donut`、`centerLabel`/`centerValue`、`showLegend` | 扇区过多会挤；复杂占比表见「做不到」表 | 段2 query-pie |
| 多 KPI 卡片栅格 | `kpi_grid` | 2–4 个指标 | `chartData`（metrics）；可选 `columns`、`title`、`chartAnimation` | `change` 须为数字；大数用 `value`+`suffix` | 段2 metrics-kpi |
| 简易数据表 | `data_table` | 表头 + 多行短文本/数字 | 必填 `headers: string[]`、`rows: string[][]`；可选 `title` | **MVP 上限**：≤5 列、≤5 行数据（+表头共 ≤6 视觉行）；无合并单元格；`highlightRow` 二期。须传 `color`/`theme.textColor` + `surface` 作卡片底，避免深色片字看不见 | `segment-datatable-demo-10s` |

### 2.4 演示

| 效果场景 | cut/overlay 类型 | 适合内容 | 具体方式 | 能力边界 | 样片参照 |
|----------|------------------|----------|----------|----------|----------|
| 合成终端打字演示 | `terminal_scene` | CLI / API 步骤 | `steps`（cmd/out/pause/pill）；可选 `terminalTitle`、`prompt`、`accentColor` | **无需真录屏**；非真实交互回放 | 段3 demo-terminal；完整片 `0:41–0:47` |
| 截图上叠鼠标/高亮 | `screenshot_scene` | 产品 UI walkthrough | 必填 `backgroundImage` + `screenshotSteps`；可选 `screenshotSize`、`cursorStartAt` | 坐标相对 contain-fit 归一化；本样板**未覆盖** | 无 showcase 成片；组件在 `ScreenshotScene` |
| 多图动漫风场景 | `anime_scene` | 静帧序列 + 粒子/光效 | `images[]`；可选 `particles`、`lightingFrom`/`To`、`vignette`、`animation` | 需图片资产；零密钥讲解优先 11 种样板 cut | 样板未用 |

### 2.5 媒体底图（无 type 或兜底）

| 效果场景 | cut/overlay 类型 | 适合内容 | 具体方式 | 能力边界 | 样片参照 |
|----------|------------------|----------|----------|----------|----------|
| 直接播一段 MP4 | （无 type，有视频 `source`） | 本地/URL 视频 | `source` 指向 mp4 等；可选 `source_in_seconds`、Ken Burns 类 `animation` | 走 `OffthreadVideo`；静音底轨由 Composition 管；非 AI 生片 | 样板未用；任意 Explainer props |
| 静图 + 运镜 | （无 type，有图片 `source`） | png/jpg 等 | `source` + `animation`（zoom-in / ken-burns / pan-* 等） | 兜底：有 `source` 但扩展名未识别时仍按图处理 | 样板未用 |
| 组件背后垫图/垫视频 | （任意组件 cut 的字段） | 氛围底 | cut 上 `backgroundImage` 或 `backgroundVideo`（视频优先）；`backgroundOverlay` 控暗层 | 默认暗层约 0.55，保证字可读 | 组件 cut 通用 |

### 2.6 Overlay（叠在画面上）

| 效果场景 | cut/overlay 类型 | 适合内容 | 具体方式 | 能力边界 | 样片参照 |
|----------|------------------|----------|----------|----------|----------|
| 角落章节小标题 | `section_title` | 短标签 | overlays 数组：`text`、可选 `position`/`accentColor` | 不是全屏标题（全屏用 cut `hero_title`） | 完整片「核心差异 / 数据表现 / 生产指标」 |
| 角标大数字 | `stat_reveal` | 短统计 | `text` + 可选 `subtitle`、`position` | 角标级；主视觉数字用 `stat_card` | 完整片 +47%、62% |
| 全屏标题叠层 | `hero_title`（overlay） | 临时盖字 | overlay 的 `text`/`subtitle` | 与 cut 版同组件，注意时间轴重叠 | 样板主用 cut 版 |
| 技术栈/厂商轮播徽章 | `provider_chip` | 名称列表 | `providers[]`；可选 `cycleSeconds`、`label`、`position` | 用于标注生成源/栈名，非图表 | 完整片 `0:41–0:47` |

**旁白字幕：** 非 overlay.type；走顶层 `captions`（词级）→ `CaptionOverlay`。样板 `audio: {}`，配音可后补。

---

## 3. 辅表：Composition 入口（Root.tsx）

注册表：`remotion-composer/src/Root.tsx`。轻度讲解默认 **`Explainer`**。

| Composition id | 用途（一句话） | 何时用 | 备注 |
|----------------|----------------|--------|------|
| **Explainer** | 按 cuts/overlays 拼讲解片 | 轻度 Remotion、数据叙事、本文件主表全部场景 | 1920×1080；时长由 cuts 末尾推算 |
| TalkingHead | 竖屏口播底片 + 侧栏/三分之一叠组件 | 已有说话人视频，要叠图表/字幕卡 | 1080×1920；overlay 复用部分 Explainer 组件，**不是**完整 Explainer 时间轴 |
| CinematicRenderer | 多场景影调视频 + 标题条 | 成片感、信号线/影调场景编排 | 另有 fixture：`SignalFromTomorrowWithMusic` |
| TitledVideo | 底片上压一句大 tagline | 已有成片只加片尾金句 | 横屏 |
| HeroTitle | 单独渲标题卡 | 只出片头/片尾静帧动画 | 也可作 Explainer cut/overlay |
| ProductReveal / ProductRevealVertical | 产品图揭示 | 商品短揭示（横/竖） | 非轻度讲解主路径 |
| CaptionOverlayOnly | 只渲字幕层 | 后期叠字幕 | — |
| CollageBurst | 竖屏拼贴爆发 | 多片段 curtain 拼贴 | 1080×1920 |
| LyricOverlay | 歌词叠底片 | 音乐歌词类 | 竖屏 |
| EndTag / EndTagOverlay | 片尾金句 | 冷色收束字；Overlay 版可合成到正片上 | — |

---

## 4. 做不到 / 需另路径

| 想要的效果 | Remotion 现状 | 建议路径 |
|------------|---------------|----------|
| 复杂数据表格（合并格 / 超限行列） | `data_table` **MVP 已支持**简易表：≤5 列、≤5 行数据（+表头）；无合并 | 更大矩阵 / 合并单元格：`screenshot_scene` 或 HyperFrames；超限会被 slice |
| 三栏及以上「左右对比卡」 | **已支持**：`comparison.columns`，上限 **4** | 超过 4 栏或矩阵对比 → `bar_chart` / `kpi_grid` |
| 折线上每个点标数值 | **已支持**：`showPointLabels`（默认 false；MVP 仅第一条 series） | 多系列全标 / 避碰布局仍待扩展 |
| 真·录屏交互回放 | `terminal_scene` / `screenshot_scene` 是**合成演示** | 真录屏用播放 `source` 视频 cut，或 Playwright 录制后再 Embed |
| Chat / IDE / PR / Slack 等专用 UI 场景 | SCENE_TYPES 仅列候选，**未实现** cut | 勿规划；用 `screenshot_scene` 或等组件落地 |
| 品牌定制、非模板观感 | Explainer 是模板化 cut 目录 | Atelier 手写 Composition，或 HyperFrames |
| 电影级生成镜头 | Remotion 不生成画面内容 | 重度 AI 视频管线后再合成 |
| 默认浅色字色忘传导致图表「看不见」 | 已修 Explainer 传 `textColor`；组件默认仍偏浅色主题 | 深色片自检见 showcase 参照 §6；细节见 [01](./01-Remotion图表深色主题可读性优化.md) |

---

## 5. 轻度 60s 推荐编排（showcase 三幕）

样板主题：向量搜索 vs 关键词搜索 · `theme: flat-motion-graphics` · 1920×1080 · 30fps。

| 幕 | 时长 | Props | 成片 | 镜头串 |
|----|------|-------|------|--------|
| 1 · intro / 对比 | ~17–18s | `segment-01-intro-comparison.json` | `renders/segment-01-intro-comparison.mp4` | `hero_title` → `text_card` → `comparison` → `stat_card` |
| 2 · charts | ~23–24s | `segment-02-charts.json` | `renders/segment-02-charts.mp4` | `bar_chart` → `line_chart` → `pie_chart` → `kpi_grid` |
| 3 · terminal-close | ~20–21s | `segment-03-terminal-close.json` | `renders/segment-03-terminal-close.mp4` | `terminal_scene` → `callout` → `progress_bar` → `text_card` → `hero_title` |

完整片：`explainer-props-60s.json` → `renders/showcase-60s.mp4`。

规划口诀：钩子标题 → 论证（对比/图表）→ 演示或收束；每镜约 4–6s；图表至少留 4s；用 `section_title` 分段。

项目目录：`projects/remotion-light-showcase/`（另有 `video_plan.md`、`RENDER.md`）。

---

## 6. 维护说明

1. **新增 cut/overlay**：改组件 → `components/index.ts` → `Explainer.tsx` 类型与分发 → **必须**更新 `SCENE_TYPES.md` → 再改本文件主表。  
2. **本版范围**：仅 `docs/轻度视频可优化点/`；**不改** `03-usercheck` SKILL、**不改** `light-remotion-showcase.md` 链接正文。  
3. **样片路径变更**：同步改本节 §5、[01](./01-Remotion图表深色主题可读性优化.md) 背景表，并提醒更新 Agent 参照。  
4. **勿臆造 type**：规划前对照 `SCENE_TYPES.md` 与 `SceneRenderer`；文档无、代码无的 type 禁止写入 props。  
5. **图表深色可读性**：历史问题与 Phase A 修复见 [01](./01-Remotion图表深色主题可读性优化.md)；能力边界（点标签、表格）归本文件 §4。

### 核对基准（写本文时）

| 来源 | 路径 |
|------|------|
| cut/overlay 权威表 | `remotion-composer/SCENE_TYPES.md` |
| 分发分支 | `remotion-composer/src/Explainer.tsx` |
| Composition 列表 | `remotion-composer/src/Root.tsx` |
| 轻度 Agent 参照 | `openmontage/.../references/light-remotion-showcase.md` |
| 图表可读性记录 | `docs/轻度视频可优化点/01-Remotion图表深色主题可读性优化.md` |
| 样片工程 | `projects/remotion-light-showcase/` |
