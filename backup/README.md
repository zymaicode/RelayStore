# backup — 备份区

两个子区，边界完全隔离，**不得混用**。

| 子区 | 路径 | 内容 | 远端 |
|---|---|---|---|
| 本地版本库 | `backup/vcs/` | `src` / `docs` / `tests` 的**脱敏**源码快照，仿 GitHub 分支与 tag | **无 remote**（纯本地） |
| 私有敏感区 | `backup/private/` | 账号、凭据、私人笔记、真实数据 | **严禁推送**，永不作 remote 源 |

## 为什么要本地版本库

GitHub 可能推送失败（网络、墙、配额、仓库被删）。`backup/vcs` 提供与远端解耦的兜底版本线：
断网也能提交、打 tag、回滚、对比，网络恢复后再对齐远端。

## 快照怎么做

```powershell
pwsh -File tools\scripts\backup-snapshot.ps1 -Message "chore: baseline"
```

脚本会：复制 `src` / `docs` / `tests` → 脱敏（绝对路径、用户名、邮箱、token、SteamID）→
`git add/commit`（在 `backup/vcs` 内）→ 失败即中止。

## 恢复

```powershell
cd backup\vcs
git log --oneline --decorate
git checkout <tag-or-commit> -- src docs
# 复制回项目根（脚本会检查只读属性）
```

## 禁止

- 在 `backup/vcs` 配 remote（`git remote add` 也不许）。
- 把 `backup/private` 的任何内容放进 `vcs`。
- 把未脱敏的日志、`.env`、浏览器 cookie 放进来。
