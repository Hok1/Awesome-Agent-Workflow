#!/usr/bin/env python3
"""assert_taskdev.py 红绿验证（迷你 git 仓；cargo 断言以 TD_SKIP_CARGO 跳过）。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
ASSERT = ROOT.parent / "assert_taskdev.py"

OVERVIEW_GREEN = """# rbs-core 任务计划

## 执行记录

### T1：SM2 验签能力与 Bearer 用户认证

- 状态：Completed
- 修改文件：rbs/core/src/auth/authn/sm2.rs（新增）
- 核心实现：SM3+SM2 验签
- 设计偏差：无
- 待处理：无

#### 实现期补充与残余风险

- 补测：签名 r||s 长度异常的拒绝路径
- 残余风险：无
"""

GIT = shutil.which("git") or "git"


def git(args: list[str], cwd: Path) -> None:
    subprocess.run([GIT] + args, cwd=cwd, capture_output=True, check=True)


CASE_LIST: list[dict] = [
    {"name": "green", "expect": 0},
    {"name": "red-head-moved", "expect": 1, "extra_commit": True, "want": "HEAD 移动"},
    {"name": "red-staged", "expect": 1, "stage": True, "want": "暂存区改动"},
    {"name": "red-no-backfill", "expect": 1, "overview": "# 计划\n\n## 执行记录\n\n（空）\n",
     "want": "T1 小节"},
    {"name": "red-no-risk-section", "expect": 1,
     "overview": OVERVIEW_GREEN.replace("#### 实现期补充与残余风险", "#### 其他"),
     "want": "实现期补充与残余风险"},
    {"name": "red-scope-creep", "expect": 1, "touch": "rbs/core/src/admin/key.rs",
     "want": "超出 T1 范围"},
    {"name": "red-no-sm2-module", "expect": 1, "no_sm2": True, "want": "未新增"},
    {"name": "red-no-tests", "expect": 1, "no_tests": True, "want": "自动化测试"},
]


def _force_remove(func, path, _exc):
    os.chmod(path, 0o666)
    func(path)


def run_case(case: dict) -> tuple[bool, str]:
    case_dir = CASES / case["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir, onexc=_force_remove)
    (case_dir / ".sdd/SR-1/AR-1/rbs-core").mkdir(parents=True)
    (case_dir / "rbs/core/src/auth/authn").mkdir(parents=True)

    git(["init", "-q"], case_dir)
    git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base"], case_dir)
    head = subprocess.run([GIT, "rev-parse", "HEAD"], cwd=case_dir, capture_output=True,
                          text=True, check=True).stdout.strip()

    (case_dir / ".sdd/SR-1/AR-1/rbs-core/tasks-overview.md").write_text(
        case.get("overview", OVERVIEW_GREEN), encoding="utf-8")

    if not case.get("no_sm2"):
        sm2 = case_dir / "rbs/core/src/auth/authn/sm2.rs"
        sm2.write_text("pub fn verify_sm2() {}\n", encoding="utf-8")
    if not case.get("no_tests"):
        common = case_dir / "rbs/core/src/auth/authn/common.rs"
        common.write_text("#[cfg(test)]\nmod tests {\n    #[test]\n    fn t() { assert!(true); }\n}\n",
                          encoding="utf-8")
    if case.get("touch"):
        t = case_dir / case["touch"]
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("// touched\n", encoding="utf-8")
    if case.get("stage"):
        f = case_dir / "rbs/core/src/auth/authn/staged.rs"
        f.write_text("// staged\n", encoding="utf-8")
        git(["add", "rbs/core/src/auth/authn/staged.rs"], case_dir)
    if case.get("extra_commit"):
        git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "moved"], case_dir)

    env = dict(**os.environ)
    env["TD_BASE_COMMIT"] = head
    env["TD_SKIP_CARGO"] = "1"
    result = subprocess.run(
        [sys.executable, str(ASSERT)],
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
