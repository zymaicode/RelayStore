# memory — 记忆取区

> 目的：**同一个坑不踩第二次**；把「做法」变成可复用的资产。

## 结构

```text
memory/
  index.md                     # 总索引：一条一句，先看这里
  experience/                  # 经验：有效做法、踩通的外部源、好用的命令
  errors/                      # 错误：现象 -> 根因 -> 处置 -> 防复发
  playbooks/                   # 可复用流程（多步操作手册）
  templates/                   # 条目模板
```

## 规则

1. 文件命名：`YYYYMMDD-<kebab-slug>.md`（英文 slug，正文中文）。
2. 每条必有：**现象 / 根因 / 处置 / 复用建议**。
3. 写完必须在 `index.md` 加一行指针，否则等于没写。
4. 同类错误出现第 2 次：升级为回归测试（`tests/security` 或 `tests/contract`）。
5. 条目脱敏；敏感细节只写 `backup/private`，这里留指针。
