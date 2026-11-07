# Steam 清单获取链路：三条路线与定版（C 主 / A 辅 / B 备）

- 日期：2026-11-05
- 类型：经验
- 标签：#steam #manifest #api #datasource
- 来源任务：Session 03 / D-010

## 背景
fylsdy 仓库消失后，需要重新确定“清单从哪来”。调研了三种路线，结论直接写进 ARD D-010~D-012。

## 路线对比

| 路线 | 是什么 | 端点 / 形态 | 成本 | 用途 |
|---|---|---|---|---|
| A 静态仓库 | token + depot key；**无 gid** | `opensource/ManifestHub-*` JSON | 已付 44 MB，离线可用 | 凭据层、回放、格式样本 |
| B ManifestAutoUpdate | **加密清单库** | 根目录 applist/version.txt；100+ 动态分支 | 需专用入库工具解密；分支漂移 | M3 备选，当前不用 |
| **C API 链** | gid + manifest 文件 | 见下 | 每 appid 1 请求；key 24h | **主路线** |

## C 链路（已实测）

```text
① gid      GET https://api.steamcmd.net/v1/info/<appid>        # 免鉴权、免 key
② 文件     https://hubcapmanifest.com/api/v1/generate/manifest?depot_id=&manifest_id=&api_key=
③ 回退     api.manifesthub1.filegear-sg.me/manifest?apikey=&depotid=&manifestid=
④ 回退     raw.githubusercontent.com/qwe213312/k25FCdfEOoEJ42S6/main/<depot>_<gid>.manifest  (命名待验证)
```

实测证据（2026-11-05）：
- `/v1/info/550` → **Left 4 Dead 2，9 个 depot**，depot 551 gid `314878501352141828` size 11.3 GB；
- `/v1/info/3240220` → **GTA V Enhanced，6 个 depot**，depot 3240221 gid `7738940149188702855`（600 字节补丁）；
- hubcapmanifest.com 返回 200；manifesthub1 端点来自 LuaTools 的 `manifests.ps1`；
- `version.txt` 取回是密文 → 确认 B 不可直接解析。

## 关键认知
- ManifestHub 系仓库是 **credential cache**，不是 manifest cache；清单的 gid 必须走 API。
- 免费 API key 24 小时过期，是唯一硬约束 → 设计上必须“按需查 + 缓存 + 回放”。
- 抓到的 appinfo 立即落 `src/data/cache/`，断网可回放（契约测试用 fixture，不联网）。

## 复用建议
- 新接 appid：先 `steamcmd`，失败读 cache，再走 manifesthub1/hubcap。
- key 放 `backup/private/.env`（`SR_HUBCAP_KEY`），不进代码、不进日志。
- 若 C 全线失效：退回 A 的 token/key + 官方 Steam API（自有账号）；再不行再用人工。
