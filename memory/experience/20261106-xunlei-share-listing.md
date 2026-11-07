# 2026-11-06 · 迅雷分享免登录列举（协议还原）

## 协议（来自 gopeed-extension-xunlei）
1. `POST https://xluser-ssl.xunlei.com/v1/shield/captcha/init`，body 含 client_id/client_version/device_id/meta.captcha_sign；
   `captcha_sign = '1.' + md5 链`：初值 `CLIENT_ID+CLIENT_VERSION+'pan.xunlei.com'+device_id+timestamp`，依次追加 14 个 salt 各做一次 md5。
2. 请求头固定：`X-Client-Id: Xqp0kJBXWhwaTpB6`、`X-Client-Version: 1.92.89`、`X-Device-Id`、`X-Captcha-Token`、`Referer: https://pan.xunlei.com/`。
3. 列表：`GET /drive/v1/share?share_id&pass_code&limit=100&space=&thumbnail_size=SIZE_MEDIUM&scene=NORMAL` → 根 + `pass_code_token`；子目录用 `GET /drive/v1/share/detail?parent_id&pass_code_token`。
4. 目录判定：`kind` 是字符串 `drive#folder` / `drive#file`（不是对象）。
5. 转存/下载直链需要本人 Cookie + Authorization；**列目录不需要登录**。

## 该分享的实测定性
- 53 文件 / 148,876,640,610 B（138.65 GiB）。
- `PBZ.part001.exe` 是 **exe** 而非 rar：真正的执行入口是它（自解压/安装器）→ 最高风险点。
- 11 份 `解压必看，领取迅雷会员.JPG` 广告图 + MOD 合集里混入成人 MOD、GCM 修改器安装包、一键安装包。
- 商店页确证 Denuvo；发售后 9 天的可玩学习版不合逻辑 → 引流包概率高。

## 复用
`python -m steam_research.cli pan-list <url>` 先看清单与大小，再决定要不要下 —— 对外部网盘来源的默认动作。
