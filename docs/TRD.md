# TRD — 技术设计

| 项目 | 内容 |
|---|---|
| 文档 | 五项文档之 TRD（技术设计） |
| 版本 | v0.1（M0） |
| 日期 | 2026-11-05 |
| 关联 | [PRD](PRD.md) 需求 · [ARD](ARD.md) 进度 · [CLAUDE.md](../CLAUDE.md) 分区规则 |
| 状态 | 基线 |

---

## 1. 设计原则

1. **离线优先**：本地快照/缓存优先，网络只是补充源。
2. **单一定义、单一出口**：所有网络访问经 `net.py`；所有源实现同一 Provider 协议。
3. **可回放**：外部响应先落盘（`cache/`）再解析，契约测试用脱敏样本。
4. **失败显式**：降级、缺失、冲突都必须出现在输出与日志里，禁止静默兜底。
5. **标准库优先**：核心逻辑零第三方依赖，便于长期维护与审计。

## 2. 总体架构

```text
                +--------------------------------------------------+
   CLI          |  cli.py  (argparse: query / fetch / lua / verify |
                |           / report / doctor)                     |
                +---------------------+----------------------------+
                                      |
                +---------------------v----------------------------+
   Domain       |  catalog (SQLite)   manifest (acf/json/lua)       |
                |  lua_gen            verify (sha1/size)            |
                |  report (md/json)                                 |
                +---------------------+----------------------------+
                                      |
                +---------------------v----------------------------+
   Sources      |  SourceProvider interface                        |
                |    LocalSnapshot | GitHubRaw | Morrenus | Manual  |
                |  resolver: 优先级链 + 健康度 + 限速 + 重试        |
                +---------------------+----------------------------+
                                      |
                +---------------------v----------------------------+
   Infra        |  net.py (timeout/retry/rate-limit/proxy)          |
                |  cache.py (sha256 blobs, TTL)                     |
                |  paths.py (项目根解析, 相对路径)                   |
                +--------------------------------------------------+
```

## 3. 代码布局（主代码区）

```text
src/py/
  requirements.txt
  steam_research/
    __init__.py
    cli.py            # 入口：query / appinfo / coverage / directlink / restore-app / keys-* / index-build ...
    model.py          # dataclass: AppRecord / ManifestRef / AccessToken / DepotKey
    catalog.py        # SQLite schema + 幂等 upsert + query + history
    resolver.py       # 优先级链、降级、attempts 日志、cache 兜底
    verify.py         # SHA-1 / size 校验 + safe_join（路径穿越 / ADS 防护）
    keys.py           # Keyring：JSON 语料 / config.vdf / key.vdf / 合并去重
    coverage.py       # 只读可用性判定（appinfo + key + 索引 + HEAD + steamtools 探针）
    pipeline.py       # app 级编排：逐 depot 隔离失败 + 结构化报告（ok/skipped/missing_*/failed）
    restore.py        # chunk 并发下载 + 内容寻址缓存 + 按 offset 组装 + 双层 sha1
    depot.py          # AES-256（ECB-IV + CBC/PKCS7）+ VZip / Zip / VZstd 解码
    manifest.py       # 分段容器 + protobuf：FileMapping / ChunkData / linktarget
    directlink.py     # 清单 / chunk 直链构造、下载与校验
    parsers/
      __init__.py
      acf.py          # Steam appmanifest_*.acf（VDF 子集，错误带行号）
      hub_json.py     # ManifestHub JSON：tokens / depot_keys / manifest_map / record
      lua.py          # SteamTools Lua 键值块（解析 + 只改 gid/size 行）
      vdf.py          # 通用 VDF（含转义与行号错误）
      steamcmd.py     # api.steamcmd.net appinfo -> gid
    sources/
      __init__.py
      appinfo.py      # 匿名 steamcmd app_info_print -> depots + gid（未购买 app 可用）
      cdn.py          # chunk 直链（akamaized 等）与主机回退
      hubcap.py       # hubcapmanifest 生成 / 下载 .manifest（内容寻址缓存）
      manifest_mirror.py  # 多仓库 x 多端点（raw / jsDelivr / githack）manifest 回退
      manifest_index.py   # depot -> 可用 gids 索引（任意 build 回退）
      steamtools.py   # steamtools.games 公共 API 探针 + key.vdf 拉取
      xunlei_share.py # 迅雷云盘分享树列举（免登录，仅元数据；下载仍需本人账号）
    reports/
      __init__.py
      coverage.py     # 多仓库覆盖度对比（M1-T08 / Q1）
    lua_gen.py        # Lua 生成 / manifest id 更新                              (M2)
    report.py         # 清单差异报告                                              (M3)
  vendor_ref/         # 从 opensource 复制出来的参考实现（首行注明来源）
    <file>            # 只参考，不参与 import 链
```


### 3.1 CLI 命令一览

| 命令 | 作用 | 何时用 |
|---|---|---|
| `doctor` / `query` / `import-acf` / `report` | 本地库与索引 | 离线检索 |
| `appinfo <appid>` | 匿名 steamcmd 取 depots + gid | 任何 app（含未购买） |
| `keys-merge` / `keys-sync` | 合并 / 增量拉取公开 key 语料（含 steamtools key.vdf） | 扩 key 覆盖 |
| `index-build` | 从镜像文件清单建 `depot -> gids` 索引 | 任意 build 回退的前提 |
| `coverage <appid>` | **只读**判定能否下、缺什么（`--steamtools` / `--hubcap-key`） | 查新作，不占空间 |
| `directlink <depot> --gid` | 单 depot 清单 + chunk 验证 / 还原 | 定点排查 |
| `restore-app <appid>` | 整 app 还原 + 逐文件 sha1 + 结构化报告 | 正式获取本体 |
| `hubcap-check` | 校验 hubcap key / 配额 / 拉单个 manifest | 接入按需清单前自检 |
| `pan-list <url>` | 免登录列出迅雷分享的文件树与大小（不下正文） | 评估外部来源是否值得下 |

报告统一落 `tests/reports/`，命名 `<command>-<appid|depot>[-<variant>].json`。
规则：`vendor_ref/` 只放**复制出来**的第三方代码；文件头必须有
`# source: <repo>@<commit> | copied_at: YYYY-MM-DD | reason: ...`。

## 4. 数据模型

### 4.1 领域对象（`model.py`）

```python
@dataclass(frozen=True)
class ManifestRef:
    appid: int
    depot_id: int
    gid: str            # manifest id, 19 位十进制字符串
    size: int | None
    sha1: str | None    # 40 hex
    source: str         # local_snapshot | github_raw | morrenus | manual
    source_url: str
    fetched_at: str     # ISO8601 UTC

@dataclass(frozen=True)
class AppRecord:
    appid: int
    name: str | None
    depots: tuple[int, ...]
    manifests: tuple[ManifestRef, ...]
```

### 4.2 SQLite 表结构（`catalog.py`）

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS app (
  appid       INTEGER PRIMARY KEY,
  name        TEXT,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manifest (
  appid       INTEGER NOT NULL,
  depot_id    INTEGER NOT NULL,
  gid         TEXT NOT NULL,
  size        INTEGER,
  sha1        TEXT,
  source      TEXT NOT NULL,
  source_url  TEXT NOT NULL,
  fetched_at  TEXT NOT NULL,
  PRIMARY KEY (appid, depot_id, gid, source)
);

CREATE TABLE IF NOT EXISTS probe (
  url        TEXT PRIMARY KEY,
  status     INTEGER,
  ok         INTEGER NOT NULL,      -- 0/1
  latency_ms INTEGER,
  checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
```

索引：`CREATE INDEX idx_manifest_app ON manifest(appid, fetched_at DESC);`
幂等：全部 `INSERT ... ON CONFLICT DO UPDATE`。

### 4.3 本地缓存（`cache.py`）

- 路径：`src/data/cache/<sha256(url)>/<filename>` + 同名 `.meta.json`（url/status/耗时/时间）。
- TTL：清单类 24h；仓库目录类 7d；探针结果 10min。
- 复现：`--offline` 只读缓存，命中率写进报告。

## 5. 外部源接口（`sources/base.py`）

```python
class SourceProvider(Protocol):
    name: str
    def available(self) -> bool: ...
    def lookup(self, appid: int) -> list[ManifestRef]: ...
    def health(self) -> dict: ...   # {ok, latency_ms, checked_at}

class Resolver:
    # 顺序：local_snapshot -> github_raw -> morrenus -> manual
    # 失败一次记 probe，连续 3 次失败则本会话内降权（不删除源）
    def resolve(self, appid: int) -> ResolveResult: ...
```

### 5.1 源清单与已知端点

| 源 | 层级 | 形态 | 端点 / 访问方式 | 说明 |
|---|---|---|---|---|
| `steamcmd` | **主（gid）** | HTTP API | `https://api.steamcmd.net/v1/info/<appid>` | 免鉴权、免 key；返回 app→depot→`manifests.public.gid`；实测 550→9 depot |
| `hubcap` | **主（文件）** | HTTP API | `https://hubcapmanifest.com/api/v1/generate/manifest?depot_id=&manifest_id=&api_key=` | Morrenus 系；key 形如 `smm_`+96 hex，Discord 登录后自助生成，按天配额（免费档约 10~25 次/天）并带到期时间（`api_key_expires_at`），需存 `backup/private/`.env |
| `local_snapshot` | 凭据层 | 目录 | `opensource/ManifestHub-*` | 只含 token/key，**无 gid**；离线可用 |
| `manifesthub_api` | 回退 | HTTP API | `https://api.manifesthub1.filegear-sg.me/manifest?apikey=&depotid=&manifestid=` | LuaTools 现用链；key 24h |
| `github_raw` | 回退 | HTTP | `raw.githubusercontent.com/qwe213312/k25FCdfEOoEJ42S6/main/<depot>_<gid>.manifest` | 93 GB 仓库，命名规则待采样（R-09） |
| `morrenus` | 备注 | HTTP | `https://manifest.morrenus.xyz/`（现指向 hubcapmanifest） | 旧域名，保留兼容 |
| `manual` | 人工 | 用户提供 | `steamtools.games` / trionine 页面 | **只人工查**，不写自动抓取 |

### 5.2 降级规则（对应 D-011）
1. 固定顺序：`steamcmd` → 本地 fixture/cache → `manifesthub_api` → `hubcap` → `github_raw` → 人工。
2. 网络类错误（超时/5xx/限流）→ 降级并记 probe；同一源连续 3 次失败本会话降权。
3. 404 / 空结果 → 记为「该源无数据」，不降权（如 steamcmd 返回 `_missing_token`）。
4. 全部失败 → 返回 `ResolveResult(ok=False, reasons=[...])`，CLI 退出码 2。
5. `steamcmd` 成功后立即把 appinfo JSON 落 `src/data/cache/`，保证断网可回放。

## 6. 解析器契约

| 解析器 | 输入 | 输出 | 关键点 |
|---|---|---|---|
| `acf.py` | appmanifest_*.acf | `AppRecord` + `ManifestRef` | VDF 子集：嵌套 key value、字符串转义；`StateFlags` 保留 |
| `steamcmd.py` | steamcmd appinfo JSON | `AppRecord` + `list[ManifestRef]` | 只取 `depots` 下数字键；`manifests.public` 缺失的 depot 跳过并计数 |
| `hub_json.py` | ManifestHub JSON | `list[ManifestRef]` | 兼容 `{"appid": {"depots": {...}}}` 与扁平两种形态 |
| `lua.py` | SteamTools Lua | `LuaEntry` dict | 键值块 + `addappid` / `setManifestid` 形态；保留未知字段 |

解析失败必须抛出带 **文件、行号、期望值** 的 `ParseError`（安全测试覆盖）。

## 7. Lua 生成（`lua_gen.py`，对标 LMU）

目标格式（SteamTools 兼容）：
```lua
addappid(3240220)
addappid(3240221, 1, "<manifest-id>")
setManifestid(3240221, "<manifest-id>", <size>)
```

规则：
- 只写已解析且校验通过的 manifest；缺失字段用注释标注 `-- TODO`，不臆造。
- 更新已有 Lua：仅改动 id/size 行，其余行逐字节保持（兼容测试断言 diff）。
- 输出默认写 `src/data/out/*.lua`，显式 `--in-place` 才覆盖用户文件（二次确认）。

## 8. 校验（`verify.py`）

- 清单一致性：`depot_id + gid` 与来源记录一致；sha1 为 40 hex 且格式合法。
- 内容一致性（有摘要时）：按文件列表算 SHA-1 流式比对（4 MB chunk），大小不符即 FAIL。
- 结果结构：`VerifyReport(ok, checks=[{name, expected, actual, status}])`，CLI 退出码 0/3。
- 防投毒：路径必须落在允许前缀内，禁止 `..`、绝对路径、ADS；单文件上限可配置。

## 9. 测试策略（映射测试区）

| 子区 | 覆盖对象 | 样例 |
|---|---|---|
| `tests/unit` | 三个解析器、verify、lua_gen、paths | 畸形 VDF / 缺字段 / 超大整数 |
| `tests/integration` | catalog + cache + resolver（本地假源） | 幂等 upsert、TTL、降级链 |
| `tests/contract` | 各源响应格式（脱敏样本） | 404、限流 429、字段缺失 |
| `tests/e2e` | CLI 全链路 | `query --offline`、`lua` → 兼容检查 |
| `tests/compatibility` | 生成 Lua 可被 LuaTools/LMU 规则解析 | fixture 对照 |
| `tests/security` | 脱敏、路径穿越、SSRF、超大文件、Lua 注入 | `file://`、`..\`、10 GB 声明 |

门禁命令：`tools/scripts/gate-check.ps1` 校验：pytest 全绿 → 报告文件存在 → ARD 状态非 pending。

## 10. 工具链脚本契约（工具链区）

| 脚本 | 作用 | 退出码 |
|---|---|---|
| `clone-opensource.ps1` | 刷新开源快照（depth=1） | 0 全部成功 / 1 有失败 |
| `set-readonly.ps1` | 给 opensource 打只读属性 | 0 |
| `import-from-opensource.ps1` | 复制代码出区 + 写来源头 | 0 / 1 越界 |
| `desensitize-scan.ps1` | 脱敏扫描（token/邮箱/用户名/SteamID） | 0 干净 / 1 命中 |
| `backup-snapshot.ps1` | 脱敏快照 → `backup/vcs` 提交 | 0 / 1 扫描失败 |
| `run-tests.ps1` | 跑测试并落报告（unittest 回退时 `-t` 项目根） | pytest 退出码；3 = 未收集到用例（门禁不通过） |
| `gate-check.ps1` | 合并门禁 | 0 通过 / 1 拦截 |
| `env-check.ps1` | 环境与分区自检 | 0 |
| `steam-download.ps1` | 用 `tools/bin/steamcmd.exe` 把本体装进独立目录（默认 `src/data/body/<appid>`，拒绝写 `D:\Steam`） | steamcmd 退出码 |

所有脚本：`-Verbose` 可选、幂等、路径由 `$PSScriptRoot` 推导、不写死盘符。

## 11. 安全设计

- 凭据：只从环境变量或 `backup/private/.env` 读取；日志脱敏函数统一 `redact()`。
- 网络：默认只允许 `https`；重定向放行（目标域名族走可配置白名单，CDN 普遍多跳）；禁止 `file://`；超时 15s。
- 下载：单文件**不设硬上限**（按清单 size 放行，超出声明值才告警）；保留总配额预警、磁盘余量检查、断点续传与哈希校验。
- 供应链：`manifests.ps1` 等外部脚本仅存放于 `tools/vendor/`，人工审阅后离线执行；禁止 `iex (irm ...)`。
- 本机：`D:\Steam` 与配置（`steamapps` / `config` / `userdata` / 注册表）**未经用户明确授权严禁写入或修改**；产物先落独立目录；授权后写入前先备份 `steamapps\*.acf` / `libraryfolders.vdf`，产物目录与回滚点记入 ARD。

## 12. 开发环境与运行

```powershell
# 环境
python --version      # 3.12.x
pip install -r src\py\requirements.txt   # 仅 pytest（核心零依赖）

# 运行（在项目根执行）
python -m steam_research.cli doctor
python -m steam_research.cli query 3240220 --offline
python -m steam_research.cli coverage 4115450 --steamtools --key-file src\data\keys\merged.json
python -m steam_research.cli restore-app 340 --out-dir src\data\directlink\app-340 --key-file src\data\keys\merged.json --manifest-index tests\reports\mirror-index.json
```

环境变量：`SR_PROXY`（可选）、`SR_MORRENUS_KEY`（可选，存 private/.env）。

## 13. 未决技术点

0. **数据源已定版（D-010）**：gid 走 steamcmd，文件走 hubcap，回退链见 §5.1/§5.2。
1. ManifestHub 各仓库 JSON 结构差异较大，需 M1 采样后收敛 schema（先宽松解析 + 保留原始）。
2. Lua 语法子集边界（是否支持 `if/for`）→ 先做「键值 + addappid/setManifestid」最小集。
3. `fylsdy/ManifestHub` 404 的替代源（镜像 / fork）待定。
4. 大仓库浅克隆的更新策略（git pull --depth=1 的冲突面）。
5. `qwe213312` raw 文件命名规则（`<depot>_<gid>.manifest` 未验证）。
6. `ManifestAutoUpdate` 加密库的格式与解密可行性 —— 列为 M3 备选，不投入 M1。