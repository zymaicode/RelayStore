# 学习版 vs 官方版：可确定的差异（2026-11-06）

> 结论先行：**体积差 2.19 GiB（1.56%）、版本落后约 6 天、多出 DRM 绕过组件**。
> 逐文件 diff **做不到** —— 官方 manifest 拿不到（镜像 404 + 无 depot key），见 ARD D-036。

## 1. 硬指标对比

| 维度 | 官方（Steam depot 4115451） | 学习版（35 卷 RAR） | 差 |
|---|---|---|---|
| 未压缩体积 | **150,856,184,777 B = 140.50 GiB** | **148,505,917,219 B = 138.31 GiB** | **−2.19 GiB（−1.56%）** |
| buildid | 26367565（timeupdated 2026-11-04 08:01 UTC，timebuildupdated 2026-11-01） | 归档内文件 mtime **2026-10-29 18:18** | 落后约 **6 天** |
| 分发单位 | depot 4115451（chunk，SHA-1 寻址） | 35 卷 × 4 GiB（RAR5，首卷 SFX） | — |
| 完整性依据 | 每文件 `sha1`（manifest）+ chunk sha1 | RAR CRC + 每卷整文件 SHA-1（迅雷 `hash`） | **不可比** |
| DRM | Denuvo（`包含第三方 DRM: Denuvo`）+ Steam DRM | Denuvo 壳保留，**外加 coldloader.dll 绕过 Steam 校验** | 关键差异 |
| 可运行性 | 需账号授权（Denuvo token） | 依赖 loader，是否可跑**未验证**（禁止执行） | — |

## 2. 学习版多出来的东西（已实测）

| 文件 | 大小 | 说明 |
|---|---|---|
| `PBZ/platform/steam/coldloader.dll` | 116,736 B | 内含 `ColdLoader`、引用 `InstallPathsteamclient64.dll` → 已知 Steam/Denuvo 绕过 loader |
| `PBZ/ProjectPBZ/Binaries/Win64/8za_v2.exe` | 5,532,248 B | SSL.com 代码签名；仅导入系统库；无外联 URL；用途未知 |
| `PBZ/ProjectPBZ/Binaries/Win64/CheckEnv.exe` | 69,464 B | 导入 `MiguGameSDK64.dll`，含「咪咕互动娱乐有限公司」→ 中国渠道发行组件（官方版可能也有） |

保留但未替换：`PBZ/platform/steam/steam_api64.dll` 319,128 B（与 Valve 原版同量级，**未见 Goldberg 替换**）。

## 3. 那 2.19 GiB 差在哪？（推测，按可能性排序）

1. **多语言语音包被删**：只留中文/英文语音，删掉其他语种（PBZ 全语音，单语种pack常 1–3 GiB）；
2. **redist 被删**：VC++ / DirectX 安装包装箱（常见 0.3–1 GiB）；
3. **版本落后 6 天**：期间可能新增/替换过资源；
4. **RAR 存储模式**：熵 8.000 说明基本无压缩，所以"解开会比归档大很多"不成立。

## 4. 做不到的部分（诚实说明）

| 想要 | 为什么做不到 | 需要什么 |
|---|---|---|
| 逐文件清单 diff | 官方 manifest 镜像 404，且无 depot key 无法解密 | 购买该游戏后取 manifest，或等社区补档 |
| 判断 `PBZ.exe` 是否被改 | 511 MB Denuvo 混淆 exe，无官方哈希对照 | 同上（官方 manifest 的 `sha_content`） |
| 判断 loader 是否"能跑" | 禁止执行任何 exe | 需在隔离环境 + 授权账号下测试（不属于本项目范围） |

## 5. 对我们的意义

- **不是"官方原样归档"**：含第三方 loader、版本旧 6 天、无逐文件哈希 → 不满足项目"可复现 + 可校验"标准。
- **也不是"纯盗版"**：主体是真实 UE5 构建（`PBZ/Engine`、`PBZ/ProjectPBZ`、`PBZ/platform/steam` 结构完整）。
- **定位**：内容可用、来源不可信。若要归档，应把它当"待验证素材"，而不是"官方副本"。
