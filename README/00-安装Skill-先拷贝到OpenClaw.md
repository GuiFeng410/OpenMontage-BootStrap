# 00 — 安装 Skill：先拷贝到 OpenClaw

适用：机器上**还没有** OpenMontage 仓库，只想先在 OpenClaw 里装一个引导 Skill。

## 1. 拷贝什么

从已发布的 BootStrap 仓（或本机已有副本）复制整个目录：

```text
openmontage/skills/openmontage-bootstrap-installer/
```

到 OpenClaw **用户本地独立 Skill 目录**（路径以你的 OpenClaw/eClaw 为准，例如 `~/.openclaw/skills/`）。

启用 Skill：`openmontage-bootstrap-installer`。

此时**不必**先配置仓库内 MCP（由安装流程口述）。

## 2. 对 Agent 说什么

> 我想生成视频 / 做个动画解说，按 BootStrap 安装流程来。

## 3. 安装 Skill 会做什么

1. 问你要把仓库放到哪个文件夹 `<TARGET>`  
2. 引导（或代跑）`git clone`：先 GitHub，失败用 Gitee  
3. **只口述**注册 **4 个 MCP**（门面 + TTS/图/视频 providers）并启用 **3 个 Skill**（setup / produce / providers）  
4. **付费 Key 安装时不必填**；MCP 先能启动即可  
5. 交接：先 setup → produce 零 Key 出片；需要收费能力时再填 Key（Skill03 / [04](./04-收费Providers接入.md)）

## 4. 镜像地址

```text
https://github.com/GuiFeng410/OpenMontage-BootStrap.git
https://gitee.com/rory_-3232/open-montage-boot-strap.git
```

## 5. 配好之后

继续：[01](./01-手动克隆与配置OpenClaw.md)（核对）→ [02](./02-环境检测与安装.md) → [03](./03-零Key最小出片.md) → 需要时 [04](./04-收费Providers接入.md)（只填 Key）
