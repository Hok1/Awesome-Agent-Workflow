#!/usr/bin/env python3
"""assert_tobe.py 红绿验证：绿夹具必须通过，红夹具必须在预期条款上失败。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
ASSERT = ROOT.parent / "assert_tobe.py"
DOC_REL = Path(".sdd") / "SR-1" / "AR-1" / "rbs-core" / "模块详细设计说明书.md"
CTX_REL = Path(".sdd") / "SR-1" / "AR-1" / "rbs-core" / ".context" / "详细设计上下文.md"

GREEN_CTX = """# 模块详细设计 ASIS context

## C1. ASIS 状态与阅读说明

## C3. 关键 ASIS 事实

| 编号 | 事实 |
|---|---|
| A1 | 验签入口按 TokenType 分派 |
| A2 | SUPPORTED_ALGORITHMS 硬编码 |
| A5 | 登记 alg 推导仅 RSA/P-256 |

## C14. TOBE 推导依据

| 决策编号 | 输入依据 | 推导过程摘要 | 被采纳原因 |
|---|---|---|---|
| D1 | R1 / A1 / A2 / E1 | 复用现有分派 | 改动面最小 |

## C16. 完整追踪矩阵

| 需求/AR | ASIS 结论 | 证据 | TOBE 决策 | 正式说明书章节 |
|---|---|---|---|---|
| R1 | A2 | E1 | D1 | 4.1 |
| R2 | A5 | E2 | D2 | 4.2 |
"""

GREEN_DOC = """# AR-1-SM2用户认证-rbs-core模块详细设计说明书

TOBE 状态：完成

## 1. 需求背景 / 当前 AR 描述

SR-1 要求用户认证支持 SM2。ASIS 结论 A1、A2 表明现有验签入口按 TokenType 分派。

## 2. 外部依赖

GTA 侧 SM2 表示法约定为外部输入（ASIS 待确认项，A4）。

## 3. 整体方案

在 rbs-core 的 authn 模块扩展 SM2 算法分支，复用现有 Verifier 抽象（A1）。

## 4. 模块详细方案

### 4.1 算法分派扩展

现状约束：`SUPPORTED_ALGORITHMS` 硬编码四种算法（A2）；`validate_and_derive_alg`
仅识别 RSA/P-256/384/521（A5）。目标设计：扩展白名单与推导逻辑。

公钥落库沿用 `auth_value` 字段（A8），无 DDL 变更。

### 4.2 验签链路

`BearerTokenVerifier` 主流程不变（A6），在 DecodingKey 构造处支持 SM2 PEM。

## 5. 对外接口

无新增对外接口；详见第 4 章契约与工程落点。

## 6. 数据库 / 表设计

无结构变更；`auth_value`/`auth_alg` 字段取值扩展（A8、A9）。

## 7. 受影响模块与交互

rbs-rest 中间件透传不受影响；rbs-cli 侧 SM2 签名为其独立设计范围。

## 8. 关键契约清单

| 契约 | 权威位置 |
|---|---|
| alg 取值扩展 | 4.1 |
| 公钥 PEM 存储 | 4.1 |

## 9. 附录 / 三方件约束

OpenSSL vendored 具备 SM2 能力（A16）。
"""


def with_rust_block(doc: str, lines: int) -> str:
    body = "\n".join(f"    let x_{i} = {i};" for i in range(lines))
    return doc + f"\n```rust\nfn impl_detail() {{\n{body}\n}}\n```\n"


CASE_LIST: list[dict] = [
    {"name": "green", "expect": 0, "doc": GREEN_DOC},
    {"name": "green-doc-status-variant", "expect": 0,
     "doc": GREEN_DOC.replace("TOBE 状态：完成", "文档状态：**部分完成**")},
    {"name": "green-table-status", "expect": 0,
     "doc": GREEN_DOC.replace("TOBE 状态：完成\n\n",
                              "| 决策编号 | 设计点 | 状态 / 待确认说明 |\n|---|---|---|\n| D1 | 分派扩展 | 已定稿 |\n\n")},
    {"name": "green-mermaid-e401-node", "expect": 0,
     "doc": GREEN_DOC + "\n```mermaid\nflowchart TD\n    A[请求] --> B{验签}\n    B -->|失败| E401[\"AuthError::TokenInvalid → 401\"]\n```\n"},
    {"name": "red-missing-file", "expect": 1, "doc": None, "want": "产物不存在"},
    {"name": "red-missing-chapter", "expect": 1,
     "doc": GREEN_DOC.replace("## 6. 数据库 / 表设计", "## 6. 存储"),
     "want": "大纲不完整"},
    {"name": "red-evidence-section", "expect": 1,
     "doc": GREEN_DOC + "\n## 附：证据索引\n\n| E1 | 位置 |\n",
     "want": "证据索引"},
    {"name": "red-excess-e-refs", "expect": 1,
     "doc": GREEN_DOC + "\n依据 E1、E2、E3、E4 四处证据。\n",
     "want": "证据编号"},
    {"name": "red-process-words", "expect": 1,
     "doc": GREEN_DOC + "\n以上结论的检索过程如下：略。\n",
     "want": "过程性内容"},
    {"name": "red-test-cases", "expect": 1,
     "doc": GREEN_DOC + "\n测试用例 TC-01：SM2 验签通过。\n",
     "want": "测试用例编号"},
    {"name": "red-task-split", "expect": 1,
     "doc": GREEN_DOC + "\n## 任务拆分\n\nTASK-1：实现白名单扩展。\n",
     "want": "任务拆分"},
    {"name": "red-long-rust", "expect": 1,
     "doc": with_rust_block(GREEN_DOC, 12),
     "want": "Rust 代码块"},
    {"name": "red-no-identifiers", "expect": 1,
     "doc": GREEN_DOC.replace("SUPPORTED_ALGORITHMS", "算法白名单").replace("validate_and_derive_alg", "alg 推导函数").replace("auth_value", "公钥字段").replace("BearerTokenVerifier", "Bearer 验签器"),
     "want": "契约保真不足"},
    {"name": "red-no-status", "expect": 1,
     "doc": GREEN_DOC.replace("TOBE 状态：完成\n\n", ""),
     "want": "状态表达"},
    {"name": "red-ctx-missing-tobe-part", "expect": 1,
     "doc": GREEN_DOC,
     "ctx": GREEN_CTX.split("## C14")[0],
     "want": "追踪矩阵"},
    {"name": "red-ctx-no-a-refs", "expect": 1,
     "doc": GREEN_DOC,
     "ctx": GREEN_CTX.replace("R1 / A1 / A2 / E1", "R1 / 现状描述").replace("A2 | E1", "结论 | 证据").replace("A5 | E2", "结论 | 证据"),
     "want": "追踪未引用 ASIS 结论编号"},
    {"name": "red-ctx-beyond-a16", "expect": 1,
     "doc": GREEN_DOC,
     "ctx": GREEN_CTX + "\n| R3 | A23 | E9 | D3 | 4.3 |\n",
     "want": "凭空编号"},
]


def run_case(case: dict) -> tuple[bool, str]:
    case_dir = CASES / case["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    if case["doc"] is not None:
        target = case_dir / DOC_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(case["doc"], encoding="utf-8")
    ctx_text = case.get("ctx", GREEN_CTX)
    if ctx_text is not None:
        ctx_target = case_dir / CTX_REL
        ctx_target.parent.mkdir(parents=True, exist_ok=True)
        ctx_target.write_text(ctx_text, encoding="utf-8")
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
        detail = "TOBE-ASSERT-PASS"
    else:
        detail = f"期望退出码 {case['expect']} 实得 {result.returncode}"
    return ok, f"{detail} | out={output.strip()[-300:]}"


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
