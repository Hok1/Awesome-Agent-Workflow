#!/usr/bin/env python3
"""module-tobe-design 黑盒断言：只读产物文件，不 import skill 任何源码。

断言对象：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md
本脚本必须在 workspace 之外执行（判据保密纪律）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WORKSPACE = Path.cwd()
ARTIFACT = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / "模块详细设计说明书.md"

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


# ---------------------------------------------------------------- 断言 1
# 出处：definitions/module-tobe-design.yaml —— output 契约 required；
#       SKILL.md 成果物协作规则——「文件名固定，不重复拼接 AR、需求短名或模块组名」。
if not ARTIFACT.is_file():
    fail(f"产物不存在：{ARTIFACT.relative_to(WORKSPACE)}（output 契约 required）")
    text = ""
else:
    text = ARTIFACT.read_text(encoding="utf-8-sig")
    notes.append(f"产物字符数={len(text)}")

if text:
    # ------------------------------------------------------------ 断言 2
    # 出处：SKILL.md §4.1——「正式说明书必须按 tobe-output-template.md 的
    #       9 个一级章节组织」。
    CHAPTERS = [
        (r"##\s*1[.、\s]", "需求背景"),
        (r"##\s*2[.、\s]", "外部依赖"),
        (r"##\s*3[.、\s]", "整体方案"),
        (r"##\s*4[.、\s]", "模块详细方案"),
        (r"##\s*5[.、\s]", "对外接口"),
        (r"##\s*6[.、\s]", "数据库"),
        (r"##\s*7[.、\s]", "受影响模块"),
        (r"##\s*8[.、\s]", "关键契约清单"),
        (r"##\s*9[.、\s]", "附录"),
    ]
    missing_chapters = []
    for pattern, keyword in CHAPTERS:
        head = re.search(pattern + r"[^\n]*", text)
        if not (head and keyword in head.group(0)):
            missing_chapters.append(f"{pattern[4:7]}..{keyword}")
    if missing_chapters:
        fail(f"9 章大纲不完整，缺或标题不含关键词：{missing_chapters}")

    # ------------------------------------------------------------ 断言 3
    # 出处：SKILL.md 成果物协作规则——正式说明书「不得写入 ASIS 检索过程、
    #       证据编号表、推导过程、反证记录、门禁采样、追踪矩阵等过程性内容」。
    #       判定的是正文中的证据编号引用/索引表；fenced 代码块（含 mermaid）
    #       里的 E401 类节点 ID 不是证据编号，先剥离再计数。
    if re.search(r"证据索引", text):
        fail("说明书含「证据索引」章节（过程性内容禁止进入正式说明书）")
    prose = re.sub(r"```.*?```", "", text, flags=re.S)
    e_refs = re.findall(r"\bE\d+\b", prose)
    if len(e_refs) > 3:
        fail(f"说明书正文暴露证据编号（E 形态 {len(e_refs)} 处 >3），证据编号表属过程性内容")
    for process_word in ("检索过程", "查证过程", "反证记录", "门禁采样", "追踪矩阵"):
        if process_word in text:
            fail(f"说明书含过程性内容字样「{process_word}」")

    # ------------------------------------------------------------ 断言 4
    # 出处：SKILL.md 成果物协作规则——「TOBE 中引用的 ASIS 事实必须在
    #       详细设计上下文中使用已有的 ASIS 结论编号和证据编号建立追踪」；
    #       references/tobe-context-template.md——C14「TOBE 推导依据」
    #       （输入依据=R/A/E 编号）与 C16「完整追踪矩阵」。
    #       判定对象是 context 的 TOBE 增量部分，不是说明书。
    ctx_path = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / ".context" / "详细设计上下文.md"
    if not ctx_path.is_file():
        fail("详细设计上下文缺失（TOBE 的追踪矩阵无处落地）")
    else:
        ctx = ctx_path.read_text(encoding="utf-8-sig")
        has_tobe_part = ("C14" in ctx or "C16" in ctx) and ("追踪矩阵" in ctx or "推导依据" in ctx)
        if not has_tobe_part:
            fail("context 缺少 TOBE 推导依据（C14）或完整追踪矩阵（C16）章节")
        split_at = ctx.find("C14") if "C14" in ctx else ctx.find("C16")
        asis_zone, tobe_zone = ctx[:split_at], ctx[split_at:]
        # 合法编号集合由 ASIS 输入自身给出（断言必须有出处：出处=ASIS 产物的实际编号域）
        valid_ids = set(int(m) for m in re.findall(r"\bA(\d+)\b", asis_zone))
        tobe_a_refs = sorted(set(int(m) for m in re.findall(r"\bA(\d+)\b", tobe_zone)))
        notes.append(f"context TOBE 区引用 ASIS 结论编号={tobe_a_refs} 合法域={len(valid_ids)}个")
        if len(tobe_a_refs) < 2:
            fail(f"TOBE 追踪未引用 ASIS 结论编号（C14/C16 区仅 {tobe_a_refs}），证据链未建立")
        beyond = [n for n in tobe_a_refs if n not in valid_ids]
        if beyond:
            fail(f"TOBE 追踪引用了 ASIS 输入中不存在的编号：{beyond}（凭空编号）")

    # ------------------------------------------------------------ 断言 5
    # 出处：SKILL.md 职责边界——TOBE 不负责「测试用例编号、测试矩阵、建议测试
    #       文件、测试命令、Fixture、Mock 或断言清单」「AICoding 任务编号、
    #       任务拆分、任务依赖、最小验证集或开发排期」。
    if re.search(r"\bTC-\d+\b", text):
        fail("说明书含测试用例编号（TC- 形态），测试用例设计不属 TOBE 职责")
    if re.search(r"\bTASK-\d+\b", text) or re.search(r"##.*任务拆分", text):
        fail("说明书含任务拆分内容，AICoding 任务拆分不属 TOBE 职责")

    # ------------------------------------------------------------ 断言 6
    # 出处：SKILL.md 职责边界——不负责「完整类或函数实现、可直接运行的业务逻辑、
    #       控制流和异常捕获、初始化或日志样板、完整迁移脚本，以及从现有代码
    #       复制的大段实现」。
    for m in re.finditer(r"```(?:rust|rs)\n(.*?)```", text, re.S):
        lines = m.group(1).strip().splitlines()
        if len(lines) >= 10:
            fail(f"说明书含 ≥10 行的 Rust 代码块（{len(lines)} 行），大段实现不属 TOBE 职责")

    # ------------------------------------------------------------ 断言 7
    # 出处：SKILL.md 成果物协作规则——「契约保真是硬要求：凡是……ASIS context
    #       ……中已经明确给出的接口定义、方法/函数签名、入参出参、DTO/VO/消息
    #       字段……必须在正式说明书中原样保留或结构化等价保留」。
    #       以下标识符由 ASIS（A2/A5/A8 等）查明，属真实现状契约。
    identifiers = ["SUPPORTED_ALGORITHMS", "auth_value", "validate_and_derive_alg", "BearerTokenVerifier"]
    found = [i for i in identifiers if i in text]
    notes.append(f"契约标识符命中={found}")
    if len(found) < 2:
        fail(f"说明书未承接 ASIS 已查明的现状契约标识符（仅命中 {found}），契约保真不足")

    # ------------------------------------------------------------ 断言 8
    # 出处：SKILL.md 输出模式——「至少保留 TOBE 状态」；阻塞规则——「标记 TOBE
    #       阻塞或部分完成」；tobe-output-template.md §3.1 决策表——
    #       「状态 / 待确认说明」列（取值 已定稿 / 需前置确认）。
    #       两种合法形态：行内状态字段，或决策表状态列（表头含「状态」且
    #       表体出现 已定稿/需前置确认）。
    status_inline = re.search(
        r"状态[^\n|：:]{0,8}[：:|]\s*\*{0,2}(完成|部分完成|阻塞|已定稿)", text
    )
    status_table = bool(
        re.search(r"状态[^|\n]*\|", text) and re.search(r"已定稿|需前置确认", text)
    )
    if not (status_inline or status_table):
        fail("说明书未给出状态表达（行内状态字段或决策表状态列，取值 完成/部分完成/阻塞/已定稿）")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("TOBE-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("TOBE-ASSERT-PASS")
