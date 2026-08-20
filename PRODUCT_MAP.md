# PRODUCT_MAP — 逻辑分层（不大搬家）

OpenMontage-BootStrap 当前目录仍按历史路径放代码。本文件只做**阅读地图**，不要求把 `tools/`、`lib/` 一次性改名。

版本身份见 [`distribution/manifests/release-manifest.json`](distribution/manifests/release-manifest.json)。

```text
open-montage-boot-strap/
│
├─ 01-agent-entry/               Agent 入口与宿主约定
│  ├─ AGENT_GUIDE.md
│  ├─ AGENTS.md
│  ├─ skills/bootstrap/          BootStrap 01–07（extraDirs #1）
│  ├─ skills/providers/          付费 / Stock 执行 Skill（extraDirs #2）
│  └─ skills/production/         路由、合同、L3、explainer、seedance（extraDirs #3）
│
├─ 02-production-engine/         生产引擎
│  ├─ product/pipelines/         YAML 管线清单
│  ├─ skills/                    导演 md：pipelines / core / creative / meta（不进 extraDirs）
│  ├─ tools/
│  └─ lib/
│
├─ 03-state-contracts/           数据契约
│  └─ product/schemas/           JSON Schema
│
├─ 04-interfaces/                用户与 Agent 接口
│  ├─ openmontage/mcp/
│  └─ backlot/
│
├─ 05-render-runtimes/           合成运行时
│  ├─ runtimes/remotion/
│  └─ ink-theater/
│
├─ 06-quality/
│  └─ tests/
│
├─ 07-distribution/              安装 / 升级（骨架）
│  └─ distribution/
│
├─ product/styles/               风格 YAML
│
└─ 08-local-workspace/           不提交 Git
   ├─ Agent-Docs/
   ├─ Agent-ReadMe/
   ├─ Agent-Temp/
   └─ projects/                  产品语义上是用户作品，升级不得覆盖
```

Python 加载器仍在 `styles/playbook_loader.py` 与 `schemas/artifacts/`（`from styles.playbook_loader` / `from schemas.artifacts` 未改）。

**产品三层（目标，尚未物理拆仓）：** 仓库是工厂；`release-manifest` 是成品版本；`projects/` 是作品仓库。详见 `Agent-ReadMe/other/02.md`（本机）或 Goal/01。
