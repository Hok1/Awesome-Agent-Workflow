#!/usr/bin/env python3
"""assert_repoinit.py 红绿验证（迷你 workspace：少量真实目录供路径核验）。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
ASSERT = ROOT.parent / "assert_repoinit.py"

GREEN_ARCH = """# 软件实现设计说明书 (SDD)

## 文档元数据

  project: "globaltrustauthority-rbs"

# 目录

- 1 系统概览 …… 第 40 行（{{行号占位保留——目录区豁免}}）

## 1 系统概览

### 1.1 系统定位

**系统名称**: RBS
**一句话描述**: 资源经纪服务，验证远程证明并分发密钥。
**所属领域**: 机密计算
**核心价值**: 证明验证、密钥分发、策略管控

### 1.2 系统边界

- "{{包含的功能范围1——1.2 区豁免，保留占位}}"

### 1.3 上下游关系

- system: "{{上游系统——1.3 区豁免}}"

## 2 模块清单

### 2.1 模块职责表

| 模块 | 职责 | 类型 | 路径 |
|---|---|---|---|
| rbs-core | 认证验签与公钥登记 | 业务 | rbs/core |
| rbs-rest | REST API 层 | 业务 | rbs/rest |
| rbs-cli | 命令行工具 | 工具 | tools |
"""

GREEN_AGENTS = """# AGENTS.md

## Build / Test

- 构建：`cargo build --workspace`
- 测试：`cargo test`

## Language

Rust 2021。
"""

CASE_LIST: list[dict] = [
    {"name": "green", "expect": 0, "arch": GREEN_ARCH, "agents": GREEN_AGENTS},
    {"name": "red-no-arch", "expect": 1, "arch": None, "agents": GREEN_AGENTS, "want": "不存在"},
    {"name": "red-residual-placeholder", "expect": 1, "agents": GREEN_AGENTS,
     "arch": GREEN_ARCH.replace("**系统名称**: RBS", "**系统名称**: {{系统名称}}"),
     "want": "残留"},
    {"name": "red-no-real-path", "expect": 1, "agents": GREEN_AGENTS,
     "arch": GREEN_ARCH.replace("rbs/core", "核心仓").replace("rbs/rest", "接口仓"),
     "want": "真实代码路径"},
    {"name": "red-phantom-path", "expect": 1, "agents": GREEN_AGENTS,
     "arch": GREEN_ARCH.replace("rbs/core", "rbs/core/src/ghost"), "want": "不存在"},
    {"name": "green-crate-domain-not-path", "expect": 0, "agents": GREEN_AGENTS,
     "arch": GREEN_ARCH + "\n模块关系：rbs-core/auth 依赖 rbs-core/infra；rbc 与 rbs-cli 并列。\n"},
    {"name": "red-missing-section", "expect": 1, "agents": GREEN_AGENTS,
     "arch": GREEN_ARCH.replace("## 2 模块清单", "## 2 组件"), "want": "固定章节缺失"},
    {"name": "red-no-agents", "expect": 1, "arch": GREEN_ARCH, "agents": None,
     "want": "AGENTS.md 不存在"},
    {"name": "red-agents-no-cargo", "expect": 1, "arch": GREEN_ARCH,
     "agents": "# AGENTS.md\n\n构建：make。\n", "want": "cargo"},
]


def run_case(case: dict) -> tuple[bool, str]:
    case_dir = CASES / case["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir)
    for d in ("rbs/core", "rbs/rest", "tools", "rbc", "rbs/api-types"):
        (case_dir / d).mkdir(parents=True, exist_ok=True)
    if case.get("arch") is not None:
        t = case_dir / ".sdd"
        t.mkdir(parents=True, exist_ok=True)
        (t / "software_architecture.md").write_bytes(case["arch"].encode("utf-8"))
    if case.get("agents") is not None:
        (case_dir / "AGENTS.md").write_bytes(case["agents"].encode("utf-8"))

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
    return ok, f"{detail} | out={output.strip()[-280:]}"


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
