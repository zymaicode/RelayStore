# 已删除仓库的存世副本怎么找（commit 作者检索法）

- 日期：2026-11-05
- 类型：经验
- 标签：#github #forensics #manifesthub
- 来源任务：Session 02

## 背景
`fylsdy/ManifestHub` 突然 404，需要在没有父仓库的情况下判断“有没有人 fork”。
父仓库删除后，GitHub 的 fork 列表/网络页面全部失效，普通仓库搜索也只给名字，看不出血缘。

## 有效方法（按性价比排序）
1. **判死因**：`api.github.com/users/<name>` + `github.com/<name>` 都 404 ⇒ 账号注销（改名会 301）。
   这一步决定后面是“找 fork”还是“找幸存镜像”。
2. **提交作者检索**：`/search/commits?q=author-name:<name>` 或 `author:<name>`。
   用户删了，提交记录仍被索引；命中的仓库就是镜像/副本。本次 19 条提交全部指向 `kken26627-clone/90l-ua-mani`。
3. 仓库名搜索 `q=<Repo> in:name`（默认不含 fork；父仓库没了 fork 会变独立仓库，仍会出现）。
4. 交叉验证：`q=<name> in:readme`、issues 搜索、Software Heritage `origin/search`、Wayback CDX。
   本次 SWH 只存了该用户的另一个小仓库，说明 SWH 不保证抓到清单类大仓库。

## 本次结论（可复用事实）
- fylsdy 账号已注销；仓库无公开 fork 名残留。
- 存世副本：`kken26627-clone/90l-ua-mani`，HEAD 提交作者即 fylsdy（2026-04-28）。
- 血缘：oureveryday（2025-02）→ fylsdy（2026-01~04）→ kken26627-clone（2026-06）。
- 上游仍在：`oureveryday/ManifestAutoUpdate`（408★，约 21.4 GB）。

## 复用建议
- 遇到“源仓库 404”先跑 `author-name:` 检索，通常 1~2 次 API 调用就能定位镜像。
- 注意 API 限额：core 60/h、search 10/min；一次批量检索别超过 10 个查询。
- 镜像仓库常有超大历史，克隆一律 `--depth 1`（本次 44.1 MB）。
