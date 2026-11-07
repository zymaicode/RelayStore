# 2026-11-06 · 未购买游戏直链：从 401 到 sha1 命中

## 现象
直链 manifest/chunk 都能 200 拿到，但 chunk 解不出东西：raw sha1 对不上，LZMA 也解不开。

## 根因（三个都不在文档里）
1. **manifest 不是裸 protobuf**：它是「u32 magic + i32 length + blob」多段结构，段魔数 `71F617D0`(payload) / `1F4812BE`(meta) / `1B81B817`(sig) / `32C415AB`(end)。按裸 protobuf 解会撞到 wire type 4。
2. **FileMapping.chunks 是字段 6**，不是 2（2 是 size）。猜字段号会得到「文件有名字、零 chunk」。
3. **chunk 是 AES 密文**：`iv = AES-256-ECB-decrypt(前 16 B)`，其余 `AES-256-CBC(iv)+PKCS7`；解密后首字节才看到 `VZa`(LZMA) / `VSZa`(zstd) / `PK`(zip)。直接拿密文当压缩流必然失败。

## 处置（全部来自 SteamKit2 源码，不是猜）
- `opensource/SteamKit2-SteamRE`：`Types/DepotManifest.cs`（分段容器）、`Steam/CDN/DepotChunk.cs`（ECB-IV→CBC→按魔数分派）、`Util/VZstdUtil.cs`（8 字节头 + frame + 15 字节尾）。
- `depot.py`：纯标准库 AES-256 解密（FIPS-197/SP800-38A 向量验证）+ VZip(7+5+stream+10) + Zip + VZstd(8+frame+15)。
- `manifest.py`：分段容器 + protobuf 字段（1 filename / 6 chunks；chunk: 1 sha,2 crc fixed32,3 offset,4 cb_original,5 cb_compressed）。
- 实测：3DMark depot 1276160 → manifest 19,054 B / 21 文件 / 405 chunk → 首 chunk 191,584 B → 明文 1,048,576 B → sha1 命中。

## 复用建议
- 拿不准二进制格式时，先去 `opensource/` 里找**能跑的实现**对照，比搜索快十倍，而且参数是事实不是传闻。
- 「HTTP 200 + 字节数对」只能证明链路通；「解密后 sha1 对」才证明内容对。两者要分开写进验收。
- zstd 在 Python 3.12 标准库里没有：本机用 `zstd.exe` 子进程兜底，并把「找不到可执行文件」变成明确错误而不是静默失败。
- 未购买 app 的 **gid** 仍是瓶颈（steamcmd.net 常返回 `_missing_token`）；镜像仓库文件名 `<depot>_<gid>.manifest` 可以反查，这是下一步要自动化的。
