# 开源快照浅克隆实测（M0）

- 日期：2026-11-05
- 类型：经验
- 标签：#git #opensource #network

## 背景
项目需要把 7 个 ManifestHub / 工具仓库收进 `opensource/` 作只读参考。

## 做法
`git clone --depth 1 --single-branch --no-tags`（脚本 `tools/scripts/clone-opensource.ps1`）。
网络为直连 GitHub（未配置代理），实测可用。

## 实测结果

| 仓库 | 结果 | 体积 / 耗时 |
|---|---|---|
| steamtools-games/ManifestHub3 | ✅ | 24 MB / 5.6s |
| SteamAutoCracks/ManifestHub | ✅ | 23.3 MB / 4.8s |
| SSMGAlt/ManifestHub2 | ✅ | 23.3 MB / 6.4s |
| trionine/ManifestHub | ✅ | 9 MB / 3.5s |
| madoiscool/LuaTools | ✅ | 4.4 MB / 3.6s |
| fairy-root/lua-manifest-updater | ✅ | 0.3 MB / 2.6s |
| fylsdy/ManifestHub | ❌ 404 | Repository not found |
| luatools.vercel.app/manifests.ps1 | ✅ | 22.6 KB |

## 复用建议
- 清单类仓库单个约 20~25 MB，全量刷新 < 1 分钟，可放心 `-Force` 重刷。
- 404 不等于网络问题：先 `git ls-remote` 或 GitHub API 确认，再决定是否找镜像（见 errors 条目）。
- 深浅克隆用 `-c core.longpaths=true`，避免 Windows 长路径失败。
