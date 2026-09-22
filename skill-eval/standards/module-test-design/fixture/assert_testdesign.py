#!/usr/bin/env python3
"""module-test-design 黑盒断言：只读产物文件与 workspace，不 import skill 任何源码。

断言对象：.sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md
约束对象：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md（不得被改写，sha1 钉死）
本脚本必须在 workspace 之外执行（判据保密纪律）。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

WORKSPACE = Path.cwd()
ARTIFACT = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / "模块测试用例设计.md"
SPEC = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / "模块详细设计说明书.md"
SPEC_SHA1 = "f409b788cb6872e8d0bdcd532cc6f74ee5140729"  # 夹具钉版

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


# ---------------------------------------------------------------- 断言 0
# 出处：SKILL.md 成果物协作规则——「测试设计是独立成果物……
#       不得把测试用例写回 TOBE 正式说明书」。
if SPEC.is_file():
    got = hashlib.sha1(SPEC.read_bytes()).hexdigest()
    if got != SPEC_SHA1:
        fail("TOBE 正式说明书被改写（测试设计不得回写说明书）")
else:
    fail("TOBE 正式说明书缺失（输入夹具应就位）")

# ---------------------------------------------------------------- 断言 1
# 出处：definitions/module-test-design.yaml —— output 契约 required。
if not ARTIFACT.is_file():
    fail(f"产物不存在：{ARTIFACT.relative_to(WORKSPACE)}（output 契约 required）")
    text = ""
else:
    text = ARTIFACT.read_text(encoding="utf-8-sig")
    notes.append(f"产物字符数={len(text)}")

if text:
    # ------------------------------------------------------------ 断言 2
    # 出处：SKILL.md §4——「每个用例一个条目（##### TCn）」。
    tc_heads = re.findall(r"^#{5}\s*TC\d+", text, re.M)
    notes.append(f"TC 用例条目数={len(tc_heads)}")
    if len(tc_heads) < 3:
        fail(f"用例条目（##### TCn 形态）不足：{len(tc_heads)} 条，未形成最小验证集")

    # ------------------------------------------------------------ 断言 3
    # 出处：SKILL.md §4——「用例正文不得使用任何表格」。
    tc_blocks = re.split(r"^#{5}\s*TC\d+[^\n]*$", text, flags=re.M)[1:]
    table_in_tc = 0
    for block in tc_blocks:
        body = re.split(r"^#{1,5}\s", block, maxsplit=1, flags=re.M)[0]
        if re.search(r"^\s*\|.*\|", body, re.M):
            table_in_tc += 1
    if table_in_tc:
        fail(f"{table_in_tc} 条用例正文含表格（§4 明文：用例正文不得使用任何表格）")

    # ------------------------------------------------------------ 断言 4
    # 出处：SKILL.md §3——每条用例至少包含「前置数据/Fixture/依赖状态」
    #       「输入或触发步骤」「预期结果、断言对象和精确判定条件」；
    #       §4——「四个行为字段「前置 / 输入 / 预期 / 断言」」。
    FIELDS = ("前置", "输入", "预期", "断言")
    incomplete = []
    for index, block in enumerate(tc_blocks, 1):
        body = re.split(r"^#{1,5}\s", block, maxsplit=1, flags=re.M)[0]
        missing = [f for f in FIELDS if f not in body]
        if missing:
            incomplete.append((index, missing))
    if incomplete:
        fail(f"{len(incomplete)} 条用例缺行为字段（前置/输入/预期/断言）：{incomplete[:3]}")

    # ------------------------------------------------------------ 断言 5
    # 出处：SKILL.md §4——覆盖矩阵「TOBE 决策/契约/风险 -> 优先级 ->
    #       覆盖用例 -> 覆盖状态 -> 未覆盖原因」。
    #       按标题形态定位章节（正文提及"覆盖矩阵"四字不算）。
    matrix = re.search(
        r"^#{2,4}\s*[\d.、\s]*覆盖矩阵[^\n]*\n(.*?)(?=\n#{1,4}\s|\Z)",
        text, re.S | re.M,
    )
    if not matrix:
        fail("缺少覆盖矩阵章节")
    else:
        mtext = matrix.group(1)
        if not re.search(r"^\s*\|.*\|", mtext, re.M):
            fail("覆盖矩阵章节无表格")
        elif not re.search(r"\bTC\d+\b", mtext):
            fail("覆盖矩阵未引用 TC 用例编号")
        elif not re.search(r"\bD\d+\b", mtext):
            fail("覆盖矩阵未关联 TOBE 决策编号（D 形态）")

    # ------------------------------------------------------------ 断言 6
    # 出处：SKILL.md 质量标准——「断言条件精确但保持语言无关，没有输出
    #       可直接粘贴的断言代码、循环、fixture 或 mock 实现」。
    code_in_tc = 0
    for block in tc_blocks:
        body = re.split(r"^#{1,5}\s", block, maxsplit=1, flags=re.M)[0]
        if re.search(r"```(?:rust|rs|python|java|go|ts)?\n(?:assert|ASSERT|#\[test\]|def test_|@Test)", body):
            code_in_tc += 1
    if code_in_tc:
        fail(f"{code_in_tc} 条用例含可直接粘贴的断言/测试代码（应保持语言无关）")

    # ------------------------------------------------------------ 断言 7
    # 出处：SKILL.md §4——「用例总览：在用例正文之前提供按验证场景分组的
    #       树状概览」；「测试范围与策略摘要：说明采用最小充分验证集」。
    if not re.search(r"用例总览|总览|概览", text):
        fail("缺少用例总览（树状概览供评审者快速判断覆盖）")
    if not re.search(r"最小充分", text):
        fail("未声明最小充分验证集策略（§4 必答项）")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("TESTDESIGN-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("TESTDESIGN-ASSERT-PASS")
