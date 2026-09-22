#!/usr/bin/env python3
"""task-split 黑盒断言：只读产物文件与 workspace，不 import skill 任何源码。

断言对象：.sdd/SR-1/AR-1/rbs-core/tasks-overview.md
约束对象：三份输入（说明书/测试设计/门禁结果）sha1 钉死，不得被改写。
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
ARTIFACT = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / "tasks-overview.md"
SPEC = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / "模块详细设计说明书.md"
TEST = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / "模块测试用例设计.md"
GATE = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / ".context" / "模块设计门禁结果.md"

INPUT_SHA1 = {
    SPEC: os.environ.get("TS_SPEC_SHA1", "f409b788cb6872e8d0bdcd532cc6f74ee5140729"),
    TEST: os.environ.get("TS_TEST_SHA1", "fbd4353d8b24a891738123639c730e3524ba2b4a"),
    GATE: os.environ.get("TS_GATE_SHA1", "cb9fa1a8e42bf59306561ae25cb3705ac0ac6fbf"),
}

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


# ---------------------------------------------------------------- 断言 1
# 出处：definitions/task-split.yaml —— output 契约 required。
if not ARTIFACT.is_file():
    fail(f"产物不存在：{ARTIFACT.relative_to(WORKSPACE)}（output 契约 required）")
    text = ""
else:
    text = ARTIFACT.read_text(encoding="utf-8-sig")
    notes.append(f"产物字符数={len(text)}")

# ---------------------------------------------------------------- 断言 2
# 出处：SKILL.md 任务计划边界·禁止写入——「生成独立 T[N]-*.md 任务文件」。
stray = [
    p for p in WORKSPACE.glob(".sdd/**/*.md")
    if re.match(r"T\d+-", p.name)
]
if stray:
    fail(f"生成了独立任务文件（禁止）：{[p.name for p in stray]}")

# ---------------------------------------------------------------- 断言 3
# 出处：SKILL.md 输入——三份输入只读（任务拆分不改写设计/验证/门禁成果物）。
for path, want in INPUT_SHA1.items():
    if not path.is_file():
        fail(f"输入文件缺失：{path.relative_to(WORKSPACE)}")
        continue
    got = hashlib.sha1(path.read_bytes()).hexdigest()
    if got != want:
        fail(f"输入被改写：{path.name}")

if text:
    # ------------------------------------------------------------ 断言 4
    # 出处：references/overview_template.md 固定骨架——元信息/执行规则/
    #       串行执行顺序/任务计划/存疑汇总/待处理用例登记/执行记录。
    SECTIONS = ["元信息", "执行规则", "串行执行顺序", "任务计划", "存疑汇总", "待处理用例登记", "执行记录"]
    missing = [s for s in SECTIONS if s not in text]
    if missing:
        fail(f"模板骨架章节缺失：{missing}")

    # ------------------------------------------------------------ 断言 5
    # 出处：overview_template.md 任务计划表——六列：编号|任务|做什么|
    #       改哪些文件|验证哪些用例|前置；SKILL.md 拆分原则 4——
    #       「拓扑排序为唯一串行序列；编号必须与执行顺序一致」。
    rows = re.findall(r"^\|\s*(T\d+)\s*\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|", text, re.M)
    notes.append(f"任务计划表行数={len(rows)} 编号={[r[0] for r in rows]}")
    if not rows:
        fail("任务计划表无 T 编号行（六列形态）")
    else:
        ids = [int(r[0][1:]) for r in rows]
        if ids != list(range(1, len(ids) + 1)):
            fail(f"任务编号不连续或顺序错乱：{ids}")
        thin = [r[0] for r in rows if len(r[2].strip()) < 8 or len(r[3].strip()) < 4]
        if thin:
            fail(f"任务行的「做什么/改哪些文件」列近乎为空：{thin}")

    # ------------------------------------------------------------ 断言 6
    # 出处：SKILL.md 拆分原则 7——「覆盖完整：每个需要实现的设计项至少由
    #       一个任务承接，每个测试用例有明确责任任务」。测试设计的 TC 全集
    #       由输入自身给出（断言必须有出处：出处=测试设计文件）。
    test_text = TEST.read_text(encoding="utf-8-sig") if TEST.is_file() else ""
    valid_tc = sorted(set(re.findall(r"\bTC\d+\b", test_text)), key=lambda s: int(s[2:]))
    referenced = set(re.findall(r"\bTC\d+\b", text))
    uncovered = [t for t in valid_tc if t not in referenced]
    notes.append(f"测试设计 TC 总数={len(valid_tc)} overview 引用={len(referenced)} 未覆盖={uncovered[:6]}")
    if uncovered:
        fail(f"测试用例未被任何任务承接（拆分原则 7 覆盖完整）：{uncovered[:8]}{'…' if len(uncovered) > 8 else ''}")

    # ------------------------------------------------------------ 断言 7
    # 出处：SKILL.md 拆分原则 8——「存疑不放行：无法确定任务边界或引用时，
    #       记录 Open Questions；未清零前不得确认计划」。正常交付的
    #       「存疑汇总」章节应为空或显式标「无」。
    m = re.search(r"##\s*存疑汇总[^\n]*\n(.*?)(?=\n##\s|\Z)", text, re.S)
    if m:
        body = m.group(1).strip()
        body_clean = re.sub(r"^\s*#.*$", "", body, flags=re.M).strip()
        if body_clean and "无" not in body_clean and re.search(r"待确认|待定|待澄清|[?？]", body_clean):
            fail(f"存疑汇总存在未决内容（未清零不得放行）：{body_clean[:100]}")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("TASKSPLIT-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("TASKSPLIT-ASSERT-PASS")
