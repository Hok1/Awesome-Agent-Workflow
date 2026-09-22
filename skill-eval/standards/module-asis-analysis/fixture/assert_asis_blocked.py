#!/usr/bin/env python3
"""module-asis-analysis 反向黑盒断言：无 software_architecture.md 时必须 fail-closed。

断言对象：workspace 全域（产物可以不存在，但任何 ASIS 类残留都必须带阻塞标记）。
出处：SKILL.md 模块边界规则——「如果 .sdd/software_architecture.md 不存在、不可读或
不包含足以识别目标模块边界的内容，立即中断 ASIS，并在详细设计上下文或返回结果中标记
ASIS 阻塞；不得继续用代码结构、README、根目录架构文档或用户口述推断边界。」
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WORKSPACE = Path.cwd()

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


# ---------------------------------------------------------------- 前提确认
# 本断言只在夹具缺失时有效；若架构文档意外存在，说明 setup 错了。
arch = WORKSPACE / ".sdd" / "software_architecture.md"
if arch.is_file():
    print("ASIS-BLOCKED-ASSERT-ERROR: software_architecture.md 意外存在，反向用例前提不成立")
    raise SystemExit(2)

# ---------------------------------------------------------------- 断言 1
# 出处：SKILL.md 目标/成果物协作规则——ASIS 阶段不得创建正式
#       《模块详细设计说明书.md》（任何情况下）。
formal = sorted(WORKSPACE.glob(".sdd/**/模块详细设计说明书.md"))
if formal:
    fail(f"ASIS 阶段创建了正式说明书（职责边界禁止）：{[str(p) for p in formal]}")

# ---------------------------------------------------------------- 断言 2
# 出处：SKILL.md 模块边界规则——缺失架构文档时「立即中断 ASIS，并在详细设计
#       上下文或返回结果中标记 ASIS 阻塞」。产物不存在=中断无残留，合规；
#       产物若存在，必须显式标记阻塞/blocked，且不得声明确定的模块边界。
contexts = sorted(WORKSPACE.glob(".sdd/SR-1/*/*/.context/详细设计上下文.md"))
stray = [
    p
    for p in sorted(WORKSPACE.glob(".sdd/SR-1/**/*.md"))
    if p.name not in ("original-requirement.md", "SR-design.md", "key-lifecycle-context.md")
    and ".context" not in p.parts
]
notes.append(f"context 产物={len(contexts)} 其他新增 md={len(stray)}")

BLOCK_MARK = re.compile(r"\bblocked\b|ASIS 阻塞|状态[：:]\s*阻塞|立即中断", re.IGNORECASE)
if contexts:
    for path in contexts:
        text = path.read_text(encoding="utf-8-sig")
        if not BLOCK_MARK.search(text):
            fail(f"{path}：无架构文档却产出了不带阻塞标记的 ASIS context")
        # 声明了确定边界（declared by ...）而无 blocked 标记 = 推断边界
        if "declared by software_architecture.md" in text and not BLOCK_MARK.search(text):
            fail(f"{path}：在架构文档缺失时声明了确定模块边界（推断边界违规）")
else:
    notes.append("无 context 产物（中断无残留，合规）")

for path in stray:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if ("模块边界" in text or "ASIS" in text) and not BLOCK_MARK.search(text):
        fail(f"{path}：疑似把 ASIS 分析写到了契约外路径，且无阻塞标记")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("ASIS-BLOCKED-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("ASIS-BLOCKED-ASSERT-PASS")
