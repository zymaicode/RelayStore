# 2026-11-06 · Go 完整内核：10 MB 做到 manifest+restore

## 结论
Go 可以独立完成「清单解析 → chunk 解密解压 → CDN 并发还原」，单文件 **10.12 MB**，输出与 Python **逐字节一致**。

## 关键实现点
- 分段容器：`[magic][len][blob]` 直到 `0x32C415AB`；payload 里是 protobuf，不是长度前缀条目（一开始就搞错了）。
- FileMapping 字段：1 名称、2 大小、5 sha_content、6 chunks、7 linktarget。
- ChunkData 的 crc 是 **fixed32（wire 5）**，不是 fixed64 —— wire 判错会直接解析失败。
- VZip 用 `lzma.ReaderConfig{DictCap}.NewReader()`（不是 `lzma.NewReaderConfig`，没有这个函数）。
- 零 chunk 条目是目录/链接标记，必须 `MkdirAll`，不能当空文件写。

## 数据（3DMark depot 1276160）
- manifest：21 文件 / 405 chunk / 412,115,023 B
- restore 首文件：3,455,847 B，sha256 与 Python 相同
- 解码：0.62 ms/chunk，1,613 MB/s

## 教训
跨语言重写最省时间的做法：先对齐「数字」（文件数/字节数/哈希），再谈性能。三个数字一相等，逻辑就对了。
