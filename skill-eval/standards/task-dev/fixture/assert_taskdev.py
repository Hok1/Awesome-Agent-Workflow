#!/usr/bin/env python3
"""task-dev 黑盒断言：读 workspace 状态 + git/cargo 外部命令，不 import 任何源码。

断言对象：RBS workspace 在执行 T1 后的落态（git 状态、tasks-overview 回填、
代码改动范围、cargo 验证结果）。
本脚本必须在 workspace 之外执行（判据保密纪律）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE = Path.cwd()
OVERVIEW = WORKSPACE / ".sdd" / "SR-1" / "AR-1" / "rbs-core" / "tasks-overview.md"
BASE_COMMIT = os.environ.get("TD_BASE_COMMIT", "7ef62cd3a9e035772827808054f3e8a3e904cf50")

# T1 允许的改动范围（tasks-overview 任务计划表「改哪些文件」列 + 测试位置）
T1_ALLOWED = (
    "rbs/core/src/auth/authn/mod.rs",
    "rbs/core/src/auth/authn/common.rs",
    "rbs/core/src/auth/authn/sm2.rs",
    "rbs/core/src/auth/authn/bearer_token.rs",
)

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


def run(cmd: list[str], timeout: int = 120, cwd: Path | None = None,
        env: dict | None = None) -> tuple[int, str]:
    result = subprocess.run(
        cmd, cwd=cwd or WORKSPACE, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


# ---------------------------------------------------------------- 断言 1
# 出处：SKILL.md 调度边界——「绝不执行 git add、git commit、push、发布」。
code, out = run(["git", "rev-parse", "HEAD"])
head = out.strip()
notes.append(f"HEAD={head[:12]}")
if head != BASE_COMMIT:
    fail(f"git HEAD 移动了（{head[:12]} != {BASE_COMMIT[:12]}），违反「绝不 git commit」")
code, out = run(["git", "diff", "--cached", "--name-only"])
if out.strip():
    fail(f"存在暂存区改动（违反「绝不 git add」）：{out.strip().splitlines()[:5]}")

# ---------------------------------------------------------------- 断言 2
# 出处：SKILL.md §5——「先在 tasks-overview.md 的 ## 执行记录 中写入当前
#       Task 的最终交接：状态（Completed）……以及必填小节「实现期补充与残余风险」
#       ——缺失会被 done 拒绝」。
if not OVERVIEW.is_file():
    fail("tasks-overview.md 缺失（输入夹具应就位）")
    text = ""
else:
    text = OVERVIEW.read_text(encoding="utf-8-sig")
    exec_match = re.search(r"##\s*执行记录[^\n]*\n(.*)\Z", text, re.S)
    exec_zone = exec_match.group(1) if exec_match else ""
    t1_match = re.search(r"###\s*T1[^\n]*\n(.*?)(?=\n###\s*T\d|\Z)", exec_zone, re.S)
    t1_zone = t1_match.group(1) if t1_match else ""
    notes.append(f"执行记录区字符数={len(exec_zone)} T1 小节={len(t1_zone)}")
    if not t1_zone:
        fail("执行记录中无 T1 小节（§5 强制交接检查）")
    else:
        if not re.search(r"状态[^\n]*Completed", t1_zone):
            fail("T1 小节未标记「状态：Completed」")
        if "实现期补充与残余风险" not in t1_zone and "实现期补充与残余风险" not in exec_zone:
            fail("缺必填小节「实现期补充与残余风险」（§5：缺失会被 done 拒绝）")

# ---------------------------------------------------------------- 断言 3
# 出处：SKILL.md §1.4——「不提前实现后续 Task」；tasks-overview T1 的
#       「改哪些文件」列为允许范围（出处=任务计划输入自身）。
code, out = run(["git", "status", "--porcelain", "-uall"])
# porcelain 行 = 2 字符状态码 + 空格 + 路径；从 index 2 起再 strip 更稳。
changed = []
for line in out.splitlines():
    if not line.strip():
        continue
    p = line[2:].strip().strip('"')
    if " -> " in p:  # rename: 取新路径
        p = p.split(" -> ", 1)[1].strip()
    changed.append(p)
code_changed = [
    p for p in changed
    if p.endswith((".rs", ".toml")) and not p.startswith(".sdd")
]
notes.append(f"代码改动文件={code_changed}")
for p in code_changed:
    if p in T1_ALLOWED:
        continue
    if p.startswith("rbs/core/tests/") or p.startswith("rbs/tests/"):
        continue  # 测试位置合理扩展
    fail(f"改动超出 T1 范围（不提前实现后续 Task）：{p}")

# ---------------------------------------------------------------- 断言 4
# 出处：tasks-overview T1——「新增」authn/sm2.rs；SKILL.md §1.4
#       「严格按已评审设计实现」。
if not (WORKSPACE / "rbs/core/src/auth/authn/sm2.rs").is_file():
    fail("未新增 rbs/core/src/auth/authn/sm2.rs（T1 计划的核心落点）")

# ---------------------------------------------------------------- 断言 5
# 出处：SKILL.md §1.5——「将前置条件、输入、步骤、预期结果、断言……
#       落实为自动化测试」。
test_hit = False
for p in changed:
    if not p.endswith(".rs"):
        continue
    fpath = WORKSPACE / p
    if not fpath.is_file():
        continue
    content = fpath.read_text(encoding="utf-8", errors="replace")
    if "#[test]" in content or "#[cfg(test)]" in content:
        test_hit = True
        break
if not test_hit:
    fail("未发现新增/修改的自动化测试（#[test] 或 #[cfg(test)]）")

# ---------------------------------------------------------------- 断言 6
# 出处：SKILL.md §1.7——「执行当前 Task 的全部非待处理测试，逐项核对预期
#       结果」；§1.8——「执行与实现正确性直接相关的构建、编译或类型检查」。
#       TD_SKIP_CARGO 仅供红绿验证的迷你仓使用（无 Rust 工程）；实测不设。
if os.environ.get("TD_SKIP_CARGO") == "1":
    notes.append("cargo 断言跳过（红绿迷你仓）")
else:
    # Windows MAX_PATH 适配：eval workspace 嵌套路径 + cargo build script 深路径
    # 超 260 字符导致 LNK1104。用 subst 映射短盘符后构建（环境适配，与判据无关）。
    drive = "Z:"
    run(["subst", drive, "/D"], timeout=15)  # 先卸（占用残留时）
    code, out = run(["subst", drive, str(WORKSPACE)], timeout=15)
    notes.append(f"subst exit={code} {out[:100]}")
    if code != 0:
        fail(f"subst 映射失败：{out[:200]}")
    else:
        try:
            # Strawberry Perl 前置：Git 自带 MSYS perl 会使 vendored OpenSSL 的
            # Configure 失败（实测主仓复现），必须原生 Windows perl 优先。
            cargo_env = os.environ.copy()
            cargo_env["PATH"] = r"C:\Strawberry\perl\bin" + os.pathsep + cargo_env.get("PATH", "")
            code, out = run(
                ["cargo", "test", "-p", "rbs-core", "--lib"],
                timeout=1800, cwd=Path(drive + "\\"), env=cargo_env,
            )
            notes.append(f"cargo test exit={code} 输出尾部={out[-200:]}")
            if code != 0:
                fail(f"cargo test -p rbs-core --lib 失败（exit={code}）：{out[-600:]}")
        finally:
            run(["subst", drive, "/D"], timeout=15)

print("NOTES: " + json.dumps(notes, ensure_ascii=False))
if problems:
    print("TASKDEV-ASSERT-FAIL")
    for index, problem in enumerate(problems, 1):
        print(f"  [{index}] {problem}")
    raise SystemExit(1)
print("TASKDEV-ASSERT-PASS")
