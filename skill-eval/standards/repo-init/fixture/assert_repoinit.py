#!/usr/bin/env python3
"""repo-init 黑盒断言：只读产物文件与 workspace，不 import skill 任何源码。

断言对象：.sdd/software_architecture.md 与 AGENTS.md（RBS workspace）。
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
ARCH = WORKSPACE / ".sdd" / "software_architecture.md"
AGENTS = WORKSPACE / "AGENTS.md"

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


# ---------------------------------------------------------------- 断言 1
# 出处：SKILL.md Phase 4——写 .sdd/software_architecture.md；
#       下游 module-asis-analysis 以它为唯一模块边界来源。
if not ARCH.is_file():
    fail(".sdd/software_architecture.md 不存在（下游模块边界来源缺失）")
    text = ""
else:
    text = ARCH.read_text(encoding="utf-8-sig")
    notes.append(f"架构文档字符数={len(text)}")

if text:
    # ------------------------------------------------------------ 断言 2
    # 出处：SKILL.md Phase 4——「Fill in all placeholders '{{***}}'，
    #       IMPORTANT: do NOT modify or fill in any placeholders in
    #       'section 1.2' and 'section 1.3' and 目录」。
    #       即：豁免区（目录 / 1.2 / 1.3）之外的 {{}} 必须清零。
    def section_range(start_pat: str, end_pat: str) -> tuple[int, int]:
        s = re.search(start_pat, text, re.M)
        e = re.search(end_pat, text, re.M)
        return (s.start() if s else len(text)), (e.start() if e else len(text))

    toc = section_range(r"^#\s*目录", r"^##\s*1\s")          # 目录
    s12 = section_range(r"^###\s*1\.2", r"^###\s*1\.3")      # 1.2
    s13 = section_range(r"^###\s*1\.3", r"^##\s*2\s")        # 1.3
    exempt = sorted([toc, s12, s13])
    residual = []
    for m in re.finditer(r"\{\{", text):
        pos = m.start()
        if not any(a <= pos < b for a, b in exempt):
            residual.append(pos)
    notes.append(f"豁免区外残留占位符={len(residual)}")
    if residual:
        line_no = text[: residual[0]].count("\n") + 1
        fail(f"豁免区（目录/1.2/1.3）之外残留 {{{{ 占位符 {len(residual)} 处，首处在第 {line_no} 行")

    # ------------------------------------------------------------ 断言 3
    # 出处：模板「## 2 模块清单 / 2.1 模块职责表」含「当前代码仓下相对路径」列；
    #       SKILL.md——架构文档是下游唯一边界来源，模块路径必须真实。
    real_modules = ["rbs/core", "rbs/rest", "tools", "rbc", "rbs/api-types"]
    mentioned = [m for m in real_modules if m in text]
    notes.append(f"真实模块路径命中={mentioned}")
    if len(mentioned) < 2:
        fail(f"模块清单未落到真实代码路径（命中 {mentioned}，<2）")
    # 防伪：产物中以真实模块根开头并深入到 src/tests/文件 的引用必须存在；
    # 「crate 名/职责域」（如 rbs-core/auth）是模块关系写法，不当作文件路径。
    claimed = sorted(set(re.findall(r"\b(?:rbs(?:-[\w]+)?|rbc|tools)(?:/[\w.\-]+)+", text)))
    checkable = [
        p for p in claimed
        if re.search(r"\.(rs|toml|md)$", p)
        or re.match(r"^(rbs/(core|rest|api-types)|rbc|tools)(/src\b|/tests\b|$)", p)
    ]
    phantom = [p for p in checkable if not (WORKSPACE / p).exists()]
    if phantom:
        fail(f"产物引用的路径在 workspace 不存在：{phantom[:6]}")

    # ------------------------------------------------------------ 断言 4
    # 出处：模板固定结构——文档元数据 / 目录 / 系统概览 / 模块清单。
    for sec in ("目录", "系统概览", "模块清单"):
        if sec not in text:
            fail(f"模板固定章节缺失：{sec}")

# ---------------------------------------------------------------- 断言 5
# 出处：SKILL.md Phase 5——写 AGENTS.md，Detect「Build, test, and lint
#       commands」「Languages, frameworks, and package manager」。
if not AGENTS.is_file():
    fail("AGENTS.md 不存在（Phase 5 产物缺失）")
else:
    agents = AGENTS.read_text(encoding="utf-8-sig", errors="replace")
    if "cargo" not in agents.lower():
        fail("AGENTS.md 未提及 cargo（Rust 仓的构建/测试命令未发现）")
    if "rust" not in agents.lower():
        fail("AGENTS.md 未识别 Rust 语言")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("REPOINIT-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("REPOINIT-ASSERT-PASS")
