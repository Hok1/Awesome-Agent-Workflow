#!/usr/bin/env python3
"""dev-design-gate 反向黑盒断言（带缺陷输入，期望命中并判不通过）。"""

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
RESULT = WORKSPACE / ".sdd" / "SR-2" / ".context" / "dev-design-gate.md"

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


# 先跑正向形式断言（defect 版 sha1 经环境变量覆盖）
env = os.environ.copy()
env["DG_DESIGN_SHA1"] = "629aa2007841f83a39e86a4127e7676bd361dd61"
env["DG_TEST_SHA1"] = "d58d9a752fbd31203468e11914caf76c70ec2ab8"
common = subprocess.run(
    [sys.executable, str(Path(__file__).with_name("assert_devgate_common.py"))],
    cwd=WORKSPACE, env=env, capture_output=True, text=True, encoding="utf-8",
    errors="replace", timeout=120, check=False,
)
notes.append(f"形式断言 exit={common.returncode}")
if common.returncode != 0:
    fail("形式断言未通过：\n" + common.stdout.strip()[-1000:])

if RESULT.is_file():
    text = RESULT.read_text(encoding="utf-8-sig")

    # ------------------------------------------------------------ 断言 7
    # 出处：SKILL.md 结论判定——「任一检查项未达标……不得通过」；
    #       夹具含检查项 1（方案待定）与检查项 3（覆盖矩阵漏 A3）的缺陷。
    m = re.search(r"(?:结论|门禁状态)[^\n|：:]{0,6}[：:|]?\s*\*{0,2}(不通过|通过|阻塞)", text)
    if m and m.group(1) == "通过":
        fail("夹具含两处未达标缺陷，结论不得为「通过」")

    # ------------------------------------------------------------ 断言 8
    # 出处：SKILL.md 3 项准入检查表——缺陷 1 属检查项 1「决策已收敛」，
    #       缺陷 2 属检查项 3「契约与验收可执行」；「未达标项必须指明问题出处」。
    #       判定落点：需整改项/未达标项区域（避免被判定表的逐项列出骗检——
    #       检查项名在判定表中无论达标与否都会出现）。
    rect_zone = ""
    m2 = re.search(r"##\s*需整改项[^\n]*\n(.*?)(?=\n##\s|\Z)", text, re.S)
    if m2:
        rect_zone = m2.group(1)
    if not rect_zone:
        fail("报告缺「需整改项」章节（不通过时必填）")
    else:
        if not re.search(r"检查项?\s*1|决策已收敛", rect_zone):
            fail("需整改项未命中检查项 1（决策已收敛：方案含「待定」）")
        if not re.search(r"检查项?\s*3|契约与验收可执行", rect_zone):
            fail("需整改项未命中检查项 3（契约与验收可执行：覆盖矩阵漏 A3）")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("DEVGATE-DEFECT-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("DEVGATE-DEFECT-ASSERT-PASS")
