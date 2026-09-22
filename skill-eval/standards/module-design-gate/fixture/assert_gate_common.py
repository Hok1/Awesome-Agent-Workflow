#!/usr/bin/env python3
"""module-design-gate 正向黑盒断言（形式合规，不钉结论值）。

断言对象：.sdd/SR-1/AR-1/rbs-core/.context/模块设计门禁结果.md
约束对象：三份输入（说明书/测试设计/context）sha1 钉死，不得被改写。
本脚本必须在 workspace 之外执行（判据保密纪律）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

# grader 环境 stdout 可能是 GBK；统一 UTF-8 防 UnicodeEncodeError 掩盖真实判据
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE = Path.cwd()
RESULT = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / ".context" / "模块设计门禁结果.md"
SPEC = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / "模块详细设计说明书.md"
TEST = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / "模块测试用例设计.md"
CTX = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / ".context" / "详细设计上下文.md"

# 正向用例（干净三件套）的钉版 sha1；反向用例由环境变量覆盖为 defect 夹具的 sha1。
INPUT_SHA1 = {
    SPEC: os.environ.get("MDG_SPEC_SHA1", "f409b788cb6872e8d0bdcd532cc6f74ee5140729"),
    TEST: os.environ.get("MDG_TEST_SHA1", "fbd4353d8b24a891738123639c730e3524ba2b4a"),
    CTX: os.environ.get("MDG_CTX_SHA1", "36577b460f1b4c23c55b5cce0915c369922199a9"),
}

CONCLUSIONS = ("通过", "不通过", "阻塞")
ADVICES = (
    "可进入 AICoding",
    "回 ASIS 补证据后重试",
    "回 TOBE 补设计后重试",
    "回测试设计补用例后重试",
    "先做上游/用户确认",
    "拆分范围后有限进入 AICoding",
    "阻塞，缺少必要输入",
)

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


# ---------------------------------------------------------------- 断言 1
# 出处：definitions/module-design-gate.yaml —— output required；
#       SKILL.md 成果物协作规则——编排调用时必须写入该路径。
if not RESULT.is_file():
    fail(f"门禁结果不存在：{RESULT.relative_to(WORKSPACE)}（output 契约 required）")
    text = ""
else:
    text = RESULT.read_text(encoding="utf-8-sig")
    notes.append(f"结果字符数={len(text)}")

# ---------------------------------------------------------------- 断言 2
# 出处：SKILL.md 成果物协作规则——「本 skill 不得创建、编辑或覆盖正式说明书
#       中的任何章节」「不得创建、编辑或覆盖测试设计成果物中的任何章节」、
#       「不得直接覆盖其正文」（context）。
for path, want in INPUT_SHA1.items():
    if not path.is_file():
        fail(f"输入文件缺失：{path.relative_to(WORKSPACE)}")
        continue
    got = hashlib.sha1(path.read_bytes()).hexdigest()
    if got != want:
        fail(f"门禁改写了输入文件 {path.name}（sha1 变动）")

if text:
    # ------------------------------------------------------------ 断言 3
    # 出处：SKILL.md 门禁结论——「结论只能是：通过 / 不通过 / 阻塞」。
    #       形态容差：行内（结论：通过）或表格行（| 门禁状态 | 通过 |）。
    #       交替顺序「不通过」在前，避免「不通过」被截成「通过」。
    m = re.search(
        r"(?:门禁状态|门禁结论|结论)[^\n|：:]{0,6}[：:|]\s*\*{0,2}(不通过|通过|阻塞)",
        text,
    )
    conclusion = m.group(1) if m else None
    notes.append(f"结论={conclusion}")
    if conclusion is None:
        fail("门禁结论缺失或不在 {通过/不通过/阻塞} 枚举内（接受行内或表格形态）")

    # ------------------------------------------------------------ 断言 4
    # 出处：SKILL.md 门禁结论——「门禁还必须给出明确的门禁建议」，
    #       建议为七值枚举。
    advice_hits = [a for a in ADVICES if a in text]
    notes.append(f"建议命中={advice_hits}")
    if not advice_hits:
        fail("门禁建议缺失或不在七值枚举内")

    # ------------------------------------------------------------ 断言 5
    # 出处：SKILL.md 门禁结论——「除受限场景外，只要存在任一适用维度未达标，
    #       门禁结论不得为 通过」；「通过：所有适用维度均达标，阻断问题为 0，
    #       可进入 AICoding」。
    if conclusion == "通过" and advice_hits and "可进入 AICoding" not in advice_hits:
        fail(f"结论为通过但建议不含「可进入 AICoding」（{advice_hits}），结论与建议不一致")
    if conclusion == "不通过" and advice_hits == ["可进入 AICoding"]:
        fail("结论为不通过但建议为「可进入 AICoding」，自相矛盾")

    # ------------------------------------------------------------ 断言 6
    # 出处：SKILL.md 成果物协作规则——「门禁引用的需求/AR 编号、TOBE 决策编号
    #       和契约编号必须来自正式说明书；覆盖目标、测试用例和测试缺口编号必须
    #       来自独立测试设计；ASIS 证据编号必须能在详细设计上下文的证据索引中反查」。
    spec_text = SPEC.read_text(encoding="utf-8-sig") if SPEC.is_file() else ""
    test_text = TEST.read_text(encoding="utf-8-sig") if TEST.is_file() else ""
    ctx_text = CTX.read_text(encoding="utf-8-sig") if CTX.is_file() else ""
    valid_d = set(re.findall(r"\bD\d+\b", spec_text))
    valid_tc = set(re.findall(r"\bTC\d+\b", test_text))
    valid_a = set(re.findall(r"\bA\d+\b", ctx_text))
    valid_e = set(re.findall(r"\bE\d+\b", ctx_text))
    notes.append(f"可反查域 D={len(valid_d)} TC={len(valid_tc)} A={len(valid_a)} E={len(valid_e)}")

    ref_d = set(re.findall(r"\bD\d+\b", text))
    ref_tc = set(re.findall(r"\bTC\d+\b", text))
    ref_a = set(re.findall(r"\bA\d+\b", text))
    ref_e = set(re.findall(r"\bE\d+\b", text))
    bad_d = sorted(ref_d - valid_d)
    bad_tc = sorted(ref_tc - valid_tc)
    bad_a = sorted(ref_a - valid_a)
    bad_e = sorted(ref_e - valid_e)
    if bad_d:
        fail(f"门禁引用了说明书中不存在的决策编号：{bad_d}")
    if bad_tc:
        fail(f"门禁引用了测试设计中不存在的用例编号：{bad_tc}")
    if bad_a:
        fail(f"门禁引用了 context 中不存在的 ASIS 结论编号：{bad_a}")
    if bad_e:
        fail(f"门禁引用了 context 中不存在的证据编号：{bad_e}")

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("MDG-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("MDG-ASSERT-PASS")
