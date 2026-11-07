# 2026-11-06 · 未购买游戏的直链：哪一段免费、哪一段要技术

## 实测矩阵（2026-11-06，未购买的 3DMark appid 223850 / depot 1276160）
| 环节 | 结果 |
|---|---|
| manifest 文件 | ✅ GitHub raw 镜像 `qwe213312/k25FCdfEOoEJ42S6/main/<depot>_<gid>.manifest` → 200 / 19 KB / magic `d017f671` |
| chunk 文件 | ✅ `https://steampipe.akamaized.net/depot/<depot>/chunk/<sha>` → 200 / 191 KB |
| depot key | ✅ 本地 ManifestHub 语料 29 万条里能查到 |
| gid | ⚠️ `api.steamcmd.net` 对未购买 app 常返回 `_missing_token`，无 depots |
| CDN 域名 | ⚠️ `*.steamcontent.com` 被 TLS 重置；akamaized 可用；eccdnx 403 |

## 关键认知
1. **直链不需要第三方 key**：manifest 与 chunk 都能匿名拿；hubcap key 的价值只在「gid 查询/旧清单兜底」，不是直链本身。
2. chunk 拿到的是 **AES 加密 + LZMA 压缩**的数据，raw sha1 必然不等于 manifest 里的 sha —— 别把它当失败，是没解密。
3. IV 派生不是「全零 / 前 16 字节 / sha 前 16 字节」这三种（都试过，均不匹配）。下一步应直接对照 SteamKit / DepotDownloader 源码，而不是继续猜。

## 复用建议
- 判断「直链是否可用」只看 HTTP 200 + 字节数；判断「内容是否正确」必须解密后再比 sha1，两者别混为一谈。
- 探测 CDN 时准备多域名回退：本机 `steamcontent.com` 全线 RST，akamaized 正常 —— 写死一个域名等于写死失败。
- 判断 app 是否「未购买」最省事的间接证据：本机 `steamapps/*.acf` 里没有该 appid，且 `steamcmd.net` 返回 `_missing_token`。
