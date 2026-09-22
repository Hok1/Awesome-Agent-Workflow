#!/usr/bin/env python3
"""assert_devgate_common.py / assert_devgate_defect.py 红绿验证。"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
FIX = ROOT.parent / "fixture"
ASSERT_POS = ROOT.parent / "assert_devgate_common.py"
ASSERT_NEG = ROOT.parent / "assert_devgate_defect.py"

RESULT_REL = Path(".sdd/SR-2/.context/dev-design-gate.md")
DESIGN_REL = Path(".sdd/SR-2/dev-design.md")
TEST_REL = Path(".sdd/SR-2/test-design.md")

GREEN_RESULT = """# 轻量设计门禁结果 · SR-2

## 结论

**通过** —— 三项准入全部达标。

建议：可进入任务拆分

## 检查判定

| # | 检查项 | 判定 |
|---|---|---|
| 1 | 决策已收敛 | 达标 |
| 2 | 代码论断可回溯 | 达标 |
| 3 | 契约与验收可执行 | 达标 |

## 需整改项

无。

## 存疑 / 阻塞项

无。

## 统计

- unqualified_items: 0
- blocking_issues: 0
- pending_questions: 0
"""

DEFECT_RESULT = """# 轻量设计门禁结果 · SR-2

## 结论

**不通过** —— 方案含未决项且覆盖矩阵漏验收标准。

建议：修正后重新门禁

## 检查判定

| # | 检查项 | 判定 |
|---|---|---|
| 1 | 决策已收敛 | 未达标 |
| 2 | 代码论断可回溯 | 达标 |
| 3 | 契约与验收可执行 | 未达标 |

## 需整改项

- **[检查项 1]** 问题：方案中溢出处理写「待定」。
  整改对象：dev-design.md
  整改方向：明确选择 checked_add。
- **[检查项 3]** 问题：覆盖矩阵缺验收标准 A3。
  整改对象：test-design.md
  整改方向：补 A3 行与对应用例或登记回流。

## 存疑 / 阻塞项

无。

## 统计

- unqualified_items: 2
- blocking_issues: 0
- pending_questions: 0
"""

CASE_LIST: list[dict] = [
    {"name": "pos-green", "script": ASSERT_POS, "expect": 0, "result": GREEN_RESULT},
    {"name": "pos-red-no-result", "script": ASSERT_POS, "expect": 1, "result": None,
     "want": "门禁报告不存在"},
    {"name": "pos-red-design-mutated", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT, "mutate": "design", "want": "改写了输入文件"},
    {"name": "pos-red-no-conclusion", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT.replace("**通过** —— 三项准入全部达标。", "总体不错。"),
     "want": "结论缺失"},
    {"name": "pos-red-no-advice", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT.replace("可进入任务拆分", "下一轮再说"),
     "want": "建议缺失"},
    {"name": "pos-red-missing-item", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT.replace("契约与验收可执行", "验收情况"),
     "want": "逐项判定不可见"},
    {"name": "pos-red-pass-nonzero", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT.replace("unqualified_items: 0", "unqualified_items: 1"),
     "want": "必须全 0"},
    {"name": "pos-red-fail-zero", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT.replace("**通过**", "**不通过**").replace("可进入任务拆分", "修正后重新门禁"),
     "want": "自相矛盾"},
    {"name": "neg-green", "script": ASSERT_NEG, "expect": 0, "result": DEFECT_RESULT,
     "defect": True},
    {"name": "neg-red-wrongly-pass", "script": ASSERT_NEG, "expect": 1,
     "result": GREEN_RESULT, "defect": True, "want": "不得为「通过」"},
    {"name": "neg-red-missing-item1", "script": ASSERT_NEG, "expect": 1, "defect": True,
     "result": DEFECT_RESULT.replace("- **[检查项 1]** 问题：方案中溢出处理写「待定」。\n  整改对象：dev-design.md\n  整改方向：明确选择 checked_add。\n", ""),
     "want": "未命中检查项 1"},
    {"name": "neg-red-missing-item3", "script": ASSERT_NEG, "expect": 1, "defect": True,
     "result": DEFECT_RESULT.replace("- **[检查项 3]** 问题：覆盖矩阵缺验收标准 A3。\n  整改对象：test-design.md\n  整改方向：补 A3 行与对应用例或登记回流。\n", ""),
     "want": "未命中检查项 3"},
    {"name": "neg-red-no-rect-section", "script": ASSERT_NEG, "expect": 1, "defect": True,
     "result": DEFECT_RESULT.replace("## 需整改项", "## 整改列表").replace("- **[检查项 1]**", "- **决策收敛**").replace("- **[检查项 3]**", "- **覆盖**"),
     "want": "需整改项"},
]


def run_case(case: dict) -> tuple[bool, str]:
    case_dir = CASES / case["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir)
    prefix = "defect-" if case.get("defect") else ""
    for rel, name in [(DESIGN_REL, prefix + "dev-design.md"), (TEST_REL, prefix + "test-design.md")]:
        target = case_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FIX / name, target)
    if case.get("mutate") == "design":
        with open(case_dir / DESIGN_REL, "ab") as f:
            f.write("\n改写\n".encode("utf-8"))
    if case["result"] is not None:
        target = case_dir / RESULT_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(case["result"].encode("utf-8"))

    result = subprocess.run(
        [sys.executable, str(case["script"])],
        cwd=case_dir, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120, check=False,
    )
    output = result.stdout + result.stderr
    ok = result.returncode == case["expect"]
    detail = ""
    if ok and case["expect"] == 1:
        want = case.get("want", "")
        ok = want in output
        detail = f"命中条款[{want}]" if ok else f"退出码正确但未命中条款[{want}]"
    elif ok:
        detail = "PASS"
    else:
        detail = f"期望退出码 {case['expect']} 实得 {result.returncode}"
    return ok, f"{detail} | out={output.strip()[-280:]}"


def main() -> int:
    mismatches = 0
    for case in CASE_LIST:
        ok, detail = run_case(case)
        mark = "OK " if ok else "BAD"
        print(f"[{mark}] {case['name']}: {detail}")
        if not ok:
            mismatches += 1
    print(f"\n共 {len(CASE_LIST)} 用例，不符预期 {mismatches} 个")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
