# 2026-11-06 · M1-T01：appmanifest (.acf/VDF) 解析器落地

## 现象
本机 6 个 `appmanifest_*.acf` 是 Steam 私有 VDF 文本格式：tab 分隔、引号包值、块嵌套，
还有 BOM / CRLF / `//` 注释 / 裸数字 token。标准库没有 VDF 解析器，第三方库里没有一个能只靠标准库跑。

## 根因
VDF 没有公开规范，格式"宽松但没容错"：多一个 `}` 或半个引号，Steam 自己会静默忽略整份文件，
所以坏数据不会报错，只会让清单对不上 —— 必须自己写词法器才能在出错时给出准确行号。

## 处置
1. `src/py/steam_research/parsers/acf.py`：手写词法器（BOM / CRLF / `//`、`/* */` / 转义 / 裸 token）+ 递归块解析。
2. 错误统一 `AcfParseError(line, column, path)`：unclosed 块报"开块行"，未闭合字符串报"起始行"，非法字符报当行。
3. 归一：`AcfAppState.to_app_record()` → 共享 `AppRecord`（`source="acf"`，manifest 按 depot 排序）。
4. 夹具先脱敏：`LastOwner` → 0、`LauncherPath` → `C:\Steam\steam.exe`，6 个真实文件里挑 3 种形态
   （2 depot / 6 depot 带 InstallScripts / 空 InstalledDepots）。
5. **先红后绿**：测试先跑出 ImportError，再写实现，28 条单测一次转绿。

## 踩到的坑（重要）
- `run-tests.ps1` 用 `python -m unittest discover -s tests` 收不到任何用例（子目录不是包），
  脚本把 "Ran 0 tests" 判成 exit 0 —— **空套件能过门禁**。已补 `tests/__init__.py` + `tests/unit/__init__.py`、
  加 `-t $Root`、0 用例返回 3。
- `gate-check.ps1` 取"最近 10 分钟内的报告"时没排序，拿到的可能是旧报告；已加 `Sort-Object LastWriteTime -Descending`。

## 复用建议
- 写解析器前先确认测试真的能跑起来（跑出红），否则"绿"可能只是没跑到。
- VDF 里数字都是字符串：比较前统一 `int()`，别拿 `"600"` 和 `600` 直接比。
- 模块化夹具目录按格式分：`tests/fixtures/acf/`、`tests/fixtures/contract/`，避免一个目录混多种格式。
