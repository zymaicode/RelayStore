# 2026-11-06 · 把「未购买直链」工程化成一条命令

## 结果
`python -m steam_research.cli restore-app 223850 --out-dir ... --key-file ... --max-depot-bytes ...`
→ 3DMark（未购买）39 个 depot：9 还原（282 文件 / 1.43 GB / sha1 全过）、24 超限跳过、5 镜像缺失、1 缺 key，392 s。

## 工程上的五个决定
1. **失败按 depot 隔离**：一个 depot 的 key/manifest/chunk 出问题不能拖垮整个 app；状态枚举 `ok/skipped/missing_key/missing_manifest/failed`。
2. **报告不粉饰**：`ok = 所有非 skipped 都是 ok`。缺 5 个镜像就是 `ok=false`，附逐条原因。
3. **Keyring 容错**：语料里混着长度不对的 key（如 `3632491`），单条坏 key 只计 `invalid`，不能让整批加载抛异常。
4. **镜像回退留证据**：记录 attempts + 实际命中的 `source_url`，事后能判断「缺 manifest」是哪个仓库没有。
5. **目录项不是文件**：清单里零 chunk / 带 `linktarget` 的条目只建目录，否则后面建子目录会 `WinError 183`。

## 踩坑
- `sources/` 下的模块用相对导入 `.manifest` 会解析到 `steam_research.sources.manifest` → 必须 `..manifest`。
- `url_for` 里字符串拼接误写成元组拼接（多了一个逗号）→ `TypeError: can only concatenate tuple`。
- 大语料加载（46 万条 key）要一次性 try/except 包住 `add_hex`，否则第一个坏值就直接失败。

## 覆盖率现状（下一步的输入）
- 镜像仓库覆盖不全：3DMark 39 个 depot 里 5 个没有 manifest（含 2313300、3941790）。
- key 语料缺 1 个（新 depot）。
- 因此下一步不是改机制，而是**扩源**：第二个 manifest 镜像 + key 语料合并去重。
