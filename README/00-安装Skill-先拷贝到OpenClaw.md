# 00 — 安装 Skill：先拷贝到 OpenClaw

适用：机器上**还没有** OpenMontage 仓库，只想先在 OpenClaw 里装一个引导 Skill。

## 1. 拷贝什么

从已发布的 BootStrap 仓（或本机已有副本）复制整个目录：

```text
openmontage/skills/openmontage-bootstrap-installer/
```

到 OpenClaw **用户本地独立 Skill 目录**（路径以你的 OpenClaw/eClaw 为准，例如 `~/.openclaw/skills/`）。

启用 Skill：`openmontage-bootstrap-installer`。

此时**不必**先配置门面 MCP。

## 2. 对 Agent 说什么

> 我想生成视频 / 做个动画解说，按 BootStrap 安装流程来。

## 3. 安装 Skill 会做什么

1. 问你要把仓库放到哪个文件夹 `<TARGET>`  
2. 引导（或代跑）`git clone`：先 GitHub，失败用 Gitee  
3. **只口述**如何注册门面 MCP、如何 `extraDirs` 启用仓内 setup + produce（**不自动改配置文件**）  
4. 等你确认配好后，交接：先跑环境计划，再出片  

仓被拉下来后，里面已含门面 MCP 与 2 个出片相关 Skill。

## 4. 镜像地址

```text
https://github.com/GuiFeng410/OpenMontage-BootStrap.git
https://gitee.com/rory_-3232/open-montage-boot-strap.git
```

## 5. 配好之后

继续：[01-手动克隆与配置OpenClaw.md](./01-手动克隆与配置OpenClaw.md)（核对配置）→ [02](./02-环境检测与安装.md) → [03](./03-零Key最小出片.md)
