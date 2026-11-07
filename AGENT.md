# AGENT.md — Agent 作业手册

> 配套 [CLAUDE.md](CLAUDE.md) 使用：CLAUDE.md 讲**规矩**，本文件讲**动作**。
> 未读完 CLAUDE.md 不得开始任务；本手册与 CLAUDE.md 冲突时以 CLAUDE.md 为准。
> **北极星目标：产出目标游戏的游戏本体，并让它稳定运行。本手册所有动作都为这一条服务。**

---

## 北极星目标与验收口径（先读这一条）

**最终交付物 = 目标游戏的游戏本体（完整可玩文件集），且在本机稳定运行。**
研究、解析、生成、校验、报告都是手段，不是交付；"文档写完""清单通了"都不算成果。

### 验收分层（做到哪一层就报哪一层，不许含糊）

| 层级 | 判据 | 必须留下的证据（落盘） |
|---|---|---|
| L1 结构完整 | depot / 文件清单齐全，无缺文件 | 校验清单报告，存 `tests/reports/` |
| L2 校验通过 | sha1 / size 与清单逐项一致 | `verify` 输出 0 失败 |
| L3 可启动 | 进程能拉起，无缺 dll / 依赖 / 启动器报错 | 启动日志（含命令与退出码） |
| L4 可玩 | 进主界面 / 进关卡，关键流程无崩溃 | 运行记录：连续 ≥ 10 分钟或到首个存档点 |
| L5 可复现 | 同步骤重跑仍通过；重启 / 断网后仍可运行 | 复现记录 + `backup/vcs` 快照 tag |

- **L4 及以上才算「可稳定运行」**。只到 L1/L2 的任务状态只能是 `doing`；写 `done` 而不给 L4 证据，视为造假。
- 每次汇报必须写清"当前层级 + 证据路径"，禁止用"基本完成""应该能跑"替代。
- 授权范围由用户界定（CLAUDE.md §1），本手册不设内容获取范围限制；§7 的工程与安全约束照旧生效。
- 落地优先级：**独立产物目录可直接启动验证（L3/L4）** → 只有拿到用户授权才写 `D:\Steam`，且写前备份。

### 每个任务开工前必须回答的三个问题

1. 这一步把本体推进到哪一层（L1~L5）？
2. 完成判据是什么？用哪条命令 / 哪个报告 / 哪个截图证明？
3. 失败怎么回退？是否已写进 ARD 风险表？

---

## 0. 30 秒开工检查单

```text
[ ] 读 CLAUDE.md（分区 / 门禁 / 禁止事项）
[ ] 读 docs/ARD.md 的「任务表」，认领一个 ready 任务（改状态为 doing）
[ ] 定层级：本任务把「本体可稳定运行」推进到 L1~L5 的哪一层，完成判据写进 ARD
[ ] 翻 memory/index.md 与 memory/errors/，看有没有踩过的同类坑
[ ] 确认要动的文件落在哪个分区，是否越界（opensource 只读 / private 禁推）
[ ] 写测试 → 跑测试 → 才写 src 主代码
[ ] 收尾：更新 ARD、写 memory 条目、执行一次备份快照
```

---

## 1. 工作流（六步法）

```text
1 认领     ARD 里把任务状态 pending -> doing，写一句打算怎么做
2 夹具     在 tests/fixtures/ 造最小样本（脱敏！）
3 测试     先写 tests/<子区>/test_xxx.py，运行并确认「红」
4 实现     在 src/ 写最小实现，跑测试到「绿」
5 门禁     tools/scripts/gate-check.ps1 通过（测试 + 报告 + ARD 三者齐全）
6 沉淀     更新 ARD / memory，跑 backup-snapshot.ps1 落一次本地版本
```

**测试没红过就写实现 = 没有测试。** 只跑测试不落报告 = 门禁不通过。

---

## 2. 分区边界速查

| 想做什么 | 正确做法 | 错误做法 |
|---|---|---|
| 用 opensource 里某个函数 | 复制到 `src/py/steam_research/vendor_ref/`，首行注明来源 repo + commit | 直接 import opensource 路径 / 打补丁 |
| 试一个新工具 | 下载到 `tools/vendor/`，先人工审阅再离线跑 | 直接 `iex` 网页脚本 |
| 存账号密码 | `backup/private/` 或环境变量 `$env:XXX` | 写进 src / docs / tests |
| 记录经验 | `memory/experience/YYYYMMDD-短标题.md` | 只在聊天里说一句 |
| 改版本 | `backup/vcs` 建 `feature/xxx` 分支 + 快照脚本 | 直接改 main / 手动复制文件夹 |

---

## 3. 命名与代码规范

- 目录、文件名、分支名：**英文 + 短横线**（`lua-manifest-updater`、`source-probe`），禁止中文与空格。
- Python：3.12，`src/py/steam_research/` 包，模块名小写下划线；公开函数写类型注解与 docstring。
- 依赖：优先标准库（`urllib` / `sqlite3` / `hashlib` / `json`）；确需第三方（如 `pytest`）写入 `src/py/requirements.txt` 并说明理由。
- 网络访问：统一走 `src/py/steam_research/net.py`（超时、重试、限速、UA、代理读环境变量），禁止散落 `urlopen`。
- 日志：`logging`，不打印凭据、cookie、完整 URL 查询串。
- 提交信息：`type(scope): subject`（`feat|fix|test|docs|chore|refactor`），正文写「为什么」。

---

## 4. 外部数据源策略（研究核心）

来源优先级与回退链（TRD §5 有接口定义）：

```text
本地快照 opensource/*  ->  GitHub raw（4 个 ManifestHub 仓库）
                        ->  Morrenus API（每日限额，备用）
                        ->  steamtools.games（人工核对，不自动抓）
```

- 先查本地快照，命中就不联网（省限额、可复现）。
- 联网默认限速：API / 元数据同一域名 `>= 1s` 间隔；内容文件下载的并发与间隔走配置（按源配额和带宽放开），全部指数退避，最多 3 次重试。
- 所有外部响应**先落盘再解析**（`src/data/cache/`，git 忽略），便于回放与契约测试。
- 契约测试用 `tests/fixtures/contract/` 的脱敏样本，不依赖实时网络（CI 可跑）。
- M0 阶段已知事实（2026-11-05 实测）：
  - `fylsdy/ManifestHub` 返回 404（仓库不存在/已改名/私有）—— 需另找镜像，勿反复重试。
  - `steamtools-games/ManifestHub3`、`SteamAutoCracks/ManifestHub`、`SSMGAlt/ManifestHub2`、`trionine/ManifestHub`、`fairy-root/lua-manifest-updater`、`madoiscool/LuaTools` 克隆成功（depth=1）。
  - `https://luatools.vercel.app/manifests.ps1` 抓取成功（22 KB），存于 `opensource/references/manifests.ps1`。

---

## 5. 常用命令

```powershell
# 环境自检（git / python / 网络 / 分区完整性）
pwsh -File tools\scripts\env-check.ps1

# 跑全部测试并落报告（门禁用）
pwsh -File tools\scripts\run-tests.ps1 -All

# 只跑某个子区
pwsh -File tools\scripts\run-tests.ps1 -Area unit

# 合并前门禁（测试通过 + 报告存在 + ARD 已更新）
pwsh -File tools\scripts\gate-check.ps1 -TaskId M1-T01

# 脱敏扫描（备份 / private 提交前）
pwsh -File tools\scripts\desensitize-scan.ps1 -Path .\src

# 本地版本快照（脱敏后提交到 backup/vcs）
pwsh -File tools\scripts\backup-snapshot.ps1 -Message "feat(manifest): parse acf"

# 从开源区复制代码（自动记录来源 commit）
pwsh -File tools\scripts\import-from-opensource.ps1 -Repo ManifestHub-trionine -Path src/lib/foo.js -Target src\py\steam_research\vendor_ref\foo.js
```

`python` 直接调用：`python -m pytest tests\unit -q`（在项目根目录执行）。

---

## 6. 记忆取区用法（沉淀，不重复犯错）

每次任务收尾落 0~2 条，宁缺毋滥：

- **经验**：`memory/experience/YYYYMMDD-<slug>.md` —— 可复用的做法、踩通的外部源、有效的命令组合。
- **错误**：`memory/errors/YYYYMMDD-<slug>.md` —— 现象 / 根因 / 处置 / 防复发。
- 写完在 `memory/index.md` 加一行指针（标题 + 一句话 + 日期），否则等于没写。
- 同类错误第 2 次出现时，必须把它升级成 `tests/security/` 或 `tests/contract/` 的回归用例。

---

## 7. 备份与恢复

- 快照内容：`src\`、`docs\`、`tests\`（自动脱敏：绝对路径、用户名、token、cookie、SteamID、邮箱）。
- 分支模型：`main` 稳定可发布 / `develop` 集成分支 / `feature/*` 特性 / `hotfix/*` 救火。
- 恢复：`cd backup/vcs` → `git log --oneline` → `git checkout <tag-or-commit> -- src docs` → 复制回项目根。
- **GitHub 推送失败时**：先 `backup-snapshot.ps1` 落本地版本并打 tag，再排查网络（直连是否可用、是否需要代理）；远端恢复后以本地 tag 为准对齐。
- `backup/private/` 永不进入 `vcs`；若必须记录敏感上下文，写 private 并在 memory 留指针。

---

## 8. 交接模板（任务结束时贴进 ARD 会话记录）

```text
[日期] 任务 <ID> <标题>
- 做了什么：...
- 改了哪些文件：src/... tests/... docs/...
- 北极星层级：L1~L5 的哪一层；证据路径：...
- 测试：<子区> 通过 N 条；报告 tests/reports/<file>
- 遗留 / 风险：...
- 记忆条目：memory/experience/<file>（如无写「无」）
```

---

## 9. 绝对不做

1. 不修改 `opensource/` 里任何东西（含 `.git`）。
2. 不把 `backup/private/` 推到远端，也不让它进 `backup/vcs`。
3. 不让未过测试的代码进 `src/`。
4. 不在路径 / 分支 / 文件名里用中文。
5. 不在被追踪文件里写凭据；不用明文密码登录任何服务。
6. 不自动执行下载来的脚本（`manifests.ps1` 等）。
7. 未经你明确授权，绝不写入或修改本机 `D:\Steam` 与配置（`steamapps` / `config` / `userdata` / 注册表）；产物先落独立目录，授权后写入前先备份并留回滚点。
8. 不把限速写成不可调的硬约束（Morrenus 有每日限额）：并发 / 速率走配置，全量下载按源配额放开，失败走退避回退。
