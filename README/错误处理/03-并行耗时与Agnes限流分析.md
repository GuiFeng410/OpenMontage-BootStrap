# 03 — 并行耗时与 Agnes 限流分析（llm-explainer-30s）

> 归属：[README/错误处理](./README.md)  
> 关联条目：[01-错误集合.md](./01-错误集合.md) 编号 **7、8**  
> 案例项目：`projects/llm-explainer-30s/`  
> 日期：2026-07-22

---

## 1. 一句话结论

**成片只有 30 秒，等待半小时+，不是因为「生成了很长的视频」。**  
时间主要花在：**云端排队渲染 + 官方视频 RPM 限流（429）/ 服务过载（503）导致的失败重试 + 被迫串行补跑**。  
对照 [Agnes Token Plan FAQ](https://agnes-ai.com/zh-Hans/docs/tokenplan)：**免费/默认用户视频实际只有 1 RPM**，原先默认「并发 3」会系统性撞限流，**并行策略必须按账号档位下调**。

---

## 2. 预估时间 vs 实际时间

### 2.1 当时怎么估的

规划汇报用的是理想公式：

```text
墙钟 ≈ ceil(段数 / 并发) × 单段云端耗时 + 拼接
     ≈ ceil(3/3) × ~5 分钟 + <2 分钟
     ≈ 6–9 分钟
```

隐含假设：

1. 三路几乎同时成功（并发 3 有效）
2. 每段大约一次提交就能完成
3. 几乎没有 503/429 风暴

### 2.2 实际发生了什么

| 项目 | 预估（理想） | 实际（llm-explainer-30s） |
|------|--------------|---------------------------|
| 成片长度 | 30s | ~30.2s（符合） |
| 段数 | 3×10s | 3×10s（符合） |
| 并发策略 | 3 路同时成功 | 先并发 3 → 大量 503/429 → 改并发 1 串行补跑 |
| 单段成功墙钟 | ~5 分钟 | 成功那次仍约 4–5 分钟（243s / 251s / 283s） |
| 失败开销 | 几乎不算 | 多轮失败 + 退避 + 编排空跑 bug |
| 拼接 | <2 分钟 | 几秒～十几秒 |
| **总等待** | **6–9 分钟** | **约 30–40 分钟量级** |

### 2.3 为什么「10 秒片」要等「4～5 分钟」

```text
成片时长 10s  = 播放长度
墙钟 4～5 分钟 = 云端排队 + GPU 按帧生成 + 编码上传 + 本地轮询
```

二者本来不是 1:1。预估里的「每段约 5 分钟」指的是**墙钟**，不是「生成 5 分钟长的片子」。

---

## 3. 出错原因拆解

### 3.1 503 Service Unavailable

- 典型位置：`POST https://apihub.agnes-ai.com/v1/videos`
- 含义：服务端忙/过载，创建任务被拒绝
- 本地表现：请求很快失败，尚未进入正常「渲完再下载」

### 3.2 429 Too Many Requests（与官方 RPM 对齐后的主因）

- 典型位置：轮询 `/agnesapi?video_id=...`（也可能出现在 create）
- 含义：单位时间内请求过多，触发限流

根据官方 [Token Plan FAQ · 视频模型 RPM](https://agnes-ai.com/zh-Hans/docs/tokenplan)：

| 用户类型 | 允许发起 RPM | 实际 RPM |
|----------|-------------:|---------:|
| 免费 / 默认 (`default`) | 2 | **1** |
| 企业认证 (`enterprise`) | 2 | **2** |
| Token Plan (`TokenPlan`) | 6 | **5** |

文档原文要点：

- 免费 / 默认用户视频模型为 **1 RPM**
- 企业认证为 **2 RPM**
- Token Plan 为 **5 RPM**
- Token Plan 另有视频订阅配额：**每天 500 秒**（Starter/Plus/Pro 同为此值，见同页配额表）
- **同类型多个 Key 共享同一限制池**，多开 Key 不能叠 RPM

因此：本机默认 **并发 3**，在 default 档等于「每分钟只允许约 1 次视频相关请求」的前提下硬开三路 create + 密集 poll → **429 几乎必然**。

### 3.3 编排 bug（已修，见错误集合 #8）

`generation_manifest` 残留 `running` 时，旧逻辑不重试却仍去拼接 → 空跑 / `FileNotFoundError`。  
已修：`pending`/`failed`/`running` 均可补跑；未完成禁止 assemble。

### 3.4 与官方其它文档的关系

| 文档 | 与本次的关系 |
|------|----------------|
| [概述](https://agnes-ai.com/zh-Hans/docs/overview) | 说明视频能力与 Base URL `https://apihub.agnes-ai.com/v1`；不解释限流数值 |
| [OpenClaw 集成](https://agnes-ai.com/zh-Hans/docs/cid1) | 配置 Base URL / Key / 模型名；故障排查提到认证、余额、网络，**未给出视频 RPM** |
| [Token Plan FAQ](https://agnes-ai.com/zh-Hans/docs/tokenplan) | **本问题的关键依据**：视频 RPM + 每日秒数配额 |
| [隐私政策](https://agnes-ai.com/zh-Hans/docs/privacy-policy) | 不涉及限流；说明免费层可能用于模型改进、付费 Token Plan 默认不训练等，与耗时无关 |

---

## 4. 真实时间线（llm-explainer-30s）

UTC 日志，本地约为 UTC+8。

```text
第一轮 并发3（约 18:40–18:46）
  scene01：多次失败后成功 ≈4 分钟
  scene02 / scene03：503 / 429，重试耗尽 → 失败
  → 约 6 分钟只换来 1/3 素材

中间（约 18:47）
  manifest running 空跑 / 误拼接风险（bug）

第二轮 并发1 串行补跑（约 18:52–19:14）
  scene02 成功 ≈4 分钟级（含失败与退避）
  scene03 成功 ≈4–5 分钟级（串行排在 scene02 后）
  → 补跑本身十几分钟量级

拼接
  FFmpeg concat + 烧字幕：秒级～十几秒
```

成功段 wall（manifest）：

- scene01：242.71s  
- scene02：251.24s  
- scene03：282.77s  

---

## 5. 原先并行方法要不要改？——要改

### 5.1 哪些可以保留

| 保留 | 理由 |
|------|------|
| 先规划、拆 5–10s 段 | Agnes 单段上限与镜头结构仍需要 |
| 落盘即进度 / 跳过已有 | 失败后只补缺段，正确 |
| 主 Agent 一次 FFmpeg 拼接 | 本地便宜，不必树形拼接 |
| 503/429 退避重试 | 仍需要，但不能代替「降并发」 |

### 5.2 哪些必须改

| 原做法 | 问题 | 应改为 |
|--------|------|--------|
| 默认 `max_concurrency=3` | 对 default 档视频 **1 RPM** 过激进 | **按账号档位设上限**（见下表） |
| 预估只报乐观值 | 用户以为 6–9 分钟必达 | **乐观 + 保守双档** |
| 遇 429 仍维持高并发重试 | 放大限流 | **自动降并发到 1，再补跑** |
| 密集轮询 | 可能占用 RPM | 拉长 poll 间隔（如 5s→8–10s），失败退避更长 |

### 5.3 推荐并发上限（按官方实际 RPM）

| 账号档位 | 官方视频实际 RPM | 推荐 `max_concurrency` | 说明 |
|----------|----------------:|------------------------:|------|
| default（免费/默认 Key） | 1 | **1** | 实质串行；「并行」只能体现在规划与补跑编排，不能硬开多路 create |
| enterprise | 2 | **1～2** | 可尝试 2；若 429 立刻降到 1 |
| TokenPlan | 5 | **2～3**（上限建议 ≤3） | 虽有 5 RPM，create+poll 仍占请求；留余量给轮询 |

环境变量建议（实现时可落地）：

```text
AGNES_ACCOUNT_TIER=default|enterprise|tokenplan
AGNES_VIDEO_MAX_CONCURRENCY=...   # 可选覆盖
```

### 5.4 预估话术（以后统一）

以 3×10s、单段云端约 5 分钟为例：

| 档位 | 并发 | 乐观 | 保守（含失败/退避） |
|------|------|------|---------------------|
| default | 1 | ~15–18 分钟 | ~25–40 分钟 |
| enterprise | 2 | ~8–12 分钟 | ~15–25 分钟 |
| TokenPlan | 2～3 | ~6–10 分钟 | ~12–20 分钟 |

**禁止**再对 default 用户只报「并发 3 → 6–9 分钟」。

### 5.5 配额提醒（Token Plan）

Token Plan 视频配额为 **每天 500 秒**（见 [tokenplan](https://agnes-ai.com/zh-Hans/docs/tokenplan)）。  
例如一天内多次试拍 30s×N，可能先撞日配额而非 RPM。规划阶段应估算：`sum(scene.duration)` 是否接近当日剩余秒数。

---

## 6. 推荐解决方法（分层）

### P0 — 立刻（流程 / 配置）✅ 已落地

1. **Agnes 视频默认并发改为 1**（default 档）  
2. 规划确认时问清 / 配置 `AGNES_ACCOUNT_TIER`  
3. 对外汇报使用**双档预估**  
4. 出现 429：降并发到 1，只补 `pending/failed/running`，不重做已完成段  

### P1 — 代码 ✅ 已落地（2026-07-23）

1. `lib/parallel_generate.py`：按 `AGNES_ACCOUNT_TIER` 选择默认并发（tokenplan=3）；CLI `--concurrency` 不得超过档位上限（除非 `--force-concurrency`）  
2. `retry_wait_seconds`：429 更长退避；`poll_interval_seconds` 默认 8s  
3. `planning_report`：输出乐观/保守两行  
4. skill `parallel-video-orchestration.md` 与 `docs/长视频并行编排` 已同步  

### P2 — 账号侧（可选）

- 需要稳定多路并行：升级 **企业认证（2 RPM）** 或 **Token Plan（5 RPM + 日 500 秒）**  
- 勿指望「多造几个同类型 Key」提高限额（官方明确共享限制池）  

### 不推荐

- 默认并发 6「抢时间」  
- 失败后无脑把三段全部重生成  
- 用树形子 Agent 拼接「省时间」（省不了云端墙钟）  

---

## 7. 生活比喻（便于对齐预期）

Agnes 视频像只有少量灶台的厨房：

- default：大约 **每分钟只接 1 单**（1 RPM）  
- 你一次喊 3 桌同时上菜 → 厨房说没空（503）或别催（429）  
- 正确做法：按灶台数排队；并行规划可以做，但下单节奏要服从 RPM  

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-22 | 初版：结合 llm-explainer-30s 日志与 Agnes Token Plan 官方 RPM，给出并行策略改动建议 |
| 2026-07-23 | P0+P1 落地：档位并发（tokenplan 默认 3）、双档预估、429 降并发、文档同步 |
