# 2026-11-06 · 扩大范围查《影之刃零》：全渠道 0 命中

## 事实
- appid 4115450，2026-10-28 已发售；depot 4115451，150,856,184,777 B（140.5 GiB），buildid 26367565，gid 3746360227235602232。
- key：merged(181k) / dc190(288k) / ooiiuur(288k) / tokens(7.5k) 全无 4115451。
- manifest：6 个已知仓库 + 11 个 GitHub 候选仓库（blobless clone 查文件）+ 本地 70,942 depot 索引 → 0 命中；raw 直链 404。
- Steam CDN：401（需授权会话）；LuaTools API：404。

## 结论
不是机制问题，是时间差：新发售游戏的 manifest 要等社区镜像同步，depot key 要等持有者分享。
hubcap 类服务只能补 manifest，补不了 depot key —— key 只能来自拥有者分享，这点要写进预期。

## 做法沉淀
- 「能不能下」不需要下载：appinfo + keyring + 镜像索引 + HEAD 即可判定，已固化为 `cli coverage <appid>`（M3-T12）。
- 扩源按「仓库 × 路径命名」遍历，优先 blobless clone 取文件清单（249k 文件索引成本只有几 MB）。
