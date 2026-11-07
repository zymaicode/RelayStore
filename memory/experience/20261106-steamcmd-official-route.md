# 2026-11-06 · steamcmd 官方路线：不需要第三方 key 的本体获取

## 现象
hubcapmanifest 的免费 key 只能 Discord 登录生成；没有 Discord 账号 → 整条 C 路线的「取文件」环节直接卡死。
但北极星要的是「本体能跑」，不是「必须走非官方链路」。

## 根因
把「研究清单链路」和「拿到本体」混成一条路走了。实际上：
- 清单/凭据研究：需要第三方源（steamcmd.net / hubcap / manifesthub）
- 拿本体：只要自有 Steam 账号 + 官方 CDN，0 第三方依赖

## 处置
1. `tools/bin/steamcmd.exe`：Valve 官方引导包 774 KB，首次运行自更新 → 251 文件 / 151 MB；CDN `HEAD 200` 可达。
2. `tools/scripts/steam-download.ps1`：封装 `+force_install_dir +login +app_update <appid> validate +quit`；
   密码 / Steam Guard 走控制台交互，脚本不落盘；`-DryRun` 可先看命令再执行。
3. **硬守卫**：目标目录落在 `D:\Steam` 或其库路径时直接抛异常（D-016：未经授权不写用户 Steam）。
4. `.gitignore` 加 `src/data/body/`：本体几十 GB，绝不能进版本库或快照。

## 复用建议
- 遇到「第三方账号卡住」时先问：这个依赖是目标本身，还是只是某条实现路径？能换官方渠道就换，北极星优先。
- 需要人输入密码的脚本：只做参数拼装 + 透传 stdin，绝不读、存、打印凭据；同时用 `-DryRun` 让用户先看命令。
- 大产物目录（>1 GB）必须在落地前先加 `.gitignore`，否则迟早被误 add。
