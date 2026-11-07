# 未购买游戏直链还原：工程化工作流

> 目标：给定一个 appid（**不要求账号拥有该游戏**），从公开直链拿到清单与内容，还原成本地目录，并逐文件校验。
> 实现：`src/py/steam_research/{pipeline,restore,directlink,depot,manifest,keys}.py` + `sources/{appinfo,manifest_mirror,cdn}.py`。

## 1. 一条命令

```powershell
$env:PYTHONPATH = "E:\vibe coding\steam\src\py"
python -m steam_research.cli restore-app <APPID> `
  --out-dir "src\data\directlink\app-<APPID>" `
  --key-file "opensource\ManifestHub-mirror-kken26627-clone\depotkeys.json" `
  --max-depot-bytes 300000000 `
  --workers 8 `
  --out "tests\reports\restore-app-<APPID>.json"
```

退出码：`0` 全部 depot 还原成功；`3` 有跳过/缺失/失败（报告里逐条写清）。

## 2. 链路（每一步都可单独调用）

| 步骤 | 模块 | 命令 | 说明 |
|---|---|---|---|
| depot + gid | `sources/appinfo.py` | `cli appinfo <appid>` | 匿名 steamcmd `app_info_print`，对未购买 app 有效 |
| manifest | `sources/manifest_mirror.py` | — | GitHub raw `<repo>/<depot>_<gid>.manifest`，多仓库依次回退 |
| depot key | `keys.py` | `--key-file` / `--config-vdf` | 本地 JSON 语料或 Steam 客户端 `config.vdf` 的 `DecryptionKey` |
| chunk | `sources/cdn.py` | — | `https://<cdn>/depot/<depot>/chunk/<sha>`，多主机回退 |
| 解码 | `depot.py` | — | AES-256（ECB-IV + CBC/PKCS7）→ VZip/Zip/VZstd |
| 组装+校验 | `restore.py` | `cli directlink --restore` | 逐 chunk sha1、逐文件 size+sha1，内容寻址缓存 `.chunks/` |
| app 级编排 | `pipeline.py` | `cli restore-app` | 逐 depot 隔离失败，产出结构化报告 |

## 3. 报告语义（`restore-app` JSON）

| 字段 | 含义 |
|---|---|
| `depots[].status` | `ok` / `skipped`（超限或 `--only-depot` 过滤）/ `missing_key` / `missing_manifest` / `failed` |
| `files_ok / files_total` | 只统计**有 chunk 的真实文件**；目录/链接项单列 `directories` |
| `bytes` | 写盘字节（等于清单 `cb_original` 之和） |
| `source_url` | 该 depot manifest 实际来自哪个镜像 |
| `ok` | 所有 depot 均为 `ok`/`skipped` 时为真；有缺失即为假（不粉饰） |

## 4. 已知边界

- **清单覆盖**：镜像没有该 `<depot>_<gid>` 时状态是 `missing_manifest`（实测 3DMark 39 个 depot 里 5 个缺失）。
- **key 覆盖**：语料 469k 条仍可能缺新 depot（实测 1 个 `missing_key`）。
- **CDN**：`*.steamcontent.com` 在本机被 TLS 重置，默认走 `steampipe.akamaized.net`；`st.dl.eccdnx.com` 对 chunk 返回 403。
- **体积**：`--max-depot-bytes` 用来控制单次还原规模；超过阈值的 depot 标 `skipped` 而不是静默丢弃。
- **不触碰本机 Steam**：产物只落 `src/data/directlink/`（已在 `.gitignore`）。

## 5. 验收口径

1. chunk 级：`len(plain) == cb_original` 且 `sha1(plain) == chunk.sha`
2. 文件级：`size == FileMapping.size` 且 `sha1(file) == sha_content`
3. depot 级：`files_ok == files_total && files_failed == 0`
4. app 级：所有非 skipped 的 depot 均为 `ok`

## 6. 扩源与重试

```powershell
# 合并多份 key 语料（坏 key 自动跳过并计数）
python -m steam_research.cli keys-merge --key-file a.json --key-file b.json --out src/data/keys/merged.json

# 只重试上次报告里没成功的 depot
python -m steam_research.cli restore-app 340 --out-dir src/data/directlink/app-340 --key-file src/data/keys/merged.json --retry-from tests/reports/restore-app-340.json
```

- manifest 端点顺序：raw.githubusercontent.com -> cdn.jsdelivr.net/gh -> raw.githack.com（同一仓库三种取法，再乘多仓库）。
- 报告新增 expected_bytes / bytes_delta：delta == 0 表示还原字节与 appinfo 声明一致。

## 7. 实测（2026-11-06）

| appid | 场景 | depot | 文件 | 字节 | delta | 耗时 | 结果 |
|---|---|---|---|---|---|---|---|
| 480 | Spacewar（免费/未购买） | 1/1 | 8 | 1,906,055 | 0 | 10 s | ok=true |
| 340 | 多 depot 整 app | 9/9 | 127 | 678,540,255 | 全 0 | 119 s | ok=true |
| 223850 | 3DMark（未购买，含超限） | 9/39 | 282 | 1,526,496,365 | — | 392 s | ok=false（5 镜像缺失 / 24 超限 / 1 缺 key） |

## 8. 扩源 TODO（3DMark 缺清单样本）

skipped/missing 的 depot 会带原因写在报告里；把 `status=missing_manifest` 的 `(depot, gid)` 收集起来即可作为新镜像源的验收样本。
