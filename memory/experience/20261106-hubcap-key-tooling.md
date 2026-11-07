# 2026-11-06 · hubcap key 工具化：拿到 key 之后一条命令到位

## 现象
M1-T10 卡在「没有真实 key」：hubcapmanifest 的免费 key 必须用户本人用 Discord 登录后在站内生成，
Agent 既不能代登录，也不该索取账号密码。每次卡在这种「只差一步人工」的地方，最容易让工具链停在半成品。

## 处置（把人工步骤压到只剩 1 次粘贴）
1. `secrets.py`：环境变量 > `backup/private/.env`，空值不覆盖；.env 解析容忍注释、引号、`export ` 前缀。
2. `is_valid_key`：`^smm_[0-9a-f]{96}$`（此格式来自 LuaTools 实现，不是猜的）——格式错直接本地拒绝，不烧配额。
3. `hubcap_stats`：/api/v1/user/stats 给出 username / daily_usage / daily_limit / can_make_requests / expires_at。
4. `cli.py hubcap-check`：一条命令完成「格式校验 → 配额查询 → 真拉一份 manifest → 落缓存」，退出码分级 0/2/4/5。
5. 输出永远只显示 key 前 8 + 后 4 位；key 永不进日志、JSON 明文、版本库。

## 复用建议
- 遇到「必须本人登录才能拿凭据」的任务，别停在等待：把**凭据之后的全部流程**做成一条命令 + 明确退出码，
  用户只需粘贴一次，Agent 侧立刻可验证。
- 凭据读取顺序固定为「环境变量 > private/.env」，且 private 目录必须被 .gitignore 与快照脚本双重排除。
- 掩码输出是硬要求：连 `--key` 这种显式传参也要掩码，避免 shell history / 截图泄露。
