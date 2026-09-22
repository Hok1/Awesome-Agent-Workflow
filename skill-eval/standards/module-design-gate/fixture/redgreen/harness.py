#!/usr/bin/env python3
"""assert_gate_common.py / assert_gate_defect.py 红绿验证。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
FIX = ROOT.parent / "fixture"
ASSERT_POS = ROOT.parent / "assert_gate_common.py"
ASSERT_NEG = ROOT.parent / "assert_gate_defect.py"

RESULT_REL = Path(".sdd/SR-1/AR-1/rbs-core/.context/模块设计门禁结果.md")
SPEC_REL = Path(".sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md")
TEST_REL = Path(".sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md")
CTX_REL = Path(".sdd/SR-1/AR-1/rbs-core/.context/详细设计上下文.md")

GREEN_RESULT = """# 模块设计门禁结果

## C1. 门禁结论

- 结论：**通过**
- 门禁建议：可进入 AICoding
- 八个准入维度均达标；阻断问题 0。

## C2. 阻断问题

无。

## C5. 上游设计反查

说明书 D1–D7 与 AR-clarify 一致；测试设计 TC1–TC27 覆盖 P0/P1。
"""

DEFECT_RESULT = """# 模块设计门禁结果

## C1. 门禁结论

- 结论：**不通过**
- 门禁建议：回测试设计补用例后重试
- 未达标维度：决策确定性、验证闭环性

## C2. 阻断问题

1. 决策确定性：D5 的「设计依据摘要」为「待定」，影响实现且未标为非阻断改进项。
2. 验证闭环性：TC99 仅写「补充单测覆盖异常场景」，缺输入/前置/断言/建议位置。
"""

CASE_LIST: list[dict] = [
    # ---------------- 正向（干净三件套） ----------------
    {"name": "pos-green", "script": ASSERT_POS, "expect": 0, "result": GREEN_RESULT},
    {"name": "pos-green-table-form", "script": ASSERT_POS, "expect": 0,
     "result": ("# 模块设计门禁结果\n\n## C1. 门禁结论\n\n"
                "| 项目 | 内容 |\n|---|---|\n"
                "| 门禁状态 | 通过 |\n| 门禁建议 | 可进入 AICoding |\n"
                "| 未达标维度 | 无 |\n\nD1–D7 已定稿，TC1–TC27 覆盖。\n")},
    {"name": "pos-red-no-result", "script": ASSERT_POS, "expect": 1, "result": None,
     "want": "门禁结果不存在"},
    {"name": "pos-red-spec-mutated", "script": ASSERT_POS, "expect": 1, "result": GREEN_RESULT,
     "mutate": "spec", "want": "改写了输入文件"},
    {"name": "pos-red-no-conclusion", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT.replace("结论：**通过**", "总体良好。"),
     "want": "门禁结论缺失"},
    {"name": "pos-red-no-advice", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT.replace("可进入 AICoding", "下一轮再说"),
     "want": "门禁建议缺失"},
    {"name": "pos-red-inconsistent", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT.replace("可进入 AICoding", "回 TOBE 补设计后重试"),
     "want": "结论与建议不一致"},
    {"name": "pos-red-phantom-d", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT.replace("D1–D7", "D1–D7、D99"),
     "want": "不存在的决策编号"},
    {"name": "pos-red-phantom-tc", "script": ASSERT_POS, "expect": 1,
     "result": GREEN_RESULT.replace("TC1–TC27", "TC1–TC27、TC88"),
     "want": "不存在的用例编号"},
    # ---------------- 反向（带缺陷三件套） ----------------
    {"name": "neg-green", "script": ASSERT_NEG, "expect": 0, "result": DEFECT_RESULT,
     "defect": True},
    {"name": "neg-green-table-form", "script": ASSERT_NEG, "expect": 0, "defect": True,
     "result": ("# 模块设计门禁结果\n\n## C1. 门禁结论\n\n"
                "| 项目 | 内容 |\n|---|---|\n"
                "| 门禁状态 | 不通过 |\n| 门禁建议 | 回测试设计补用例后重试 |\n"
                "| 未达标维度 | 验证闭环性 |\n\n"
                "## C2. 阻断问题\n\n"
                "1. 验证闭环性：TC99 为概要用例。\n")},
    {"name": "neg-red-wrongly-pass", "script": ASSERT_NEG, "expect": 1, "result": GREEN_RESULT,
     "defect": True, "want": "不得为「通过」"},
    {"name": "neg-red-missing-dim", "script": ASSERT_NEG, "expect": 1, "defect": True,
     "result": DEFECT_RESULT.replace("决策确定性、验证闭环性", "决策确定性"),
     "want": "未被判入「验证闭环性」"},
    {"name": "neg-red-dim-cheat", "script": ASSERT_NEG, "expect": 1, "defect": True,
     "result": DEFECT_RESULT.replace("未达标维度：决策确定性、验证闭环性",
                                     "未达标维度：无"),
     "want": "验证闭环性"},
]


def run_case(case: dict) -> tuple[bool, str]:
    case_dir = CASES / case["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir)
    suffix = "defect-" if case.get("defect") else ""
    for rel, name in [
        (SPEC_REL, suffix + "模块详细设计说明书.md"),
        (TEST_REL, suffix + "模块测试用例设计.md"),
        (CTX_REL, "详细设计上下文.md"),
    ]:
        target = case_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FIX / name, target)
    if case.get("mutate") == "spec":
        with open(case_dir / SPEC_REL, "a", encoding="utf-8") as f:
            f.write("\n被门禁改写的一行\n")
    if case["result"] is not None:
        target = case_dir / RESULT_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(case["result"], encoding="utf-8")

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
    return ok, f"{detail} | out={output.strip()[-320:]}"


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
