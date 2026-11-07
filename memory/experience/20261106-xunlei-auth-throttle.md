# 2026-11-06 · 迅雷分享下载：鉴权通了，带宽被封

## 鉴权怎么拿（可复用）
1. 用独立 profile 打开 pan.xunlei.com 让用户登录；
2. `localStorage['credentials_Xqp0kJBXWhwaTpB6']` 里是 `{token_type, access_token, refresh_token, expires_at}`；
3. 组装 `Authorization: Bearer <access_token>` + cookie 串，存 `backup/private/.env`；
4. 请求头仍要 `X-Client-Id/X-Client-Version/X-Device-Id/X-Captcha-Token`（captcha 免登录可拿）。

## 两个坑
- **转存自己的分享会报 `file_restore_own`**：分享归属当前账号时不要走 restore，直接 `share/file_info`（带鉴权）拿 `web_content_link`。
- **非会员限速 ~10 KB/s**：4 GB 分卷与 3 MB 图片同速，说明是账号级限速，不是单文件问题。138 GB 要 160 天，分批方案不可行。

## 教训
先测带宽再排计划：计划里写「每批 4 GB」之前，应该先用 `Range: bytes=0-52428799` 测 45 秒吞吐。10 KB/s 这种量级，一次 curl 就能否掉整个方案。
