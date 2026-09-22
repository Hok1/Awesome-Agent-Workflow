#!/usr/bin/env python3
"""effective-document-writing 黑盒断言：只读产物文件，不 import skill 任何源码。

断言对象：docs/SM2-auth-design.md（由 draft.md 重写而来）。
本脚本必须在 workspace 之外执行（判据保密纪律）。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE = Path.cwd()
ARTIFACT = WORKSPACE / "docs" / "SM2-auth-design.md"
DRAFT = WORKSPACE / ".sdd" / "draft.md"

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


# ---------------------------------------------------------------- 断言 1
# 出处：任务契约——重写到 docs/SM2-auth-design.md。
if not ARTIFACT.is_file():
    fail(f"产物不存在：{ARTIFACT.relative_to(WORKSPACE)}（任务契约）")
    text = ""
else:
    text = ARTIFACT.read_text(encoding="utf-8-sig")
    notes.append(f"产物字符数={len(text)}")

# 原稿不得被修改（重写是新文件，原稿是输入）
if DRAFT.is_file():
    draft = DRAFT.read_text(encoding="utf-8-sig")
    if "对齐了一下颗粒度" not in draft:
        fail("原稿 draft.md 被改动（重写任务不得改输入）")

if text:
    # ------------------------------------------------------------ 断言 2
    # 出处：SKILL.md 控制语言和信息密度——「不使用『赋能、抓手、闭环、拉通、
    #       沉淀、对齐颗粒度』等词替代可直接说明的动作、对象和结果」。
    #       只断言无歧义词（闭环/沉淀在验证语境有精确定义，豁免）。
    jargon = [w for w in ("赋能", "抓手", "拉通", "对齐颗粒度", "颗粒度") if w in text]
    if jargon:
        fail(f"产物含黑话词汇：{jargon}")

    # ------------------------------------------------------------ 断言 3
    # 出处：SKILL.md 同上——「避免『显著提升、全面保障、充分考虑、持续优化』
    #       等没有对象、条件或验证方式的表态」。
    empty = [w for w in ("显著提升", "全面保障", "充分考虑", "持续优化") if w in text]
    if empty:
        fail(f"产物含空泛表态：{empty}")

    # ------------------------------------------------------------ 断言 4
    # 出处：SKILL.md 隔离对话和修改过程——排除「根据你的要求」「如前所述」
    #       「经过讨论」与生成过程痕迹（Agent/轮次/提示词）。
    traces = [w for w in ("根据你的要求", "如前所述", "经过讨论", "提示词", "生成轮次", "聊天记录")
              if w in text]
    if traces:
        fail(f"产物混入对话/生成过程痕迹：{traces}")

    # ------------------------------------------------------------ 断言 5
    # 出处：SKILL.md 确定写作任务——「设计文档写结论、依据和取舍」。
    #       按语义判定而非钉词：方案结论在场 + 支撑/边界类小节在场 +
    #       诚实标记（待确认/不做/不包含）。
    if "authn" not in text and "sm2" not in text.lower():
        fail("产物未把原稿的方案要点（SM2 模块）落成明确结论")
    has_conclusion = ("结论" in text) or ("目标" in text)
    has_support = any(w in text for w in ("依据", "取舍", "原因", "边界", "范围", "影响", "限制"))
    has_honesty = any(w in text for w in ("待确认", "不做", "不包含", "不覆盖"))
    missing = []
    if not has_conclusion:
        missing.append("方案结论")
    if not has_support:
        missing.append("支撑理由/边界")
    if not has_honesty:
        missing.append("诚实标记（待确认/不覆盖）")
    if missing:
        fail(f"设计文档要素不全：缺 {missing}")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("DOCWRITE-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("DOCWRITE-ASSERT-PASS")
