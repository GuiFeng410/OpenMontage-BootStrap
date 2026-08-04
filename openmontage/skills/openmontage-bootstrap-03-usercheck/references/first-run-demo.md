# 首次轻度 Demo · Agent 参考

| 项 | 内容 |
|----|------|
| 版本 | **v0.1** |
| 受众 | BootStrap `03-usercheck` 首次 Demo 确认卡 → `04-produce` |
| 原则 | **推荐非强制**；**有啥推啥**（只推荐本机已就绪的合成引擎） |
| 关联样板成片 | Remotion：`projects/remotion-light-showcase/renders/showcase-60s.mp4`；HyperFrames：`projects/hyperframes-jewelry-demo/renders/hyperframes_jewelry_20s.mp4` |

---

## 1. 何时出示

满足**全部**：

1. 安装闭环 + `verify_ready`（或等价 ready）已过  
2. 用户说「生成视频 / 做个视频」等，且**尚无**已锁定简报（表 1–3 / `video_plan`）  
3. 用户未明确说「跳过 demo / 按自己主题」

非首次（已有完成简报或成片）：可一句带过「也可再试短 demo」，默认进完整表 1→2→3。

---

## 2. 引擎探测（有啥推啥）

先查本机合成运行时（与 `AGENT_GUIDE` / registry 一致），例如：

```bash
python -c "from tools.tool_registry import registry; registry.discover(); print(registry._tools['video_compose'].get_info().get('render_engines'))"
```

或 doctor / `provider_menu_summary()` 里的 `composition_runtimes`。

| 本机状态 | Demo 确认卡上出现 |
|----------|-------------------|
| 仅 Remotion | 只推 **Remotion 图表+对比** 路径 |
| 仅 HyperFrames | 只推 **HyperFrames 品牌渐显** 路径 |
| 两者皆有 | **并列推荐两项**，用户选一 |
| 皆无 | 推 **动态文字 / 静态图卡** 短 demo；说明装 Remotion/HF 后可升级观感 |

禁止推荐本机不可用的引擎。

---

## 3. Demo 确认卡（一张即可）

| 项 | 默认 / 选项 |
|----|-------------|
| 档位 | **轻度**（锁死） |
| 时长 | **30s（推荐）** / **10s** |
| 引擎路径 | 仅列出探测到的推荐项（见上） |
| 主题文案 | **预设**（见 §4 / §5）或 **AI 现拟**（同结构，须用户点一次确认） |
| 旁白 / BGM | 可后置 |

用户口令示例：「按推荐开始」「用 10s」「换 AI 拟题」「跳过，走完整简报」。

确认后写入等价锁定字段（勿静默开烧）：

| 字段 | 值 |
|------|-----|
| `production_tier` | `light` |
| `duration_seconds` | `10` 或 `30` |
| `light_presentation` | `remotion` / `hyperframes` / `motion_text` / `still` |
| `theme` | 确认卡主题 |
| `video_plan` | 下方对应分段表 |
| `ai_video` | `disabled` |
| `first_run_demo` | `true`（可选标记） |

然后交接 **04-produce**。

---

## 4. Remotion 路径（反推自 light-showcase）

**样板来源**

| 文件 | 用途 |
|------|------|
| `projects/remotion-light-showcase/video_plan.md` | 60s 人读结构 |
| `…/segment-01-intro-comparison.json` | 标题 + 双栏对比 |
| `…/segment-02-charts.json` | 柱/折/饼/KPI |
| `…/segment-cb-demo-10s.json` | 10s：折线 + 多栏对比 |
| `references/light-remotion-showcase.md` | cut 清单与渲染命令 |

**主题预设（可原样或 AI 改写数字/标题）**：「向量搜索 vs 关键词搜索」— 语义理解 vs 字面匹配。

**风格**：`flat-motion-graphics`，深色底 `#0F172A`，强调色 `#22D3EE` / `#34D399` / `#FB7185`。

### 4.1 推荐规划 · 30s（图表 + 双栏）

| 分段 | 时长 | `cut.type` | 画面/文案要点（反推） |
|------|------|------------|------------------------|
| 1 | 0–4s | `hero_title` | 主标题「向量搜索 vs 关键词搜索」；副标「语义理解 · 字面匹配」 |
| 2 | 4–8s | `text_card` | 「关键词找相同字，向量找相近意」 |
| 3 | 8–14s | `comparison` | 双栏：左「关键词 / BM25」右「向量 / Embedding+ANN」 |
| 4 | 14–20s | `bar_chart` | Top-10 召回率：关键词 58 / 向量 85 / 混合 92（示意） |
| 5 | 20–26s | `line_chart` | 语料规模 vs P99 延迟（两系列对比） |
| 6 | 26–30s | `hero_title` 或 `text_card` | 收束「混合检索往往更稳」+ 片尾 |

Props 可裁剪自 `explainer-props-60s.json` / segment JSON；完整 cut 能力见 `light-remotion-showcase.md`。

### 4.2 推荐规划 · 10s（更快验收）

对齐 `segment-cb-demo-10s.json`：

| 分段 | 时长 | `cut.type` | 要点 |
|------|------|------------|------|
| 1 | 0–5s | `line_chart` | 语料规模 vs 延迟（可 `showPointLabels`） |
| 2 | 5–10s | `comparison` | 三栏或双栏召回率对比（关键词 / 向量 / 混合） |

### 4.3 一句话「提示词」给 Agent（Remotion）

> 做一支零 Key 轻度 Remotion 解说 demo：主题「向量搜索 vs 关键词搜索」，深色 flat-motion-graphics；必须含 **双栏/多栏 comparison** 与至少 **一种图表**（bar 或 line）；时长按用户选的 10s 或 30s；数据可为示意；旁白后置。参照 `projects/remotion-light-showcase/` 的 props 结构写 `Explainer` cuts。

---

## 5. HyperFrames 路径（反推自 jewelry demo）

**样板来源**

| 文件 | 用途 |
|------|------|
| `projects/hyperframes-jewelry-demo/hyperframes/index.html` | 20s 五幕：品牌标题渐显 → 动能文案 → 卖点卡 → 品牌句 → 片尾 |
| `…/renders/hyperframes_jewelry_20s.mp4` | 成片观感参照 |

**主题预设**：「璀璨臻品 / Fine Jewelry」品牌片气质（可换成用户品牌名，结构不变）。

**视觉**：深底 `#08080e`，金色强调 `#D4AF37`，衬线大标题 + 轻字重副标；GSAP 渐入/位移，**非** Remotion cut 表。

### 5.1 推荐规划 · 30s（品牌渐进）

可在 20s 样板上略拉长停留：

| 分段 | 时长 | 镜头目的 | 画面/文案要点（反推自 HTML） |
|------|------|----------|------------------------------|
| 1 | 0–5s | Logo/主标渐显 | 「璀璨臻品」+ 副标「Fine Jewelry · 精工细作」+ 金线展开 |
| 2 | 5–12s | 动能文案 | 「每一件作品」→「皆是匠心与美学的完美交融」 |
| 3 | 12–20s | 卖点三卡 | 18K金 / 天然钻石 / 手工镶嵌（错落入场） |
| 4 | 20–25s | 品牌句 | 「时光淬炼，历久弥新」 |
| 5 | 25–30s | 片尾 | 「致敬优雅的你」+ 英文小字收束 |

### 5.2 推荐规划 · 10s（最短品牌感）

| 分段 | 时长 | 要点 |
|------|------|------|
| 1 | 0–4s | 主标 + 副标渐显（对齐 scene1） |
| 2 | 4–7s | 一行动能文案（对齐 scene2 压缩） |
| 3 | 7–10s | 片尾品牌句（对齐 scene5） |

### 5.3 一句话「提示词」给 Agent（HyperFrames）

> 做一支零 Key 轻度 HyperFrames 品牌 demo：深色奢品风、金色强调；**主标/Logo 渐进显现** → 动能中文短句 →（30s 时）三卖点卡 → 品牌收束句；时长 10s 或 30s；参照 `projects/hyperframes-jewelry-demo/hyperframes/index.html` 的幕结构与 GSAP 入场，可替换品牌文案；旁白后置。

---

## 6. 与完整三表的关系

| 用户选择 | 行为 |
|----------|------|
| 确认 Demo 卡 | 写入轻度锁定字段 → **04**；**不**再强制走完整表 1→2→3 |
| 跳过 Demo | 进入原「就绪接话 → 表 1→2→3」 |
| Demo 出片后再做自己的片 | 新项目或改档：走完整三表 |

详细 Remotion cut 边界仍以 `light-remotion-showcase.md` 为准；本文件只服务**首次短 demo**。
