#!/usr/bin/env python3
"""assert_asis.py / assert_asis_blocked.py 红绿验证。

正向绿夹具：合规 context（C1-C8 + declared 标记 + A/E 编号 + 真实路径）。
反向绿夹具：(a) 完全无产物；(b) 产物带 blocked 标记。
每个 case 目录下放置最小真实代码文件，供断言 5 的路径核验。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
ASSERT_POS = ROOT.parent / "assert_asis.py"
ASSERT_NEG = ROOT.parent / "assert_asis_blocked.py"

# case 目录里预置的真实代码文件（供断言 5 核验路径存在性）
REAL_FILES = [
    "rbs/core/src/auth/mod.rs",
    "rbs/core/src/auth/authn/mod.rs",
    "rbs/core/src/admin/key.rs",
    "rbs/rest/src/middleware/auth.rs",
    "tools/src/token/mod.rs",
]

GREEN_CONTEXT = """# 模块详细设计 ASIS context

## C1. ASIS 状态与阅读说明

状态：完成。未使用 SubAgent，原因：环境不支持。

## C2. 模块边界确认

边界来源：declared by software_architecture.md。
目标模块 rbs-core（rbs/core/），本次分析切片为 SM2 验签相关区域。

## C3. 关键 ASIS 事实

| 编号 | 事实 | 类型 | 来源探索 | 证据 |
|---|---|---|---|---|
| A1 | 验签入口集中在 rbs/core/src/auth/authn/mod.rs，按 alg 分派 Verifier | 事实 | Q1 | E1 |
| A2 | 用户公钥登记由 rbs/core/src/admin/key.rs 校验并写入用户库 | 事实 | Q2 | E2 |
| A3 | 认证中间件只传递 token，见 rbs/rest/src/middleware/auth.rs | 事实 | Q3 | E3 |

## C4. 调用链与数据流

中间件 → Authenticator → Verifier（证据 E1、E3）。

## C5. 配置、数据、测试与依赖现状

用户库表结构见 rbs/core/src/admin/key.rs 相关迁移（E2）。

## C6. 规格漂移、待确认与阻塞

无阻塞。一项待确认：JWKS 缓存策略（TOBE 决策输入）。

## C7. 证据索引

| 编号 | 位置 | 检索方式 |
|---|---|---|
| E1 | rbs/core/src/auth/authn/mod.rs | rg "TokenVerifier" |
| E2 | rbs/core/src/admin/key.rs | rg "validate_and_derive_alg" |
| E3 | rbs/rest/src/middleware/auth.rs | rg "Bearer" |

## C8. 需求/AR 追溯矩阵

| 需求 | ASIS 结论 | 证据 | 覆盖状态 |
|---|---|---|---|
| SR-1 验签 | A1、A3 | E1、E3 | 已覆盖 |
"""

BLOCKED_CONTEXT = """# 模块详细设计 ASIS context

## C1. ASIS 状态与阅读说明

状态：阻塞。未使用 SubAgent，原因：环境不支持。

## C2. 模块边界确认

边界来源：blocked —— .sdd/software_architecture.md 缺失，无法识别目标模块边界。

## C6. 规格漂移、待确认与阻塞

### C6.2 ASIS 阻塞项

- 阻塞原因：.sdd/software_architecture.md 缺失。
- 已完成范围：无（阶段 1 中断）。
- 继续推进需要的输入：架构基线文档。
"""

CASE_LIST: list[dict] = [
    # ---------------- 正向（assert_asis.py） ----------------
    {"name": "pos-green", "script": ASSERT_POS, "expect": 0,
     "context": GREEN_CONTEXT},
    {"name": "pos-green-table-declared", "script": ASSERT_POS, "expect": 0,
     "context": GREEN_CONTEXT.replace(
         "边界来源：declared by software_architecture.md。\n目标模块 rbs-core",
         "| 来源 | 边界来源类型 |\n|---|---|\n| `.sdd/software_architecture.md` | declared |\n目标模块 rbs-core")},
    {"name": "pos-red-source-without-type", "script": ASSERT_POS, "expect": 1,
     "context": GREEN_CONTEXT.replace("边界来源：declared by software_architecture.md。",
                                      "边界来源：.sdd/software_architecture.md（已确认）。"),
     "want": "declared"},
    {"name": "pos-red-no-artifact", "script": ASSERT_POS, "expect": 1,
     "context": None, "want": "未找到"},
    {"name": "pos-red-missing-section", "script": ASSERT_POS, "expect": 1,
     "context": GREEN_CONTEXT.replace("## C7. 证据索引", "## 证据清单").replace("## C8. 需求/AR 追溯矩阵", "## 追溯"),
     "want": "固定目录骨架不完整"},
    {"name": "pos-red-no-declared-mark", "script": ASSERT_POS, "expect": 1,
     "context": GREEN_CONTEXT.replace("declared by software_architecture.md", "根据代码结构确认"),
     "want": "declared"},
    {"name": "pos-red-thin-evidence", "script": ASSERT_POS, "expect": 1,
     "context": GREEN_CONTEXT.replace("E1", "证据甲").replace("E2", "证据乙").replace("E3", "证据丙"),
     "want": "证据编号不足"},
    {"name": "pos-red-few-conclusions", "script": ASSERT_POS, "expect": 1,
     "context": GREEN_CONTEXT.replace("A2", "结论乙").replace("A3", "结论丙"),
     "want": "结论编号不足"},
    {"name": "pos-red-phantom-path", "script": ASSERT_POS, "expect": 1,
     "context": GREEN_CONTEXT.replace("rbs/core/src/auth/authn/mod.rs", "rbs/core/src/auth/sm9_verify.rs"),
     "want": "不存在的代码路径"},
    {"name": "pos-red-no-paths", "script": ASSERT_POS, "expect": 1,
     "context": GREEN_CONTEXT.replace("rbs/core/src/auth/authn/mod.rs", "验签模块").replace("rbs/core/src/admin/key.rs", "公钥登记模块").replace("rbs/rest/src/middleware/auth.rs", "认证中间件"),
     "want": "证据链未锚定真实代码"},
    {"name": "pos-red-formal-doc-created", "script": ASSERT_POS, "expect": 1,
     "context": GREEN_CONTEXT, "extra_files": {".sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md": "# 正式说明书\n"},
     "want": "ASIS 阶段创建了正式说明书"},
    {"name": "pos-red-tobe-phrase", "script": ASSERT_POS, "expect": 1,
     "context": GREEN_CONTEXT.replace("按 alg 分派 Verifier", "按 alg 分派 Verifier，建议采用策略模式重构"),
     "want": "TOBE 拍板短语"},
    # ---------------- 反向（assert_asis_blocked.py） ----------------
    {"name": "neg-green-no-output", "script": ASSERT_NEG, "expect": 0,
     "context": None},
    {"name": "neg-green-blocked-mark", "script": ASSERT_NEG, "expect": 0,
     "context": BLOCKED_CONTEXT},
    {"name": "neg-red-unblocked-context", "script": ASSERT_NEG, "expect": 1,
     "context": GREEN_CONTEXT, "want": "不带阻塞标记"},
    {"name": "neg-red-formal-doc", "script": ASSERT_NEG, "expect": 1,
     "context": None, "extra_files": {".sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md": "# 正式说明书\n"},
     "want": "正式说明书"},
    {"name": "neg-red-stray-analysis", "script": ASSERT_NEG, "expect": 1,
     "context": None, "extra_files": {".sdd/SR-1/analysis.md": "# 模块边界分析\n据代码结构，rbs/core 是核心模块\n"},
     "want": "契约外路径"},
]


def run_case(case: dict) -> tuple[bool, str]:
    case_dir = CASES / case["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir)
    for rel in REAL_FILES:
        target = case_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("// fixture\n", encoding="utf-8")
    if case.get("context") is not None:
        ctx = case_dir / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / ".context"
        ctx.mkdir(parents=True, exist_ok=True)
        (ctx / "详细设计上下文.md").write_text(case["context"], encoding="utf-8")
    for rel, content in (case.get("extra_files") or {}).items():
        target = case_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, str(case["script"])],
        cwd=case_dir, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120, check=False,
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
