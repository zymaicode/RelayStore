# tests — 测试区

未知功能 / 模块 / 接口 / 代码，一律先在这里验证；**没过测试就不许进 src**。

## 子区

| 子区 | 用途 | 命名 |
|---|---|---|
| `unit/` | 纯函数、解析器、校验 | `test_<module>.py` |
| `integration/` | 模块协作、SQLite、缓存、文件系统 | `test_<flow>.py` |
| `contract/` | 外部源响应格式（脱敏样本，不联网） | `test_<source>_contract.py` |
| `e2e/` | CLI 全链路 | `test_cli_<scenario>.py` |
| `compatibility/` | Lua/ACF 与现有工具互通 | `test_lua_compat.py` |
| `security/` | 脱敏、路径穿越、SSRF、超大文件、投毒 | `test_<threat>.py` |
| `fixtures/` | 脱敏样本（可入库；禁止真实凭据/账号） | `<kind>/<name>.sample` |
| `reports/` | 每次运行的报告留档（不入库，保留最近 N 份） | `test-report-<ts>.txt` |

## 强制流程

1. 写夹具 → 2. 写测试并确认**失败** → 3. 写实现 → 4. 跑到**通过** → 5. 落报告 → 6. 更新 ARD。

```powershell
pwsh -File tools\scripts\run-tests.ps1 -All      # 全量 + 报告
pwsh -File tools\scripts\run-tests.ps1 -Area unit
pwsh -File tools\scripts\gate-check.ps1 -TaskId M1-T01
```

## 门禁（gate-check.ps1 校验）

- [ ] 对应测试存在且 `pytest` 退出码 0
- [ ] `tests/reports/` 有本次报告文件
- [ ] `docs/ARD.md` 中该任务状态不是 `pending`
