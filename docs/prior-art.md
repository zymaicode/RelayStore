# 先例调研：Steam 清单 / 免授权下载生态（GitHub，2026-11-06）

> 结论先行：这条链路**早就有人做成产业级产品**，而且架构和我们搭的完全一致（manifest 缓存 + key.vdf + lua + DepotDownloader / 模拟器）。
> 同样重要：**没有任何项目"破解" depot key** —— 所有 key 都来自持有者分享。
> 对《影之刃零》，最大的公共库（steamtools.games）明确回答"不在库里"。

## 1. 清单/下载工具（有实际用户量）

| 项目 | Stars | 最近更新 | 做了什么 | 关键限制 |
|---|---|---|---|---|
| `SteamRE/DepotDownloader` | 3,513 | 2026-11-06 | SteamKit2 官方血统的 depot 下载器，可指定 manifest gid、降级旧版本 | 需要 Steam 登录 + **账号拥有该 app** |
| `ikunshare/Onekey` | 1,405 | 2026-11-04 | 一键式 depot manifest 下载器，输入 AppID 即可（中文生态） | 依赖其上游清单源 |
| `Midrags/SFF`（SteaMidra） | 2,015 | 2026-11-06 | 全家桶：Hubcap 清单库 → lua → 写入 Steam 配置 → LumaCore / gbe_fork / Steamless / DLC 解锁 | 需要 Hubcap API key；本质仍是"有清单+key" |
| `SteamAutoCracks/ManifestHub` | 2,252 | 2026-11-06 | 公共 manifest 库（我们镜像的上游之一） | 只存历史 build |
| `fairy-root/steam-depot-online` | 236 | 2026-10-25 | manifest 下载/管理 GUI，支持 GitHub token 加速 | 同上 |
| `mcbabel/Steam-Manifest-Downloader` | 56 | 2026-11-01 | .lua/.st 或 AppID → 下 depot → 加入 Steam → gbe_fork 打补丁 | README 明说"仅配合自有正版 key" |
| `SLSYSL/ManifestHub-GUI` | 80 | 2026-11-04 | 从**本机 Steam** 提取密钥（即 key.vdf 生成） | 只能拿已拥有的 key |
| `steamtools-games/ManifestHub3` | 41 | 2026-11-05 | 驱动 steamtools.games 的公共缓存；**公开 API 返回 .lua + key.vdf**，免注册 | 库内没有的游戏返回 `not_in_db` |

## 2. 无 Steam 运行层（只对 Steam DRM 有效）

| 项目 | Stars | 作用 |
|---|---|---|
| `atom0s/Steamless` | 5,156 | 剥离 SteamStub 壳（exe 层），不涉及 Denuvo |
| `metrixmedia/SteamEmulator` / `alex47exe/gse_fork` | 428 / 412 | Goldberg 模拟 `steam_api`，让游戏以为有许可证 |
| `brunolee-GIT/GSE-Generator` | 189 | 一键生成 Goldberg 配置 |

## 3. Denuvo 侧（完全是另一个学科）

| 项目 | Stars | 内容 |
|---|---|---|
| `reetamdan/hypervisor-crack-audit` | 330 | 分析"用 hypervisor 拦截 Denuvo 校验"这一路线的安全性 |
| `nathan-baggs/diamond` | 119 | Denuvo 逆向代码 |
| `Nitr0-G/Denuvo-Info` | 73 | Denuvo 破解笔记汇总 |

要点：Denuvo 的公开进展都在**虚拟化/硬件层**，没有任何"改文件/改字节"的通用方案。

## 4. 实测：steamtools.games 公共 API（免注册）

```bash
curl -s -X POST "https://steamtools.games/api/generate" \
     -H "Content-Type: application/json" -d '{"appId":"4115450"}'
# => {"code":-1,"message":"not_in_db:App 4115450 is not yet in the ManifestHub database. Join our Discord to request it."}
```

- 影之刃零 **不在库内** —— 与我们在 6 个镜像 + 11 个候选仓库 + 3 份 key 语料里 0 命中完全一致。
- 该 API 对已收录游戏返回 `downloadUrl` / `luaUrl` / `keyVdfUrl`，即「清单 + 密钥 + lua」三件套。

## 5. 对我们项目的三条结论

1. **架构被验证**：我们做的 manifest 索引 + keyring + 还原 + sha1 校验，与生态里成熟产品同构；差别是我们更强调"逐文件校验 + 可复现"。
2. **钥匙不可算**：所有项目的 key 都来自「持有者导出」（config.vdf / key.vdf），没有例外；这坐实了"破解密钥"不成立。
3. **可以直接借力的两个现成接口**：
   - `steamtools.games /api/generate`：对已收录 app 直接给 lua + key.vdf → 可当**第二个 key 源**，把我们的 181,096 条语料扩大。
   - Hubcap（SFF 在用）：按需 manifest，解决"当前 build 缺失"。

## 6. 对影之刃零的判断（综合）

- 已发售（2026-10-28）、Denuvo、单 depot 140.5 GiB、只有 public 分支；
- 三个独立渠道（我们扫的镜像、GitHub 搜索、steamtools.games 官方回复）都指向同一结论：**目前无人分享**；
- 一旦有人分享，最先出现的会是 steamtools.games 的 `not_in_db` 变成正常响应 —— 这可以当作我们的**雷达探针**（一条 curl 就能查）。
