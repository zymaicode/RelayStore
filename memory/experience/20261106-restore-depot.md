# 2026-11-06 · 未购买游戏整 depot 还原：405 chunk、10 文件、全 sha1 通过

## 结果
3DMark depot 1276160（未购买）：**405/405 chunk** 解码通过，**10/10 文件** sha1 通过，412,115,023 B，耗时 1.6 s（缓存全命中）/ 首次约 60 s。

## 四个卡点与解法
1. **gid 从哪来**：`steamcmd +login anonymous "+app_info_print <appid>"` 对未购买 app 也返回 depots+gid（Portal 2 10 个、3DMark 8 个）。
   比 token API 和镜像文件名反查都稳。注意 Windows 下输出含非 GBK 字节：**按 bytes 读再 utf-8/cp1252 解码**，不要 `text=True`。
2. **AES 太慢**：纯 Python 每 MB 6.6 s → 405 chunk 要 40 分钟。大块改走 `openssl enc -d -aes-256-cbc`（-K/-iv/-nopad），单 chunk 0.37 s。
3. **VZip 解不开**：Steam 的 LZMA 流**没有 EOS 标记**，`lzma.decompress(FORMAT_ALONE)` 必报 'ended before end-of-stream'。
   正确做法：`LZMADecompressor(FORMAT_RAW, filters=[LZMA1, dict/lc/lp/pb])` + `max_length=footer 里的解压长度`，再校验 CRC32。
4. **清单里有目录项**：零 chunk 或带 `linktarget` 的条目是目录/链接。当成空文件写，后面建子目录就 `WinError 183`。
   处理：这类条目只 `mkdir`，并在报告里单列 `directories`（本例 11 个）。

## 验收口径（可复用）
- chunk 级：`len(plain) == cb_original` 且 `sha1(plain) == chunk.sha`
- 文件级：`size == FileMapping.size` 且 `sha1(file) == sha_content`
- 目录级：`files_ok == files_total` 且 `files_failed == 0`
三者分开统计，报告里都写出来，避免「chunk 全过但文件拼错」被当成成功。

## 复用建议
- 并发下载时把失败重试放在**单 chunk 层**（3 次 + 退避）；整批任一处 SSL EOF 就整体失败，等于白跑 400 个 chunk。
- 大文件 IO 与解码都走内容寻址缓存（`.chunks/<sha>`），重跑/续跑成本接近 0。
- 报告里保留 `errors[:20]`，人类第一眼看到的就是失败原因，不用翻日志。
