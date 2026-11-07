# 2026-11-06 · 100% 整 app 还原：机制之外，剩下的是覆盖度

## 结果
- 480（Spacewar，免费）：1/1 depot、8 文件、1,906,055 B、delta 0、10 s。
- 340：9/9 depot、127 文件、678,540,255 B、每 depot delta 0、119 s。
- 3DMark（223850）：9/39 depot；缺 5 个 manifest、24 个超 300 MB 被跳过、1 个缺 key。

## 这轮加的三件事
1. **多端点镜像**：`raw.githubusercontent.com` / `cdn.jsdelivr.net/gh` / `raw.githack.com` × 多仓库；某个端点被墙或 404 时自动换下一个，attempts 全记录。
2. **key 语料合并**：两份语料 181,096 条有效；坏值 112,600 条跳过并计数 —— 语料质量差是常态，不能让一条坏 key 拖垮整批。
3. **retry-from**：读上一次报告，只重跑 `failed/missing_key/missing_manifest` 的 depot；配合 chunk 缓存，重试成本≈0。

## 判断「完整」的口径
- 文件级 sha1 全过 + depot 级 `bytes == expected_bytes`（delta 0）+ 所有非 skipped depot 都是 ok。
- `ok=true` 但存在 skipped 不算 100%：必须 `restored == depots_total`。这条要写死在报告语义里，否则容易自我安慰。

## 下一步
把 `missing_manifest` 的 (depot, gid) 当验收样本扩源；优先找第二个能提供同名 `<depot>_<gid>.manifest` 的仓库，而不是先上 hubcap key。
