#!/usr/bin/env python3
"""assert_tasksplit.py 红绿验证。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
FIX = ROOT.parent / "fixture"
ASSERT = ROOT.parent / "assert_tasksplit.py"

BASE = Path(".sdd/SR-1/AR-1/rbs-core")
DOC_REL = BASE / "tasks-overview.md"

# 测试设计里真实的 TC 域是 TC1-TC27；红绿用迷你夹具，
# 其测试设计只含 TC1-TC3（断言 6 的合法域由输入自身给出）。
MINI_TEST = """# 迷你测试设计

##### TC1

- 断言：x

##### TC2

- 断言：y

##### TC3

- 断言：z
"""

GREEN_DOC = """# rbs-core 任务计划

## 元信息

- 来源详细设计文档：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md
- 来源测试用例设计文档：.sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md

## 执行规则

详细设计文档是实现设计的唯一事实来源。

## 串行执行顺序

T1 → T2

## 任务计划

| 编号 | 任务 | 做什么 | 改哪些文件 | 验证哪些用例 | 前置 |
|---|---|---|---|---|---|
| T1 | SM2 验签子模块 | 新增 authn/sm2 验签原语并接入分派 | rbs/core/src/auth/authn/sm2.rs | TC1、TC2 | 无 |
| T2 | 公钥登记扩展 | admin/key 增加 SM2 曲线识别 | rbs/core/src/admin/key.rs | TC3 | T1 |

## 存疑汇总

无。

## 待处理用例登记

无。

## 执行记录

（由 task-dev 更新）
"""

CASE_LIST: list[dict] = [
    {"name": "green", "expect": 0, "doc": GREEN_DOC},
    {"name": "red-missing-file", "expect": 1, "doc": None, "want": "产物不存在"},
    {"name": "red-task-files", "expect": 1, "doc": GREEN_DOC,
     "extra": {".sdd/SR-1/AR-1/rbs-core/T1-sm2.md": "# T1\n"}, "want": "独立任务文件"},
    {"name": "red-spec-mutated", "expect": 1, "doc": GREEN_DOC,
     "mutate": "spec", "want": "输入被改写"},
    {"name": "red-missing-section", "expect": 1,
     "doc": GREEN_DOC.replace("## 存疑汇总", "## 疑问"), "want": "骨架章节缺失"},
    {"name": "red-no-task-rows", "expect": 1,
     "doc": GREEN_DOC.replace("| T1 | SM2 验签子模块 | 新增 authn/sm2 验签原语并接入分派 | rbs/core/src/auth/authn/sm2.rs | TC1、TC2 | 无 |\n", "").replace("| T2 | 公钥登记扩展 | admin/key 增加 SM2 曲线识别 | rbs/core/src/admin/key.rs | TC3 | T1 |\n", ""),
     "want": "任务计划表无 T 编号行"},
    {"name": "red-nonsequential-ids", "expect": 1,
     "doc": GREEN_DOC.replace("| T2 | 公钥登记扩展", "| T3 | 公钥登记扩展"),
     "want": "编号不连续"},
    {"name": "red-uncovered-tc", "expect": 1,
     "doc": GREEN_DOC.replace("TC3", "TC2"), "want": "未被任何任务承接"},
    {"name": "red-open-questions", "expect": 1,
     "doc": GREEN_DOC.replace("## 存疑汇总\n\n无。", "## 存疑汇总\n\n1. SM2 的 Z 值到底是什么？待确认。"),
     "want": "存疑"},
    {"name": "red-thin-task", "expect": 1,
     "doc": GREEN_DOC.replace("新增 authn/sm2 验签原语并接入分派", "做"), "want": "近乎为空"},
]


def run_case(case: dict) -> tuple[bool, str]:
    case_dir = CASES / case["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir)
    # 迷你三输入（说明书/门禁结果内容无关紧要，存在且 sha1 一致即可；
    # 但断言钉了 sha1——用环境变量覆盖为迷你夹具的）
    import hashlib
    mini = {
        "spec": MINI_TEST,  # 说明书位放任意内容
        "test": MINI_TEST,
        "gate": "# 门禁结果\n\n| 门禁状态 | 通过 |\n",
    }
    env = {}
    targets = {
        "spec": BASE / "模块详细设计说明书.md",
        "test": BASE / "模块测试用例设计.md",
        "gate": BASE / ".context" / "模块设计门禁结果.md",
    }
    for key, rel in targets.items():
        target = case_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(mini[key].encode("utf-8"))
        env[key] = hashlib.sha1(mini[key].encode("utf-8")).hexdigest()
    if case.get("mutate") == "spec":
        with open(case_dir / targets["spec"], "a", encoding="utf-8") as f:
            f.write("\n改写\n")
    for rel, content in (case.get("extra") or {}).items():
        target = case_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if case["doc"] is not None:
        target = case_dir / DOC_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(case["doc"], encoding="utf-8")

    runenv = dict(**os.environ)
    runenv["TS_SPEC_SHA1"] = env["spec"]
    runenv["TS_TEST_SHA1"] = env["test"]
    runenv["TS_GATE_SHA1"] = env["gate"]
    if case.get("mutate") == "spec":
        # 改写后 sha1 变化，但环境钉的是改写前——断言应报「输入被改写」
        pass
    result = subprocess.run(
        [sys.executable, str(ASSERT)],
        cwd=case_dir, env=runenv, capture_output=True, text=True,
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
    return ok, f"{detail} | out={output.strip()[-260:]}"


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
