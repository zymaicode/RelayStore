# 克隆上游仓库返回 404 的处理

- 日期：2026-11-05
- 类型：错误
- 严重度：P1
- 来源任务：M0-T03

## 现象
`git clone https://github.com/fylsdy/ManifestHub.git` 返回：

```text
remote: Repository not found.
fatal: repository '...' not found
```

同一个脚本里其他 6 个仓库均成功，说明本地网络与 git 配置正常。

## 根因
上游仓库不可见：已删除、改名、转私有，或所在组织被限制。不是本地代理/DNS 问题。

## 处置
1. 用 `git ls-remote` / GitHub API 复核，确认 404（而非 401/超时）。
2. 记录到 `opensource/README.md` 与 ARD（D-005 / R-01），标记「待替代」。
3. 不为它反复重试；其余源继续可用。
4. 后续找镜像 / fork / 同组织其他仓库，找到后更新 clone 脚本的 URL。

## 防复发
- 克隆脚本输出已包含 exit code 与 stderr，失败不会被静默吞掉。
- 契约/健康度探测（M3-T02）会自动发现源失效，不必手工发现。
- 记忆索引记录本条，避免下次把 404 当成网络问题排查半小时。
