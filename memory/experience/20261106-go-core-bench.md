# 2026-11-06 · Go 内核实测：快 63 倍，但不是瓶颈

## 环境
- Go 1.27.3 zip 解压到 `D:\Go`（不写 C 盘），用户级 env：GOROOT/GOPATH(D:\GoPath)/GOCACHE(D:\GoCache)/GOPROXY + PATH。
- `go env` 校验；proxy.golang.org 可达。

## 原型 `tools/steamcore`
- AES-256-CBC（IV = ECB 解密首块）+ VZip/VZstd/zip + sha1；3.7 MB 静态 exe。
- VZip 技巧：把 5 字节 props + footer 里的 8 字节长度拼成 classic .lzma 头再交给 ulikunitz/xz/lzma。

## 实测（同一真实 chunk）
| 实现 | 每 chunk | 吞吐 |
|---|---|---|
| Go | 0.62 ms | 1,613 MB/s |
| Python（openssl + zstd 子进程） | 38.98 ms | 25.7 MB/s |

## 结论
138 GB ≈ 141k chunk：Go 1.5 min CPU，Python 92 min CPU（8 线程 ≈ 11.5 min）；下载 3.8 h 才是主导。
→ 不为性能换语言；Go 只留作可选内核/打包优势。

## 教训
「快 63 倍」听起来震撼，但换算到端到端墙钟只占 5% —— 先算分母，再优化分子。
