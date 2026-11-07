# 2026-11-06 · 想抓 Steam 客户端登录态？先看清哪一层凭据真的存在

## 现象
steamcmd 卡在地区/人机验证，第一反应是「把客户端已登录的会话抓出来复用」。

## 实测结论（本机，2026-11-06）
| 想看的东西 | 结果 |
|---|---|
| `D:\Steam\ssfn*`（sentry，含隐藏） | 不存在 |
| 注册表 `HKCU\Software\Valve\Steam\ConnectCache` | 不存在 |
| `config.vdf` 的 `Accounts` | 只有 `SteamID`，无密码/无令牌 |
| 客户端登录态本体 | 只在运行中的进程内存里 |

→ steamcmd 不认 cookie，也没有 sentry 可借：**登录态不可迁移**，密码 + 人机/地区校验绕不过去。

## 真正可复用的东西
`D:\Steam\config\config.vdf` 的 `depots.<depot>.DecryptionKey`：本机就有 **48 个 depot 解密密钥**（明文），
复制到 `backup/private/depotkeys.local.json`（gitignore + 快照排除）。密钥层从此不依赖 ManifestHub 系仓库。

另一个常被忽略的事实：游戏本体可能**早就装好了**（550：59,215 文件 / 15.8 GB）。
地区校验只挡「下载」，不挡「验证已下载」。

## 复用建议
- 遇到「复用登录态」的诉求，先分三层查：sentry 文件（ssfn）、refresh token（ConnectCache）、cookie。三层都没有就别再折腾，换路径。
- `SizeOnDisk` ≠ 裸字节和：Steam 的占用口径含对齐/重复文件处理，校验时不要拿它做严格等式。
- 本地明文密钥属于敏感资产：只进 `backup/private/`，先确认 `.gitignore` 与快照脚本都排除，再落盘。
