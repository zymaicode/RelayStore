# tools — 工具链区

安放**可重放**的辅助脚本与经过审阅的第三方工具。不放业务主代码。

## 结构

```text
tools/
  scripts/                     # 本项目自研 PowerShell 脚本
    env-check.ps1              # 环境 / 分区自检
    clone-opensource.ps1       # 刷新开源快照
    set-readonly.ps1           # 开源区只读属性
    import-from-opensource.ps1 # 从开源区复制代码并写来源头
    desensitize-scan.ps1       # 脱敏扫描
    backup-snapshot.ps1        # 脱敏快照 -> backup/vcs 提交
    run-tests.ps1              # 跑测试 + 落报告
    gate-check.ps1             # 合并门禁
  vendor/                      # 下载的外部脚本（先审阅再离线执行）
  bin/                         # 便携工具（如 LuaTools 解包件）
```

## 规则

1. 每个脚本必须可重复执行（幂等）、路径从 `$PSScriptRoot` 推导、不写死盘符。
2. 外部下载物先入 `vendor/`，**禁止** `iex (irm ...)` 直接执行；至少有 `-WhatIf` 或手工审阅记录。
3. 脚本改动视同代码：改完先跑 `env-check.ps1` + 相关测试。
4. `vendor/` 与 `bin/` 不入版本库（根 `.gitignore` 已排除）。
