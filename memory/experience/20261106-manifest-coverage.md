# 2026-11-06 · 「几乎所有 Steam 游戏都能下吗」——用数据回答

## 实测（12 个 app 抽样）
| 维度 | 结果 |
|---|---|
| depot key | 多数 100%（3DMark 89%、CS2 93%） |
| manifest（当前 gid） | 480/340/70/400/323910/2358720 100%；220 92%；3DMark 71%；620 60%；Dota2 26%；CS2 6%；Cyberpunk **0%** |
| manifest（任意 build） | CS2 93%、Dota2 100%、Cyberpunk 100%、Portal2 100%、3DMark 89% |

## 根因
镜像仓库按 `<depot>_<gid>.manifest` 存的是**某个历史 build**；appinfo 给的是**当前 build**。
越常更新的游戏（CS2、Dota2、Cyberpunk）当前 gid 越不可能命中。

## 解法
`git clone --filter=blob:none --depth 1 --no-checkout` 只拉 tree（不拉 93 GB blob）→ 得到 70,942 depot / 249,678 manifest 的索引；
当前 gid 404 时回退到该 depot 最新可用 gid，报告用 `gid_used` 标明实际用的 build。
3DMark 实测：missing_manifest 5→0、ok 9→14、文件 282→320。

## 代价（必须提前说）
- 回退 = 旧版本；`bytes_delta != 0` 是版本偏移，不是数据损坏。
- 不同 depot 混用不同 build 可能造成版本不一致，影响 L4 可玩性验证。
- 索引里没有的 depot 仍然无解（3DMark 4/39）；要「按需取当前 build」只能上 hubcap 这类服务。

## 结论
现在不是「几乎所有」，而是「**大多数热门/老游戏的某个 build 能下**」；能否下取决于镜像索引与 key 语料的覆盖，不取决于机制。
