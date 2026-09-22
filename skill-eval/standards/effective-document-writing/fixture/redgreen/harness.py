#!/usr/bin/env python3
"""assert_docwrite.py 红绿验证。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
ASSERT = ROOT.parent / "assert_docwrite.py"
DRAFT_SRC = ROOT.parent / "fixture" / "draft.md"

GREEN_DOC = """# SM2 用户认证设计说明

## 结论

在 rbs-core 新增 `authn/sm2` 模块承载 SM2/SM3 验签，Bearer 与 Attest 两条验签路径复用该模块。

## 依据

- SM2 无法复用 jsonwebtoken 的解码路径（未知 alg 直接失败），需独立分支。
- 两条验签路径共享同一密码学语义，集中实现避免双份漂移。

## 取舍

- 不改动 rbs-rest 中间件：透传不变，改动面收敛在 rbs-core。
- SM2 用户标识采用标准默认值；GTA 侧最终表示法待上游确认（待确认项）。

## 验证

- SM2 用户令牌验签通过；既有算法行为不变。
"""

CASE_LIST: list[dict] = [
    {"name": "green", "expect": 0, "doc": GREEN_DOC},
    {"name": "red-missing-file", "expect": 1, "doc": None, "want": "产物不存在"},
    {"name": "red-jargon", "expect": 1,
     "doc": GREEN_DOC.replace("## 结论", "## 结论\n\n本方案赋能认证体系，拉通两条链路。"),
     "want": "黑话"},
    {"name": "red-empty-claim", "expect": 1,
     "doc": GREEN_DOC + "\n本设计显著提升性能并全面保障安全。\n",
     "want": "空泛表态"},
    {"name": "red-conversation-trace", "expect": 1,
     "doc": GREEN_DOC + "\n根据你的要求，经过讨论得出以上结论。\n",
     "want": "对话/生成过程痕迹"},
    {"name": "red-no-conclusion", "expect": 1,
     "doc": "# 一些想法\n\n我们把认证相关的各种事情都看了一下，感觉可以做点什么。\n具体怎么做还没定，下次再说。这里先记一下大家的发言。\n" * 4,
     "want": "明确结论"},
    {"name": "red-too-short", "expect": 1,
     "doc": "# SM2\n\n做 authn/sm2。\n", "want": "要素不全"},
    {"name": "red-draft-mutated", "expect": 1, "doc": GREEN_DOC, "mutate_draft": True,
     "want": "原稿 draft.md 被改动"},
]


def run_case(case: dict) -> tuple[bool, str]:
    case_dir = CASES / case["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir)
    (case_dir / ".sdd").mkdir(parents=True)
    (case_dir / "docs").mkdir(parents=True)
    draft = case_dir / ".sdd" / "draft.md"
    shutil.copy2(DRAFT_SRC, draft)
    if case.get("mutate_draft"):
        draft.write_bytes("被改写\n".encode("utf-8"))
    if case["doc"] is not None:
        (case_dir / "docs" / "SM2-auth-design.md").write_bytes(case["doc"].encode("utf-8"))

    result = subprocess.run(
        [sys.executable, str(ASSERT)],
        cwd=case_dir, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60, check=False,
    )
    output = result.stdout + result.stderr
    ok = result.returncode == case["expect"]
    detail = ""
    if ok and case["expect"] == 1:
        want = case.get("want", "")
        ok = want in output
        detail = f"命中条款[{want}]" if ok else f"退出码正确但未命中条款[{want}]"
    elif ok:
        detail = "PASS"
    else:
        detail = f"期望退出码 {case['expect']} 实得 {result.returncode}"
    return ok, f"{detail} | out={output.strip()[-240:]}"


def main() -> int:
    mismatches = 0
    for case in CASE_LIST:
        ok, detail = run_case(case)
        mark = "OK " if ok else "BAD"
        print(f"[{mark}] {case['name']}: {detail}")
        if not ok:
            mismatches += 1
    print(f"\n共 {len(CASE_LIST)} 用例，不符预期 {mismatches} 个")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
