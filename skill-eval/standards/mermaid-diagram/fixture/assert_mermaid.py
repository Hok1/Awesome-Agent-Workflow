#!/usr/bin/env python3
"""mermaid-diagram 黑盒断言：只读产物文件，不 import skill 任何源码。

断言对象：被测 skill 在 workspace 中产出的 Markdown 文档。
驱动手段：直接调用 skill 自带的离线校验器 scripts/check_mermaid.py 与 node。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path.cwd()
SKILL_DIR = Path(
    os.environ.get("MM_SKILL_DIR") or WORKSPACE / ".aaw-eval" / "skills" / "mermaid-diagram"
)
CHECKER = SKILL_DIR / "scripts" / "check_mermaid.py"
ARTIFACT = WORKSPACE / "docs" / "SM2-密钥生命周期-图.md"

FENCE_START = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*mermaid(?:[ \t].*)?$", re.IGNORECASE)

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


def read_artifact() -> str:
    if not ARTIFACT.is_file():
        fail(f"产物文件不存在：{ARTIFACT.relative_to(WORKSPACE)}")
        return ""
    return ARTIFACT.read_text(encoding="utf-8-sig")


def extract_blocks(text: str) -> list[tuple[int, str]]:
    """返回 [(起始行号, mermaid 源码)]。"""
    blocks: list[tuple[int, str]] = []
    opener: tuple[str, int, int] | None = None
    content: list[str] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if opener is None:
            match = FENCE_START.match(line)
            if match:
                fence = match.group(1)
                opener = (fence[0], len(fence), line_number)
                content = []
            continue
        marker, width, start_line = opener
        if re.match(rf"^[ \t]*{re.escape(marker)}{{{width},}}[ \t]*$", line):
            blocks.append((start_line, "\n".join(content).strip()))
            opener = None
            content = []
        else:
            content.append(line)
    return blocks


def run_checker() -> tuple[int, str, str]:
    if not CHECKER.is_file():
        fail(f"skill 自带校验器缺失：{CHECKER}")
        return 2, "", "checker missing"
    result = subprocess.run(
        [sys.executable, str(CHECKER), str(ARTIFACT)],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------- 断言 1
# 出处：SKILL.md「## 编译验证」——交付前运行 scripts/check_mermaid.py，
#       任一图无法编译时返回非零退出码；必须完全离线。
text = read_artifact()
if text:
    blocks = extract_blocks(text)
    notes.append(f"mermaid 代码块数={len(blocks)}")
    if not blocks:
        fail("文档里没有任何 ```mermaid 代码块")
    else:
        code, stdout, stderr = run_checker()
        notes.append(f"check_mermaid.py exit={code}")
        notes.append(stdout.strip().splitlines()[-1] if stdout.strip() else "")
        if code != 0:
            fail(
                "离线校验器未通过（图不能编译）\n"
                f"  exit={code}\n  stdout={stdout.strip()[-1500:]}\n  stderr={stderr.strip()[-1500:]}"
            )

    # ------------------------------------------------------------ 断言 2
    # 出处：SKILL.md「## 选择图型」——生命周期/合法状态转换用 stateDiagram-v2，
    #       多参与者时序用 sequenceDiagram。图型与评审问题必须匹配。
    bodies = "\n".join(body for _, body in blocks)
    heads = [
        body.split("\n", 1)[0].strip().lower()
        for _, body in blocks
        if body.strip()
    ]
    kinds = [head.split()[0].rstrip(":") if head.split() else "" for head in heads]
    notes.append("图型=" + ",".join(kinds) if kinds else "图型=无")

    state_like = [k for k in kinds if k.startswith("statediagram")]
    if not state_like:
        fail("缺少 stateDiagram-v2：密钥生命周期（生成/启用/轮换/吊销/泄露/销毁）是状态转换问题")
    else:
        # 状态图必须真的画出合法转换，不能只有状态名
        for _, body in blocks:
            if body.split("\n", 1)[0].strip().lower().startswith("statediagram"):
                transitions = len(re.findall(r"-->", body))
                states = len(re.findall(r"^\s*[A-Za-z_一-鿿][\w一-鿿]*\s*:", body, re.M))
                notes.append(f"stateDiagram 转换数={transitions} 状态声明数={states}")
                if transitions < 4:
                    fail(f"stateDiagram-v2 只有 {transitions} 条转换，少于生命周期所需的 4 条")
                if states < 5:
                    fail(f"stateDiagram-v2 只声明了 {states} 个状态，覆盖不到密钥生命周期")

    # ------------------------------------------------------------ 断言 3
    # 出处：SKILL.md「编写规则 3」——主路径必须可走通；被设计触发的关键失败、
    #       回退或终止路径不能悬空。吊销与泄露必须可达终态。
    keywords_required = ["生成", "轮换", "吊销", "销毁"]
    missing = [word for word in keywords_required if word not in bodies]
    if missing:
        fail(f"生命周期图缺少关键节点：{missing}")
    if "泄露" not in bodies:
        fail("生命周期图缺少「泄露」这条安全路径（安全路径 fail-closed 是设计约束）")

    # ------------------------------------------------------------ 断言 4
    # 出处：SKILL.md「编写规则 2」——节点使用稳定的业务/模块/职责名称，
    #       避免为画图发明私有类、函数和文件。禁止出现代码标识符形态。
    invented = sorted(
        {
            name
            for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*\(\)", bodies)
        }
    )
    if invented:
        fail(f"图中出现函数调用形态的私有标识符（应为业务/职责名）：{invented}")

    # ------------------------------------------------------------ 断言 5
    # 出处：SKILL.md「## 选择图型」——sequenceDiagram 用于多个参与者之间
    #       有时间顺序的调用、消息和响应；「同一张图只回答一个主要问题」。
    #       本需求的密钥轮换涉及 客户端/签名服务/密钥存储 三方时序，必须有一张。
    sequence_count = len([k for k in kinds if k.startswith("sequencediagram")])
    notes.append(f"sequenceDiagram 数={sequence_count}")
    if sequence_count == 0:
        fail("缺少 sequenceDiagram：密钥轮换是多方按时序交互，不是单方状态变化")
    elif sequence_count > 2:
        fail(f"sequenceDiagram 出现 {sequence_count} 张，存在重复表达同一关系之嫌")

    # ------------------------------------------------------------ 断言 6
    # 出处：SKILL.md「## 选择图型」——「同一张图只回答一个主要问题。
    #       不要用多张图重复表达同一关系；只有不同图型回答不同评审问题时才同时保留。」
    #       反向断言：不得画出无法编译的伪图，也不得把无关图型塞进来凑数。
    allowed = ("flowchart", "graph", "sequencediagram", "statediagram", "classdiagram", "erdiagram")
    stray = [k for k in kinds if k and not k.startswith(allowed)]
    if stray:
        fail(f"出现与评审问题无关或自造的图型：{stray}")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("GATE-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("MERMAID-ASSERT-PASS")
