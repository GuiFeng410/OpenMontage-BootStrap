# 仓内 Skill 根（G5）

宿主 **extraDirs 只加下面三个子根**（各自的直接子目录才是带 `SKILL.md` 的包）。不要把 extraDirs 指到本目录。

```text
<仓>/skills/bootstrap
<仓>/skills/providers
<仓>/skills/production
```

| 子根 | 内容 |
|------|------|
| `bootstrap/` | BootStrap 01–07 |
| `providers/` | 付费 / Stock 执行 Skill |
| `production/` | 路由、合同、L3、explainer、seedance |
| `pipelines/` | 上游阶段导演 md，**不进** extraDirs |
| `core/` `creative/` `meta/` | 参考文，不进 extraDirs |

旧路径 `openmontage/skills/` 仅保留说明 shim，兼容期内不要当 extraDirs 根。
