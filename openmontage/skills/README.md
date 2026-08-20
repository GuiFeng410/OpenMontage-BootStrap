# 已迁移（G5 shim）

仓内 BootStrap / Provider / 生产 Skill 已迁到：

- `skills/bootstrap/`
- `skills/providers/`
- `skills/production/`

请把宿主 extraDirs 改为上述三个目录。本目录不再放置 `SKILL.md` 包。

资源定位：`ResourceLocator.bootstrap_skills()` 优先 `skills/bootstrap`，此处仅作旧路径占位。
