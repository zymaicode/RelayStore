# 2026-11-06 · 借力生态三件套 + 全项目优化

## 做了什么
1. **steamtools 探针**：`sources/steamtools.py` → `coverage --steamtools` 输出 `in_db/message/lua_url/key_url`。4115450 实测 `not_in_db`。
2. **Hubcap 接入**：`coverage --hubcap-key` 与 `restore-app --hubcap-key`，镜像 404 且索引为空时按需拉 manifest，报告记 `hubcap:<bytes>` / `source_url=hubcap:<path>`。
3. **keys-sync**：默认 3 个语料 URL + `--steamtools-app` 的 key.vdf，输出 keys/new_keys/new_depots。

## 踩坑（下次少花时间）
- urllib 的 SSL 失败是 **URLError 包着 SSLError**，只 catch `HTTPError` 会让探针直接抛出去；正确做法是兜底 `except Exception` 后用未验证 context 重试。
- 语料 URL 会失效：`qwe213312/.../depotkeys.json` 现在 404，`keys-sync` 必须把单个语料失败降级为 warning，不能中断整批。
- 相对导入：`sources/` 下引用上层模块要 `..xxx`，写成 `.xxx` 会找 `steam_research.sources.xxx`。
- ARD 表格行编辑要用**唯一整行**做锚点，用半截前缀会把别的行污染（这次修过一次 M0-T02）。

## 复用建议
- 外部服务接入一律走「可注入 fetch/post」：离线可测，线上可换。
- 判断新作是否进生态：一条 `coverage --steamtools` 就够，别先下载。
- Hubcap 是「按需 manifest」的正确位置：只补镜像缺的那一块，不做主路径。
