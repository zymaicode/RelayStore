# PRD — Steam 非官方获取链路研究

| 项目 | 内容 |
|---|---|
| 文档 | 五项文档之 PRD（产品需求） |
| 版本 | v0.1（M0 基建期） |
| 日期 | 2026-11-05 |
| 关联 | [TRD](TRD.md) 技术设计 · [ARD](ARD.md) 进度与决策 |
| 状态 | 基线（Baseline） |

---

## 1. 背景

Steam 客户端下载游戏依赖**清单（Manifest）**描述每个 Depot 的文件列表与内容哈希；社区围绕这套体系
发展出多条「非官方」获取路径：ManifestHub 类的清单仓库、Lua/SteamTools 配置、第三方清单 API、
以及带 Web 界面的查询前端。这些资源分散、格式不一、容易失效（仓库 404、API 限流），且缺乏统一的
**来源、时效、完整性**判断依据。

本项目要把这套链路**搞明白、沉淀下来、可复现**：建立本地清单目录库，做多源探测与回退，
统一解析不同格式，产出对比报告与校验能力，为后续内容管理与兼容性研究提供基础设施。

## 2. 目标（研究问题）

| 编号 | 问题 | 期望产出 |
|---|---|---|
| Q1 | 四个 ManifestHub 仓库的数据组织、字段、覆盖度差异是什么？ | 仓库对比矩阵（docs 内） |
| Q2 | 清单（appid / depot / manifest gid / sha1 / size）如何从各源稳定取到？ | 多源采集器 + 回退链 |
| Q3 | Lua 配置（SteamTools 格式）与 manifest 的映射关系是什么？ | 解析器 + 生成器 |
| Q4 | 直链 URL 的结构与可校验点有哪些（域名、路径、哈希、过期）？ | 直链结构说明 + 解析器 |
| Q5 | 源失效时如何快速发现并切换？ | 源健康度探测 + 报告 |

## 3. 用户与场景

- **主要用户**：项目研究者本人（单机、Windows 11、Steam 客户端在 `D:\Steam`）。
- **次要用户**：未来接手本项目的 Agent（依赖本 PRD / TRD / ARD 与 memory 快速接手）。
- **典型场景**：
  1. 查某个 appid 的清单在 4 个仓库里分别有没有、哪份最新、字段是否冲突。
  2. 某个仓库 404 / API 限流时，自动回退到下一源并记录降级。
  3. 手上有 appmanifest，想核对 depot 与 gid 是否一致、哈希是否对得上。
  4. 想为某 appid 生成/更新 Lua 配置，先离线校验再使用。

## 4. 范围

### 4.1 范围内（In scope）
- 清单数据的**采集、索引、解析、比对、校验、报告**。
- 4 个 ManifestHub 仓库 + Lua 工具 + 第三方 API + Web 前端的**行为研究与离线化封装**。
- 本机 Steam 客户端数据解析（`D:\Steam\steamapps\*.acf`、`libraryfolders.vdf`）；**未经用户授权不写回、不修改**。
- Lua 配置的生成与更新（LMU 等价能力）。

### 4.2 边界（操作性约束，非授权范围限制）
- 内容获取范围由用户授权界定；本文件**不设**「仅限已购 / 免费内容」的范围限制。
- `D:\Steam` 与其配置（`steamapps` / `config` / `userdata` / 注册表）**未经用户明确授权严禁写入或修改**；授权后写入前先备份 `steamapps/*.acf`、`libraryfolders.vdf`，留回滚副本。
- 凭据 / 令牌 / 私有 key 只放 `backup/private/`，不入版本库、不外发。
- 不做账号共享、代登录、Steam 凭据托管（账号安全）。

### 4.3 数据源基线（2026-11-05 定版，D-010）

| 环节 | 选型 | 理由 | 备选 |
|---|---|---|---|
| appid → depot → manifest gid | `api.steamcmd.net/v1/info/<appid>` | 免鉴权、免 key、直接给 gid；实测 L4D2 9 个 depot | 本地 fixture / manifesthub1 |
| depot+manifest → `.manifest` 文件 | `hubcapmanifest.com` API（Morrenus 系） | 主流通行链路；免费 key 需 Discord 登录自助生成，按天配额 | `manifesthub1` API、`qwe213312` raw |
| app 访问令牌 / depot 密钥 | `opensource/ManifestHub-*`、fylsdy 镜像 | 离线可得，用于内容访问阶段 | 官方 Steam API（自有账号） |
| 加密清单库（ManifestAutoUpdate） | **不接入** | 加密 + 需专用工具 + 分支漂移 | M3 再评估 |

> 结论：项目不再依赖已消失的 fylsdy 仓库；清单链路以公开 API 为主，静态仓库只作凭据与回放。
## 5. 功能需求

优先级：P0 必须（M1 内）/ P1 应该 / P2 可选。

| ID | 功能 | 优先级 | 验收标准（可测） |
|---|---|---|---|
| F1 | **清单索引与检索**：把多源数据归一为 `appid / depot / gid / sha1 / size / source / fetched_at` 索引 | P0 | 给定 appid，CLI 1 条命令返回 ≥1 条带来源与时间的记录（gid 来自 steamcmd）；无网络时读本地 fixture/cache 仍可用 |
| F2 | **多源采集与回退**：steamcmd → 本地 cache → manifesthub1 → hubcap → raw，失败自动降级并留痕（D-011） | P0 | 断网时命令不崩，输出「降级到 cache」；日志含每次尝试与耗时 |
| F3 | **格式解析**：`.acf`（VDF）、ManifestHub JSON、SteamTools Lua 三格式统一解析 | P0 | 三格式样本各 ≥3 个 fixture 解析通过；字段缺失有明确报错 |
| F4 | **Lua 生成/更新**：给定 appid + depot 集合生成 SteamTools 兼容 Lua；支持更新已有 Lua 的 manifest id | P0 | 生成文件可被现有工具读取（见 `tests/compatibility/`）；更新后 diff 仅含 id 行 |
| F5 | **直链结构解析**：解析 depot 内容 URL（host / path / gid / sha1 / 大小），产出结构说明 | P1 | 对样本 URL 输出结构化字段；非法 URL 有清晰错误码 |
| F6 | **完整性校验**：SHA-1 与 size 比对，报告不一致项 | P0 | 人为篡改 1 字节 → 校验报告标记 FAIL；一致 → PASS |
| F7 | **对比报告**：跨仓库差异（有无、最新 gid、字段冲突）+ 源健康度 | P1 | 一条命令生成 `tests/reports/report-*.md`，含覆盖率与降级统计 |
| F8 | **本地目录库**：SQLite 持久化索引与历史 | P1 | 重复采集幂等（不产生重复行）；可按时间回溯 |

## 6. 非功能需求

| 类别 | 要求 |
|---|---|
| 平台 | Windows 11（本机），PowerShell 7；Python 3.12 |
| 依赖 | 核心功能仅标准库；测试用 pytest；不引入需付费 key 的服务 |
| 性能 | 冷启动查询 < 2s（本地缓存命中）；单次全量采集 < 10 分钟 |
| 可靠性 | 幂等；外部失败可回放（响应落盘）；任何异常有退出码与可读错误 |
| 安全 | 不打印凭据；URL 参数脱敏；路径穿越防护；下载后按清单 size/hash 校验；磁盘余量检查（单文件不设硬上限） |
| 可审计 | 每次采集记录 source、url、http code、耗时、hash |
| 可移植 | 路径全部相对项目根；不在代码里硬编码 `E:\vibe coding\steam` |

## 7. 数据资产

| 资产 | 位置 | 说明 |
|---|---|---|
| 开源快照 | `opensource/` | 7 个仓库 + references，只读 |
| 本地缓存 | `src/data/cache/` | 原始响应，按 sha256 命名，git 忽略 |
| 目录库 | `src/data/catalog.db` | SQLite，git 忽略，可重建 |
| 测试夹具 | `tests/fixtures/` | 脱敏样本，可入版本库 |
| 契约夹具 | `tests/fixtures/contract/` | steamcmd appinfo 等脱敏样本（已含 550 / 3240220） |
| acf 夹具 | `tests/fixtures/acf/` | 3 份脱敏 appmanifest（550 / 3240220 / 228980）+ 3 份畸形样本 |
| 报告 | `tests/reports/` | 测试与研究报告留档 |

## 8. 指标（验收口径）

- 覆盖率：目标库内 appid 在 4 源中的**命中率**（报告输出）。
- 源可用性：连续 7 次探测成功率，低于 70% 标记为「不稳定」。
- 质量：单元 + 集成 + 契约测试全绿；门禁 100% 通过才允许进 `src`。
- 一致性：同一 appid 多源 gid 冲突时必须列出，不静默取其一。

## 9. 里程碑（详见 ARD 任务表）

| 里程碑 | 内容 | 退出条件 |
|---|---|---|
| M0 | 基建：分区、文档、开源快照、脚本 | 本 PRD/TRD/ARD 落盘，脚本可跑 |
| M1 | 清单解析与索引（F1/F2/F3/F6） | 单元 + 集成 + 契约测试绿 |
| M2 | Lua 生成与兼容（F4） | 兼容测试绿，生成物可被工具读取 |
| M3 | 直链与健康度（F5/F7/F8） | 端到端跑通，报告产出 |
| M4 | 打磨与文档冻结 | 全量回归绿，ARD 收口 |

## 10. 风险与缓解

| 风险 | 影响 | 应对 |
|---|---|---|
| 上游仓库消失/改名（如 `fylsdy/ManifestHub` 已 404） | 数据断供 | 多源 + 本地快照兜底，记录失效日期 |
| 第三方 API 限流/封禁 | 采集失败 | 默认 1 req/s + 退避重试 + 配额与缓存优先；内容下载速率可配置 |
| 清单被投毒（错误哈希/恶意路径） | 污染本地数据 | 强制校验 + 路径白名单 + 安全测试 |
| 本机账号信息泄露 | 隐私 | 脱敏扫描 + private 分区隔离 |

## 11. 未决问题（Open Questions）

1. `fylsdy/ManifestHub` 404 后的替代源是哪个（镜像 / fork / 其他组织）？—— 待 ARD 决策。
2. Morrenus API 的具体端点与限额（需加入 `backup/private/` 记录令牌策略，若有）。
3. 是否需要支持 Linux（Steam Deck）路径格式？—— 暂按 Windows。
4. 清单数据的保留周期与增量更新策略（全量 vs 增量）。