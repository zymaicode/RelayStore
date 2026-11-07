# src — 主代码区（main）

项目主代码。**未经测试的代码不得进入本区**（门禁见 [CLAUDE.md](../CLAUDE.md) §3）。

## 目录约定

```text
src/
  py/
    requirements.txt          # 仅测试依赖（pytest）；核心零依赖
    steam_research/
      cli.py                  # CLI 入口
      paths.py net.py cache.py
      model.py catalog.py
      parsers/{acf,hub_json,lua}.py
      sources/{base,local_snapshot,github_raw,morrenus,resolver}.py
      lua_gen.py verify.py report.py
    vendor_ref/               # 从 opensource 复制来的参考实现（带来源头）
  data/                       # 运行时数据，不入版本库
    cache/ catalog.db out/ tmp/
```

## 规则

- 不 import `opensource/` 里的任何路径；要用的代码复制到 `vendor_ref/` 并写来源头。
- 所有路径从 `paths.py` 取，禁止硬编码盘符。
- 提交前必须：`pytest` 全绿 + 报告落在 `tests/reports/` + ARD 更新。
- 新增依赖需在 `requirements.txt` 写注释说明理由。
