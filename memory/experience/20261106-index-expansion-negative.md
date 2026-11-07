# 2026-11-06 · 索引源扩充是负结果，效率优化才是正解

## 实测
8 个候选仓库的 `<depot>_<gid>.manifest` 文件数：dc190 0、ooiiuur/Sharing 7、steamtoolsapp 0、Nsymptotic 1、ooiiuur 1、SteamAutoCracks 0、trionine 0、Coronitaa 0。
→ 只有 qwe213312 有规模（249,678），「多仓库扩索引」收益≈0。

## 改进
- 索引 v2：`depot -> {gid -> [repos]}`，兼容 v1（`depot -> [gid]`）与旧构造 `ManifestIndex(gids=...)`。
- `restore-app --depot-workers N`：depot 级并行（ThreadPoolExecutor，state 写盘加锁）。
- `coverage --appids-file`：批量扫描输出 downloadable/blocked。
- `--appinfo-cache`：appinfo 落盘，避免每次 steamcmd（实测单次可达数分钟）。

## 教训
「加数据源」要先量覆盖率，再写代码：8 个仓库扫完只花 80 秒，却省掉了一整条错误路线。
steamcmd 是慢依赖，凡是循环调用它的功能都必须带缓存。
