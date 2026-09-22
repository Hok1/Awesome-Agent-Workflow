#!/usr/bin/env python3
"""module-asis-analysis 正向黑盒断言：只读产物文件与 workspace，不 import skill 任何源码。

断言对象：.sdd/SR-1/<AR>/<模块组>/.context/详细设计上下文.md
驱动手段：文件系统读取 + 路径真实性核验（产物提到的代码路径必须在 workspace 存在）。
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


# ---------------------------------------------------------------- 断言 1
# 出处：definitions/module-asis-analysis.yaml —— output 契约
#       .sdd/{SR}/{AR}/{模块组名}/.context/详细设计上下文.md 为 required。
candidates = sorted(WORKSPACE.glob(".sdd/SR-1/*/*/.context/详细设计上下文.md"))
notes.append(f"context 产物候选={len(candidates)}")
if not candidates:
    fail("未找到 .sdd/SR-1/<AR>/<模块组>/.context/详细设计上下文.md（output 契约 required）")
    text = ""
    artifact = None
else:
    artifact = candidates[0]
    if len(candidates) > 1:
        notes.append(f"存在多份产物，取第一份：{artifact}")
    text = artifact.read_text(encoding="utf-8-sig")

if text:
    # ------------------------------------------------------------ 断言 2
    # 出处：SKILL.md 阶段 1——「加载 asis-output-template.md，把包含 C1–C8
    #       全部固定目录的骨架写入文件；保留所有标题」；质量标准——
    #       「无内容、未完成或不适用的章节保留标题并写明原因」。
    SECTIONS = [
        ("C1", "ASIS 状态"),
        ("C2", "模块边界"),
        ("C3", "关键 ASIS 事实"),
        ("C4", "调用链"),
        ("C5", "配置、数据、测试"),
        ("C6", "规格漂移"),
        ("C7", "证据索引"),
        ("C8", "追溯矩阵"),
    ]
    missing_sections = [
        f"{tag}.{kw}" for tag, kw in SECTIONS if not (tag in text and kw in text)
    ]
    if missing_sections:
        fail(f"固定目录骨架不完整，缺：{missing_sections}")

    # ------------------------------------------------------------ 断言 3
    # 出处：SKILL.md 模块边界规则——边界来源必须显式标记为
    #       「declared by software_architecture.md」或「blocked」；
    #       本用例架构文档已就位，应为前者。
    #       措辞容差：产物可用表格形态表达（来源列=software_architecture.md，
    #       类型列=declared）——判定 C2 章节内 declared 与该文件名共现。
    c2_match = re.search(r"##\s*C2[^\n]*\n(.*?)(?=\n##\s*C3|\Z)", text, re.S)
    c2_body = c2_match.group(1) if c2_match else ""
    has_declared = "declared by software_architecture.md" in text or (
        "declared" in c2_body.lower() and "software_architecture.md" in c2_body
    )
    if not has_declared:
        fail("C2 未把边界来源标记为 declared（+software_architecture.md），模块边界规则的合法来源标记缺失")

    # ------------------------------------------------------------ 断言 4
    # 出处：SKILL.md 阶段 5——「生成稳定 ASIS 结论编号，例如 A1、A2」；
    #       阶段 6——「证据编号，例如 E1、E2」；质量标准——「重要结论有证据」。
    conclusions = sorted(set(re.findall(r"\bA\d+\b", text)))
    evidences = sorted(set(re.findall(r"\bE\d+\b", text)))
    notes.append(f"结论编号={conclusions[:8]} 证据编号数={len(evidences)}")
    if len(conclusions) < 2:
        fail(f"稳定 ASIS 结论编号不足（{conclusions}），阶段 5 要求 A1、A2 形态")
    if len(evidences) < 3:
        fail(f"证据编号不足（{len(evidences)} 条），阶段 6 要求证据编号可追溯")

    # ------------------------------------------------------------ 断言 5
    # 出处：SKILL.md 输入——「如果代码仓可访问，必须直接检查代码」；
    #       质量标准——「重要结论有证据」。防伪证：产物提到的代码路径必须真实存在。
    path_tokens = sorted(
        set(
            re.findall(
                r"(?:rbs(?:-core|-rest|-api-types)?|rbc|tools)/[A-Za-z0-9_/.\-]+\.(?:rs|toml)",
                text,
            )
        )
    )
    notes.append(f"产物引用代码路径数={len(path_tokens)}")
    if len(path_tokens) < 3:
        fail(f"产物仅引用 {len(path_tokens)} 条代码路径，证据链未锚定真实代码")
    phantom = [p for p in path_tokens[:10] if not (WORKSPACE / p).exists()]
    if phantom:
        fail(f"产物引用了 workspace 中不存在的代码路径（伪造证据之嫌）：{phantom}")

    # ------------------------------------------------------------ 断言 6
    # 出处：SKILL.md 目标——「模块详细设计说明书.md：ASIS 阶段不得写入」；
    #       成果物协作规则——「本 skill 不得创建、编辑或覆盖正式说明书中的任何章节」。
    formal = sorted(WORKSPACE.glob(".sdd/**/模块详细设计说明书.md"))
    if formal:
        fail(f"ASIS 阶段创建了正式说明书（职责边界禁止）：{[str(p) for p in formal]}")

    # ------------------------------------------------------------ 断言 7
    # 出处：SKILL.md 职责边界——「把『建议采用』『可以复用』『应新增』写成
    #       ASIS 结论」违规；实现方案选择只能记录为「TOBE 决策输入」。
    c3_match = re.search(r"C3[^\n]*\n(.*?)(?=\n##\s*C4|\Z)", text, re.S)
    c3_body = c3_match.group(1) if c3_match else ""
    tobe_phrases = [p for p in ("建议采用", "可以复用", "应新增") if p in c3_body]
    if tobe_phrases:
        fail(f"C3 出现 TOBE 拍板短语（ASIS 不得给实现方案结论）：{tobe_phrases}")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("ASIS-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("ASIS-ASSERT-PASS")
