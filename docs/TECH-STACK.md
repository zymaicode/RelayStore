# 技术栈决策（Steam 免账户客户端 · Windows GUI）

> 定位：**精简版 Steam 客户端** —— 只做「查清单 → 取密钥 → 连 CDN 下 chunk → 本地解密组装 → 可选免 Steam 启动」；**不存储、不分发任何游戏内容**。

## 1. 决策表

| 编号 | 决策点 | 结论 |
|---|---|---|
| D0 | 项目形态 | Windows 桌面 GUI |
| D1 | 目标平台 | 仅 Windows |
| D2 | 内容源 | 多源可插拔：镜像 → hubcap → 本地/手动 |
| D3 | 运行层 | 包含（仅无 Denuvo 游戏） |
| D4 | 界面+核心 | Tauri（Rust 壳 + Web UI）+ Python sidecar |
| D5 | 分发层 | 无（内容始终从 Valve CDN 流过） |
| D6 | 下载路径 | 只走 Steam CDN |
| D7 | 数据更新 | 内置在线更新 + 手动导入兜底 |

## 2. 技术栈

| 层 | 选型 | 现状 |
|---|---|---|
| GUI 壳 | Tauri 2 + React/Vue + TypeScript | 待建 |
| 核心 | Python 3.12（现有 steam_research） | 已有，211 测试 |
| 核心↔GUI | 本地 HTTP + JSON-RPC + SSE 进度流 | 待建 |
| sidecar 打包 | PyInstaller onefile / Nuitka | 待建 |
| 索引/数据 | SQLite catalog.db + 索引 JSON v2 | 已有 |
| 下载/解密 | AES-256-CBC + LZMA/zstd/zip（openssl 加速） | 已有 |
| 运行层 | gbe_fork 注入 steam_api64.dll + steam_settings | 待集成 |
| 更新器 | 拉索引/语料增量，失败读本地 import 目录 | 待建 |

## 3. 架构

```text
Tauri 壳（Rust + WebView2）
   UI：游戏列表 / 进度 / 日志 / 设置
   Rust：窗口、进程守护、sidecar 启停、自动更新
        │ 127.0.0.1 + token（HTTP/JSON-RPC + SSE）
Python sidecar（steam_research）
   coverage → pipeline → restore → keys/index → runtime
        │ HTTPS（无需账号）
   Valve CDN
```

## 4. IPC 契约（已实现，S1）

> 实现：`src/py/steam_research/sidecar.py`，命令 `python -m steam_research.cli sidecar --port-file ...`。
> 鉴权：请求头 `X-Sidecar-Token`；进度：`GET /events?job=<id>&since=<n>`（SSE）。

| 方法 | 入参 | 出参 |
|---|---|---|
| coverage.check | appid | downloadable / depots / missing |
| restore.start | appid, target, depotWorkers, workers | jobId |
| restore.progress | jobId（SSE） | depotId / filesOk / bytes / speed / status |
| restore.cancel | jobId | cancelled |
| runtime.deploy | appid, target | ok / deployed |
| data.sync | — | indexVersion / keysCount / updated |

## 5. 现有代码复用

| 模块 | 新角色 | 改动 |
|---|---|---|
| sources/appinfo.py | depot+gid（带缓存） | 封装为 IPC |
| sources/manifest_mirror.py / manifest_index.py | 清单多源 + 任意 build 回退 | 无 |
| sources/hubcap.py | 按需清单兜底 | 暴露 key 配置 |
| keys.py | 语料 + key.vdf | 加增量更新 |
| depot.py / restore.py / pipeline.py | 下载解密组装 | 加进度回调 |
| coverage.py | 可用性判定 | 无 |

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| 清单/密钥覆盖不足（新作、Denuvo） | coverage 提前判定 + hubcap key 兜底 |
| Denuvo 无法免账户启动 | UI 标注 DRM 类型，明确不可启动 |
| 杀软误报（PyInstaller + DLL 释放） | 代码签名、不加壳、运行层与主程序分离 |
| Tauri 与 sidecar 生命周期 | Rust 侧进程守护 + 端口探测 + 退出清理 |
| 大文件中断 | chunk 续传 + state 断点 + 磁盘预检 |
| 更新源失效 | 多源 + 手动导入兜底 |

## 7. MVP（第一版）

1. 游戏列表（本地库 / 手动 appid）
2. coverage 判定并解释原因
3. 下载 → 解密 → 组装 → 校验报告
4. 进度 / 暂停续传 / 日志面板
5. 索引与密钥内置更新
6. 不含运行层、不含分发

## 8. 里程碑

| 阶段 | 内容 | 预估 |
|---|---|---|
| S1 | sidecar 协议 + Tauri 骨架 + 跑通一次真实下载 | 1 周 |
| S2 | 进度/续传/日志 + 更新器 + 打包 | 1 周 |
| S3 | 运行层插件 + 适配 + 签名 | 1–2 周 |
