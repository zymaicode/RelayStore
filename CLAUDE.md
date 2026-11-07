# CLAUDE.md — Steam Research 项目总纲

> 本文件是**项目最高约束**。任何 Agent（Claude / Codex / 其他）进入本仓库后，必须先读完本文件再动手。
> 本仓库为 **Steam 非官方获取链路（清单 / 直链 / Lua 配置）的技术研究与实践项目**；内容范围由用户授权界定。
> **终极目标（北极星）：产出目标游戏的游戏本体，并保证其在本机稳定运行 —— 这是本项目唯一的最终验收标准（见 §1.1）。**
> 详细分区规则、作业流程见 [AGENT.md](AGENT.md)。

---

## 1. 项目一句话

研究 Steam 的**清单（Manifest）体系**与**非官方下载链路**：清单来源、Lua 配置生成、直链分发、校验与回退，
把散落在多个 ManifestHub / 工具 / API 里的知识沉淀成本项目可复用的**本地目录库 + 探测与校验工具链**。

**授权范围**：内容获取范围由用户授权界定，本项目**不设**「仅限已购 / 免费内容」的范围限制；
保留的约束只剩工程与安全两类（令牌保管、路径规范、测试门禁），见 §7。

### 1.1 终极目标（北极星，优先级最高）

> **要产出的最终成果：目标游戏的「游戏本体」—— 完整、可直接启动、可玩的文件集，且能在本机稳定运行。**

- **一句话判据**：游戏能启动、能进游戏、能正常玩，没有缺文件 / 崩溃 / 校验失败。
  只把清单解析通、只生成 Lua、只拿到直链，都**不算完成**，只算中间手段。
- **优先级**：与任何子目标（研究结论、对比报告、工具链完备度）冲突时，一律让位于「本体可稳定运行」。
  研究是手段，本体可跑是目的；不为"研究得漂亮"而偏离终局。
- **可验证性**：每个里程碑都必须能回答"它让本体离可跑近了哪一步"，并在 `tests/reports/` 或 ARD 留下证据；
  无法验证的产出按**未完成**处理。
- **范围**：由用户授权界定（见 §1），不再限定已购 / 免费内容；§7 的工程与安全约束照旧生效。
- **落地路径**：本体产物默认落**独立目录**（可直接启动验证 L3/L4）；写入 `D:\Steam` 与其配置须**用户明确授权**，且先备份（§7.8）。
- **收敛路径**：M1 清单（拿到 appid / depot / gid / sha1 / size）→ M2 Lua（让工具认）→ M3 直链（拿到文件）
  → M4 组装校验 → **本体可稳定运行**。验收分五层（L1 结构完整 / L2 校验通过 / L3 可启动 / L4 可玩 / L5 可复现），
  **L4 及以上才算达标**，细则见 [AGENT.md](AGENT.md) 首章。

---

## 2. 分区地图（英文路径，禁止中文路径）

| 序号 | 分区 | 路径 | 英文名 | 职责 | 写入规则 |
|---|---|---|---|---|---|
| 1 | 主代码区 | `src\` | main | 项目主代码、CLI、库、数据模型 | 可写；**必须先过测试门禁** |
| 2 | 测试区 | `tests\` | tests | 全部测试与报告（子区见 §3） | 可写；默认先写测试 |
| 3 | 工具链区 | `tools\` | toolchain | 脚本、二进制、第三方工具、辅助程序 | 可写；脚本须可重放 |
| 4 | 开源项目区 | `opensource\` | opensource | 外部仓库**只读快照** | **禁止修改**；需要什么就复制出去 |
| 5 | 备份区 | `backup\` | backup | 本地版本库 + 敏感私有区（见 §4） | 分级管控 |
| 6 | 记忆取区 | `memory\` | memory | 项目经验、错误点、处理方法、可复用思路 | 可写；有坑必记 |
| 7 | 文档区 | `docs\` | docs | PRD / TRD / ARD | 可写；随进度更新 |

根目录文件：`CLAUDE.md`（本文件，总纲）、`AGENT.md`（作业手册）、`.gitignore`（根仓库忽略规则）。

### 2.1 六大区展开

```text
E:\vibe coding\steam\
├─ CLAUDE.md                  # 项目宪法（本文件）
├─ AGENT.md                   # Agent 作业手册
├─ docs\                      # 五项文档中的 PRD / TRD / ARD
│  ├─ PRD.md                  #   产品需求：做什么、给谁、验收标准
│  ├─ TRD.md                  #   技术设计：怎么做、模块 / 接口 / 数据 / 测试策略
│  └─ ARD.md                  #   进度与决策：里程碑、任务、决策、风险、会话记录
├─ src\                       # 1 主代码区
│  ├─ py\steam_research\      #   Python 主实现
│  └─ data\                   #   本地数据（catalog.db 等，不入版本库）
├─ tests\                     # 2 测试区
│  ├─ unit\ integration\ contract\ e2e\ compatibility\ security\
│  ├─ fixtures\               #   测试夹具（脱敏后的清单样本）
│  └─ reports\                #   测试报告输出（每次运行留档）
├─ tools\                     # 3 工具链区
│  ├─ scripts\                #   PowerShell 脚本（可重放）
│  └─ vendor\ bin\            #   下载的外部脚本 / 工具
├─ opensource\                # 4 开源项目区（只读）
│  ├─ ManifestHub-fylsdy\ …   #   见 opensource\README.md
│  └─ references\             #   非 git 资源（manifests.ps1、API 说明）
├─ backup\                    # 5 备份区
│  ├─ vcs\                    #   仿 GitHub 流程的本地版本库（已脱敏，可独立 git）
│  └─ private\                #   敏感 / 私人信息（**严禁推送远端**）
└─ memory\                    # 6 记忆取区
   ├─ index.md                #   记忆索引（先查这里）
   ├─ experience\             #   经验条目
   ├─ errors\                 #   错误点 + 处理方法
   ├─ playbooks\              #   可复用流程
   └─ templates\              #   条目模板
```

---

## 3. 测试区子区与门禁（最重要的一条规则）

未知功能、模块、接口、代码 —— **一律先测试**。未通过测试的代码，**严禁并入主代码区**污染项目。

| 子区 | 路径 | 负责什么 | 何时必须用 |
|---|---|---|---|
| 单元 | `tests\unit\` | 函数级、解析器、纯逻辑 | 任何新函数 |
| 集成 | `tests\integration\` | 模块间、文件读写、SQLite | 跨模块改动 |
| 契约 | `tests\contract\` | 外部源（GitHub raw / Morrenus / steamtools.games）响应格式 | 接入或改动外部 API |
| 端到端 | `tests\e2e\` | CLI 全链路（查询 → 取清单 → 下载 → 校验） | 发版前 |
| 兼容 | `tests\compatibility\` | 与 SteamTools / LMU / 各 ManifestHub 数据格式兼容 | 涉及 Lua / VDF 格式 |
| 安全 | `tests\security\` | 脱敏、路径穿越、SSRF、大文件、恶意清单 | 涉及下载 / 外部输入 |

**门禁（Gate）**：`src\` 的合并只有三个条件 —— ① 对应测试存在且通过；② `tests\reports\` 留下报告；
③ ARD.md 的任务状态已更新。缺一不可。

---

## 4. 备份区规则（两条铁律）

### 4.1 `backup\vcs\` — 本地源码版本备份（仿 GitHub 策略）
- 独立 git 仓库（`backup/vcs/.git`），**不配置任何 remote**，纯本地。
- 分支：`main`（稳定）/ `develop`（集成）/ `feature/<name>`（特性）/ `hotfix/<name>`；标签 `vX.Y.Z`。
- 内容：`src\` 与 `docs\` 的**脱敏快照**，由 `tools\scripts\backup-snapshot.ps1` 生成。
- **必须脱敏**：账号、路径中的用户名、token/cookie、Steam 登录凭据、私有 API key、机器名、内网地址一律不得入库。
  pre-commit 钩子（`backup\vcs\hooks\pre-commit`）会拦截疑似泄密内容。
- 用途：GitHub 推送失败 / 断网 / 远端被墙时的版本兜底，与远端仓库互不依赖。

### 4.2 `backup\private\` — 敏感与私人信息
- 存放：账号信息、凭据、私人笔记、法律/合规相关材料、真实用户数据。
- **严禁推送远端**：此区永不作为任何 remote 的源；根仓库 `.gitignore` 已排除；若单独建库，`git remote` 必须为空。
- 提交前自查：`tools\scripts\desensitize-scan.ps1` 应报 0 命中。

---

## 5. 记忆取区（memory）—— 少踩同一个坑

每次任务结束前问三句：**有没有新经验？有没有踩坑？下次怎么更快？** 有就落一条。

- 命名：`memory\experience\YYYYMMDD-短标题.md`、`memory\errors\YYYYMMDD-短标题.md`。
- 每条必须含：**现象 / 根因 / 处置 / 复用建议**（模板见 `memory\templates\`）。
- 开工前先看 `memory\index.md` 与 FAILURE 类错误条目，避免重复犯错。
- 记忆条目也要脱敏；含敏感内容时写进 `backup\private\`，memory 里只留指针。

---

## 6. 五项文档（本项目的文档契约）

| 文档 | 路径 | 回答什么问题 | 更新时机 |
|---|---|---|---|
| CLAUDE.md | `CLAUDE.md` | 项目宪法：分区、规则、门禁、北极星目标 | 规矩变化时 |
| AGENT.md | `AGENT.md` | Agent 怎么干活：流程、命令、禁止事项 | 流程变化时 |
| PRD | `docs\PRD.md` | 做什么、给谁做、验收标准、范围边界 | 需求变化时 |
| TRD | `docs\TRD.md` | 怎么做：架构、模块、接口、数据、测试策略 | 设计变化时 |
| ARD | `docs\ARD.md` | 进度与决策：里程碑、任务、决策日志、风险、会话记录 | **每次任务后**（强制） |

**文档即事实**：代码与文档冲突时，先改文档再改代码；ARD 是进度唯一可信来源。

---

## 7. 硬性禁止（违反即回滚）

1. 修改 `opensource\` 内任何文件（包括 `.git` 目录）；需要就直接复制到 `src\` 或 `tools\` 并登记来源。
2. 把 `backup\private\` 的内容推送到任何远端，或提交进 `backup\vcs\`。
3. 未经测试的新代码进入 `src\`。
4. 在路径、文件名、分支名中使用中文（文档正文可以用中文）。
5. 把凭据、cookie、token 写进任何被追踪文件；只能放 `backup\private\` 或环境变量。
6. 自动执行来源不明的脚本（`manifests.ps1` 等外部脚本必须先在 `tools\vendor\` 审阅，再离线运行）。
7. 把 `depotkeys.json` / `appaccesstokens.json` 等解密与令牌数据写进被追踪文件或外发（只放 `backup\private\`）。
8. **未经用户明确授权**，写入或修改本机 `D:\Steam` 与其配置（`steamapps\`、`config\`、`userdata\`、注册表 `HKCU\...\Valve\Steam`）；
   本体产物默认落**独立目录**；获授权后写入前仍须备份 `steamapps\*.acf` / `libraryfolders.vdf` 并留一键还原。

---

## 8. 当前阶段

- 阶段：**M1 清单解析与索引**（M0 基建已完成；`acf` 解析器 M1-T01 已交付）
- 下一步：M1-T04 `catalog.py` + M1-T02 四仓库 JSON 采样（见 [docs/ARD.md](docs/ARD.md) 任务表）
- 环境事实：Steam 客户端 `D:\Steam`（11.15.70.27），库仅一个，账号 zymikly；详见 `memory\experience\` 首条记录。
- 北极星：**产出可稳定运行的目标游戏本体**（§1.1）。M1~M4 全部服务于这一条，每个阶段性成果都必须能回答"离本体可跑近了哪一步"。