# 本机 Steam 环境实测事实（M0）

- 日期：2026-11-05
- 类型：经验
- 标签：#steam #environment

## 背景
项目立项前先摸清本机 Steam 环境，避免后续研究中反复试错。

## 事实（2026-11-05 实测）

| 项 | 值 |
|---|---|
| 安装目录 | `D:\Steam`（客户端 11.15.70.27，安装于 2025-10-15） |
| 库数量 | 1 个（`libraryfolders.vdf` 只有 `D:\Steam`） |
| 已装游戏 | 6 个 appmanifest：GTA V Enhanced 96.17 GB / PEAK 15.31 / L4D2 13.94 / Human Fall Flat 6.33 / 妹居物语 Demo 2.92 / Steamworks 0 |
| 合计 | 客户端 1.38 GB + 游戏 134.67 GB = 137.5 GB |
| 语言 | schinese；账号 zymikly；RememberPassword=1 |
| 自启 | HKCU Run：`"D:\Steam\steam.exe" -silent` |
| 服务 | Steam Client Service：Stopped / Manual |
| 运行状态 | 研究时未运行 |

## 有用路径（只读）

```text
D:\Steam\steamapps\libraryfolders.vdf     库映射
D:\Steam\steamapps\appmanifest_<appid>.acf   已装清单
D:\Steam\config\loginusers.vdf             账号（敏感，勿摘录）
D:\Steam\userdata\<accountid3>\             账号数据
```

## 工具链事实（2026-11-05）

- `python` → `E:\msys64\mingw64\bin\python.exe`（3.12.12），**没有 pip**，因此也没有 pytest。
- 测试走 `unittest` 路径（`tools/scripts/run-tests.ps1` 自动回退），不要假设 `pytest` 可用。
- `git` 2.53 / `node` v24 可用；GitHub 直连正常（无需代理）。

## 复用建议
- 研究 acf 解析直接拿本机 6 个 appmanifest 当真实样本（先脱敏再入 fixtures）。
- **未经授权不写 `D:\Steam` 与配置**（`steamapps` / `config` / `userdata` / 注册表）；产物先落独立目录；获授权后写入前备份 `steamapps\*.acf` / `libraryfolders.vdf` 并留回滚点（D-016）。
- 账号相关信息不写进文档，放 `backup/private`。