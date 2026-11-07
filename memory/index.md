# 记忆索引

> 开工前扫一眼；新条目追加到对应分组末尾。

## 经验（experience）

| 日期 | 条目 | 一句话 |
|---|---|---|
| 2026-11-05 | [steam-local-environment](experience/20261105-steam-local-environment.md) | 本机 Steam 安装位置、账号、库、网络实测事实 |
| 2026-11-05 | [opensource-snapshot-cloning](experience/20261105-opensource-snapshot-cloning.md) | 7 仓库浅克隆实测：6 成功 1 个 404，Size 与耗时数据 |
| 2026-11-05 | [trace-deleted-repo-mirrors](experience/20261105-trace-deleted-repo-mirrors.md) | 仓库被删后如何用 commit 作者检索找到存世镜像（fylsdy 案例） |
| 2026-11-05 | [manifest-source-chain](experience/20261105-manifest-source-chain.md) | 三条清单获取路线对比与 C 路线端点（steamcmd / hubcap / manifesthub1） |
| 2026-11-06 | [scope-clause-removal](experience/20261106-scope-clause-removal.md) | 一次清掉散在 4 个文件里的范围限制条款：换句不删段 + 决策日志标废止 |
| 2026-11-06 | [northstar-conflict-audit](experience/20261106-northstar-conflict-audit.md) | 目标升级后按北极星扫冲突约定：只读/上限/限速一律改成「可做 + 可回滚」 |
| 2026-11-06 | [acf-parser-vdf](experience/20261106-acf-parser-vdf.md) | 手写 VDF 词法器解析 appmanifest：行号报错 + 先红后绿 + 修掉「0 用例也过门禁」 |
| 2026-11-06 | [m1-batch](experience/20261106-m1-batch.md) | M1 收口：形态按值判断、Lua 只改 id 行、幂等靠唯一键、降级留 attempts；快照 0 个 .lua |
| 2026-11-06 | [hubcap-key-tooling](experience/20261106-hubcap-key-tooling.md) | 只差本人登录的凭据类任务：把后续全流程做成一条命令 + 掩码输出 |
| 2026-11-06 | [steamcmd-official-route](experience/20261106-steamcmd-official-route.md) | 第三方 key 卡住时切官方 steamcmd：密码走控制台、硬守卫不写 D:\Steam |
| 2026-11-06 | [steam-login-state-audit](experience/20261106-steam-login-state-audit.md) | 登录态不可迁移（无 ssfn/ConnectCache）；config.vdf 里有 48 个 depot key |
| 2026-11-06 | [unowned-direct-link](experience/20261106-unowned-direct-link.md) | 未购买游戏直链：manifest/chunk 免鉴权可下，卡在 chunk 的 AES+LZMA 参数 |
| 2026-11-06 | [directlink-e2e](experience/20261106-directlink-e2e.md) | 直链端到端打通：分段 manifest、字段 6、ECB-IV+CBC、zstd 子进程，sha1 命中 |
| 2026-11-06 | [restore-depot](experience/20261106-restore-depot.md) | 整 depot 还原：匿名 appinfo 取 gid、openssl 加速 AES、VZip 无 EOS、目录项处理 |
| 2026-11-06 | [restore-app-pipeline](experience/20261106-restore-app-pipeline.md) | restore-app 工程化：状态枚举、报告不粉饰、Keyring 容错、镜像回退留证 |
| 2026-11-06 | [full-app-restore](experience/20261106-full-app-restore.md) | 100% 整 app：多端点镜像、key 合并、retry-from；完整口径 = delta 0 且无 skipped |
| 2026-11-06 | [manifest-coverage](experience/20261106-manifest-coverage.md) | 覆盖率实测：key 高、当前 gid 低；任意 build 回退把 CS2 6→93%、Cyberpunk 0→100% |
| 2026-11-06 | [pbz-coverage-expand](experience/20261106-pbz-coverage-expand.md) | 影之刃零全渠道 0 命中：新作时间差；coverage 命令只读判定 |
| 2026-11-06 | [prior-art](experience/20261106-prior-art.md) | 生态同构（DepotDownloader/ManifestHub/SFF）；钥匙不可算；steamtools.games 实测 not_in_db |
| 2026-11-06 | [borrow-ecosystem](experience/20261106-borrow-ecosystem.md) | steamtools 探针 / Hubcap 接入 / keys-sync；URLError≠HTTPError、语料失效降级 |
| 2026-11-06 | [pan-share-eval](experience/20261106-pan-share-eval.md) | 网盘学习版评估三问：能校验/合逻辑/装得下；本次不采用 |
| 2026-11-06 | [xunlei-share-listing](experience/20261106-xunlei-share-listing.md) | 迅雷分享免登录列举：captcha_sign 链、drive#folder、part001.exe 实锤 |
| 2026-11-06 | [xunlei-auth-throttle](experience/20261106-xunlei-auth-throttle.md) | 鉴权取 token、file_restore_own、非会员 10 KB/s 限速 |
| 2026-11-06 | [batch001-verify](experience/20261106-batch001-verify.md) | SFX→RAR5→bsdtar 免执行验证；drive 10MB/s vs share 0.04MB/s；coldloader |
| 2026-11-06 | [entropy](experience/20261106-entropy.md) | 分卷熵 8.000 / lzma 100.01%：极限压缩无效 |
| 2026-11-06 | [distribution-sources](experience/20261106-distribution-sources.md) | B2/R2/123云盘/Gofile/Pixeldrain 对比；多源安装器架构 |
| 2026-11-06 | [steamkit-probe](experience/20261106-steamkit-probe.md) | SteamKit 探测工具落地；本机 NoConnection，steamcmd 对照正常 |
| 2026-11-06 | [index-expansion-negative](experience/20261106-index-expansion-negative.md) | 多仓库扩索引收益≈0；转向并行/批量/缓存 |
| 2026-11-06 | [sidecar](experience/20261106-sidecar.md) | GUI 契约：HTTP+JSON-RPC+SSE、token、Job/取消模型 |
| 2026-11-06 | [mvp-e2e](experience/20261106-mvp-e2e.md) | MVP 跑通：Web UI 托管、480 实测、改码要重启 sidecar |
| 2026-11-06 | [go-core-bench](experience/20261106-go-core-bench.md) | Go 内核：0.62ms vs Python 39ms，快 63× 但只占墙钟 5% |
| 2026-11-06 | [go-full-core](experience/20261106-go-full-core.md) | Go 完整内核 10.12 MB，manifest+restore 与 Python 逐字节一致 |
| 2026-11-06 | [go-client](experience/20261106-go-client.md) | Go 全量客户端打通；按 Offset 组装、VZip uint32 两个坑 |
| 2026-11-06 | [wails-app](experience/20261106-wails-app.md) | Wails 桌面端 11.73 MB；go mod edit 的 @ 与 UIA 验证法 |

## 错误（errors）

| 日期 | 条目 | 一句话 |
|---|---|---|
| 2026-11-05 | [clone-404-handling](errors/20261105-clone-404-handling.md) | 上游仓库 404 时不要重试，改为记录 + 降级 + 找替代 |
| 2026-11-05 | [file-truncation-pitfall](errors/20261105-file-truncation-pitfall.md) | 用片段读取结果写回整文件 → 文件截断，门禁脚本静默失效 |
| 2026-11-06 | [false-L3-pass-detection](errors/20261106-false-L3-pass-detection.md) | 进程活着+有窗口标题≠启动成功：steam_api 报 Engine Error，判据要加截图 |

## 流程（playbooks）

| 日期 | 条目 | 一句话 |
|---|---|---|
| 2026-11-05 | [add-a-test](playbooks/20261105-add-a-test.md) | 从夹具到门禁的标准流程 |