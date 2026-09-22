#!/usr/bin/env python3
"""assert_testdesign.py 红绿验证。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
ASSERT = ROOT.parent / "assert_testdesign.py"
SPEC_SRC = ROOT.parent / "fixture" / "模块详细设计说明书.md"
SPEC_REL = Path(".sdd") / "SR-1" / "AR-1" / "rbs-core" / "模块详细设计说明书.md"
DOC_REL = Path(".sdd") / "SR-1" / "AR-1" / "rbs-core" / "模块测试用例设计.md"

TC1 = """##### TC1

- 优先级：P0
- 覆盖目标：D1（SM2 分支分派）
- 场景：SM2 Bearer 验签通过
- 建议位置：rbs/core/src/auth/authn/sm2.rs 相邻测试
- 自动化：是
- 前置：用户库已登记 SM2 公钥 PEM
- 输入：alg=SM2 的用户 JWT（SM3 摘要、r||s 签名）
- 预期：验签通过，返回 BearerContext
- 断言：验签结果为成功，上下文 sub 与令牌载荷一致；比较对象为返回值与上下文字段
"""

TC2 = """##### TC2

- 优先级：P0
- 覆盖目标：D1（未知算法拒绝保持）
- 场景：alg=SM3 等未知算法被拒绝
- 建议位置：同上
- 自动化：是
- 前置：无
- 输入：alg 取值非法的 JWT
- 预期：统一拒绝，错误语义不变
- 断言：响应错误类别与既有未知算法一致；不泄露算法枚举信息
"""

TC3 = """##### TC3

- 优先级：P0
- 覆盖目标：D3（SM2 公钥登记）
- 场景：管理员登记 SM2 JWK 公钥
- 建议位置：rbs/core/src/admin/key.rs 相邻测试
- 自动化：是
- 前置：管理员鉴权通过
- 输入：kty=EC、crv=SM2 的 JWK
- 预期：登记成功，auth_value 落库为 PEM
- 断言：落库字段为 PEM 形态且算法取值正确；再次验签可取其公钥
"""

GREEN_DOC = f"""# AR-1 SM2 用户认证 rbs-core 模块测试用例设计

## 1. 测试范围与策略摘要

本次采用最小充分验证集，优先覆盖 P0/P1 设计风险，允许一条用例覆盖多个设计目标。

## 2. 用例总览

- **算法分派**
  - TC1：SM2 Bearer 验签通过
  - TC2：未知算法拒绝
- **公钥登记**
  - TC3：SM2 公钥 JWK 登记

## 3. 测试用例

### 3.1 模块内功能集成测试

#### 3.1.1 算法分派

{TC1}
{TC2}

### 3.2 契约测试

#### 3.2.1 公钥登记

{TC3}

## 4. 覆盖矩阵

| TOBE 决策/契约 | 优先级 | 覆盖用例 | 覆盖状态 | 未覆盖原因 |
|---|---|---|---|---|
| D1 算法分派扩展 | P0 | TC1、TC2 | 已覆盖 | — |
| D3 互操作约定 | P0 | TC1、TC3 | 已覆盖 | — |

## 5. 缺口与回流建议

无。
"""

CASE_LIST: list[dict] = [
    {"name": "green", "expect": 0, "doc": GREEN_DOC},
    {"name": "red-missing-file", "expect": 1, "doc": None, "want": "产物不存在"},
    {"name": "red-too-few-cases", "expect": 1,
     "doc": GREEN_DOC.replace(TC2, "").replace(TC3, ""),
     "want": "未形成最小验证集"},
    {"name": "red-table-in-case", "expect": 1,
     "doc": GREEN_DOC.replace("- 断言：验签结果为成功，上下文 sub 与令牌载荷一致；比较对象为返回值与上下文字段",
                              "- 断言：\n\n  | 字段 | 期望 |\n  |---|---|\n  | sub | 一致 |\n"),
     "want": "用例正文含表格"},
    {"name": "red-missing-assert-field", "expect": 1,
     "doc": GREEN_DOC.replace("- 断言：响应错误类别与既有未知算法一致；不泄露算法枚举信息\n", ""),
     "want": "缺行为字段"},
    {"name": "red-no-matrix", "expect": 1,
     "doc": GREEN_DOC.replace("## 4. 覆盖矩阵", "## 4. 覆盖说明").replace("| D1 算法分派扩展 | P0 | TC1、TC2 | 已覆盖 | — |", "").replace("| D3 互操作约定 | P0 | TC1、TC3 | 已覆盖 | — |", ""),
     "want": "缺少覆盖矩阵"},
    {"name": "red-matrix-no-d", "expect": 1,
     "doc": GREEN_DOC.replace("D1 算法分派扩展", "算法分派扩展").replace("D3 互操作约定", "互操作约定"),
     "want": "未关联 TOBE 决策编号"},
    {"name": "red-paste-able-code", "expect": 1,
     "doc": GREEN_DOC + "\n##### TC9\n\n- 前置：无\n- 输入：构造令牌\n- 预期：通过\n- 断言：\n\n```rust\n#[test]\nfn tc9() { assert!(verify()); }\n```\n",
     "want": "可直接粘贴"},
    {"name": "red-spec-modified", "expect": 1, "doc": GREEN_DOC,
     "spec_mutate": True, "want": "不得回写说明书"},
    {"name": "red-no-minimal-claim", "expect": 1,
     "doc": GREEN_DOC.replace("本次采用最小充分验证集，优先覆盖 P0/P1 设计风险，允许一条用例覆盖多个设计目标。",
                              "本次尽可能多地覆盖各种测试类型。"),
     "want": "最小充分"},
    {"name": "red-no-overview", "expect": 1,
     "doc": GREEN_DOC.replace("## 2. 用例总览", "## 2. 背景"),
     "want": "用例总览"},
]


def run_case(case: dict) -> tuple[bool, str]:
    case_dir = CASES / case["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir)
    spec_target = case_dir / SPEC_REL
    spec_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SPEC_SRC, spec_target)
    if case.get("spec_mutate"):
        with open(spec_target, "a", encoding="utf-8") as f:
            f.write("\n被改写的一行\n")
    if case["doc"] is not None:
        target = case_dir / DOC_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(case["doc"], encoding="utf-8")
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
