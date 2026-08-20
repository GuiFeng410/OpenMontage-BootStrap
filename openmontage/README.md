# 已迁移（G5-D shim）

Python 包本体在 `src/openmontage/`。本目录只留加载器：把 `src/` 插进 `sys.path`，避免仓根同名目录挡住 `python -m openmontage.mcp.*`。

`skills/` 仍是 G5 Skill 旧路径占位：`ResourceLocator.bootstrap_skills()` 优先 `skills/bootstrap`。
