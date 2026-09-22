#!/usr/bin/env python3
"""module-design-gate 反向黑盒断言（带缺陷三件套，期望命中缺陷并判不通过）。

在正向形式断言基础上追加缺陷命中条款。
本脚本必须在 workspace 之外执行（判据保密纪律）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE = Path.cwd()
RESULT = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / ".context" / "模块设计门禁结果.md"

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


# ---------------------------------------------------------------- 先跑正向形式断言
# 出处：与正向相同的契约（结论枚举/建议枚举/一致性/输入不改写/编号可反查）。
# 本用例输入为 defect 夹具，sha1 钉版值经环境变量覆盖。
env = os.environ.copy()
env["MDG_SPEC_SHA1"] = "37078038bbe27a7a6eafe0249e8c5f4800be2068"
env["MDG_TEST_SHA1"] = "0415472918dfd1082e37fd76e0914ce8e73877fc"
env["MDG_CTX_SHA1"] = "36577b460f1b4c23c55b5cce0915c369922199a9"
common = subprocess.run(
    [sys.executable, str(Path(__file__).with_name("assert_gate_common.py"))],
    cwd=WORKSPACE, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    timeout=120, check=False,
)
notes.append(f"形式断言 exit={common.returncode}")
if common.returncode != 0:
    fail("形式断言未通过：\n" + common.stdout.strip()[-1200:])

if RESULT.is_file():
    text = RESULT.read_text(encoding="utf-8-sig")

    # ------------------------------------------------------------ 断言 7
    # 出处：SKILL.md 门禁结论——「不通过：存在必须整改的问题」；
    #       夹具植入两处必须整改缺陷（D5 依据=待定；TC99 概要用例），
    #       结论不得为 通过。形态容差与 common 断言 3 一致。
    m = re.search(
        r"(?:门禁状态|门禁结论|结论)[^\n|：:]{0,6}[：:|]\s*\*{0,2}(不通过|通过|阻塞)",
        text,
    )
    if m and m.group(1) == "通过":
        fail("夹具含两处必须整改缺陷，结论不得为「通过」")

    # ------------------------------------------------------------ 断言 8
    # 出处：SKILL.md 维度表 + 成果物协作规则——概要用例（TC99）「门禁必须判定
    #       验证闭环性不通过」；「结果文件只列未达标维度及其问题」——
    #       判定字段是「未达标维度」，不是全文是否提到维度名（防止被
    #       「七个维度达标」式过程表骗检）。
    m = re.search(r"未达标维度[^\n|：:]{0,4}[：:|]\s*\*{0,2}([^\n|]+)", text)
    dims = m.group(1) if m else ""
    notes.append(f"未达标维度字段={dims.strip()[:120]}")
    if not m:
        fail("报告缺少「未达标维度」字段（结论不通过时必须列出未达标维度）")
    elif "验证闭环性" not in dims:
        fail(f"TC99 概要用例未被判入「验证闭环性」未达标维度（字段值：{dims.strip()[:80]}）")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("MDG-DEFECT-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("MDG-DEFECT-ASSERT-PASS")
