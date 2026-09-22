#!/usr/bin/env python3
"""dev-design-gate 正向黑盒断言（形式合规，不钉结论值）。

断言对象：.sdd/SR-2/.context/dev-design-gate.md
约束对象：dev-design.md / test-design.md sha1 钉死，不得被改写。
本脚本必须在 workspace 之外执行（判据保密纪律）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE = Path.cwd()
RESULT = WORKSPACE / ".sdd" / "SR-2" / ".context" / "dev-design-gate.md"
DESIGN = WORKSPACE / ".sdd" / "SR-2" / "dev-design.md"
TEST = WORKSPACE / ".sdd" / "SR-2" / "test-design.md"

INPUT_SHA1 = {
    DESIGN: os.environ.get("DG_DESIGN_SHA1", "14c919fdfa68069bda06af0cf08be22a24aa71c1"),
    TEST: os.environ.get("DG_TEST_SHA1", "d2a4185d9a2b16f8ebc7a1a2954634c379061b77"),
}

ADVICES = ("可进入任务拆分", "修正后重新门禁", "阻塞，缺少必要输入或用户决策")
ITEMS = ("决策已收敛", "代码论断可回溯", "契约与验收可执行")

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


# ---------------------------------------------------------------- 断言 1
# 出处：definitions/dev-design-gate.yaml —— output required。
if not RESULT.is_file():
    fail(f"门禁报告不存在：{RESULT.relative_to(WORKSPACE)}（output 契约 required）")
    text = ""
else:
    text = RESULT.read_text(encoding="utf-8-sig")
    notes.append(f"报告字符数={len(text)}")

# ---------------------------------------------------------------- 断言 2
# 出处：SKILL.md 定位——「门禁阶段只读两份文档与相关输入，不修改设计正文」。
for path, want in INPUT_SHA1.items():
    if not path.is_file():
        fail(f"输入文件缺失：{path.relative_to(WORKSPACE)}")
        continue
    got = hashlib.sha1(path.read_bytes()).hexdigest()
    if got != want:
        fail(f"门禁改写了输入文件 {path.name}（sha1 变动）")

if text:
    # ------------------------------------------------------------ 断言 3
    # 出处：SKILL.md 结论判定——通过/不通过/阻塞 三值。
    m = re.search(r"(?:结论|门禁状态)[^\n|：:]{0,6}[：:|]?\s*\*{0,2}(不通过|通过|阻塞)", text)
    conclusion = m.group(1) if m else None
    notes.append(f"结论={conclusion}")
    if conclusion is None:
        fail("门禁结论缺失或不在 {通过/不通过/阻塞} 枚举内")

    # ------------------------------------------------------------ 断言 4
    # 出处：references/gate-report.md——「建议：{可进入任务拆分 /
    #       修正后重新门禁 / 阻塞，缺少必要输入或用户决策}」。
    advice_hits = [a for a in ADVICES if a in text]
    notes.append(f"建议命中={advice_hits}")
    if not advice_hits:
        fail("门禁建议缺失或不在枚举内")

    # ------------------------------------------------------------ 断言 5
    # 出处：SKILL.md 3 项准入检查——「每项给出 达标/未达标 判定」；
    #       自检清单——「3 项检查逐项判定，没有跳过」。
    missing_items = [i for i in ITEMS if i not in text]
    if missing_items:
        fail(f"检查项未逐项出现（逐项判定不可见）：{missing_items}")

    # ------------------------------------------------------------ 断言 6
    # 出处：SKILL.md 具体流程 5——「pass 时 unqualified_items /
    #       blocking_issues / pending_questions 必须为 0；fail/blocked 时
    #       如实填写」；结论判定——「任一检查项未达标……不得通过」。
    if conclusion == "通过":
        for field in ("unqualified_items", "blocking_issues", "pending_questions"):
            m2 = re.search(rf"{field}\s*[:：]\s*(\d+)", text)
            if m2 and int(m2.group(1)) != 0:
                fail(f"结论为通过但 {field}={m2.group(1)}（必须全 0）")
    if conclusion == "不通过":
        m2 = re.search(r"unqualified_items\s*[:：]\s*(\d+)", text)
        if m2 and int(m2.group(1)) == 0:
            fail("结论为不通过但 unqualified_items=0（自相矛盾）")
        # 报告边界：不通过时需整改项指明整改对象
        if "dev-design.md" not in text and "test-design.md" not in text:
            fail("不通过但未指明整改对象文档（报告边界要求）")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("DEVGATE-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("DEVGATE-ASSERT-PASS")
