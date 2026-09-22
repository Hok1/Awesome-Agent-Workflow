#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造并提交 task-dev 测评套件（T1 单任务端到端编码），然后启动实验。"""
import argparse
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:18110/api/v1"
RBS = r"C:\code\workspace\globaltrustauthority-rbs"
AAW = r"C:\code\workspace\Awesome-Agent-Workflow"
SKILL = os.path.join(AAW, "skills", "task-dev")
STAGE = r"C:\tmp\ctx5tdv"

SUITE_NAME = "task-dev-SR1-rbcore-T1-eval"
EXP_PROFILE = {
    "schema_version": 2,
    "name": "chrys-deepseek-official-flash-v1",
    "runner_provider": "chrys",
    "runner_model": "e5d1a7b2c901",
    "runner_reasoning_effort": "high",
    "judge_provider": "chrys",
    "judge_model": "e5d1a7b2c901",
    "judge_reasoning_effort": "high",
    "timeout_seconds": 7200,
    "network": False,
    "allowed_mcp_servers": [],
}

SETUP = {
    "commands": [
        # copytree 会把 base 的 target/ 一并复制到 workspace，其中嵌入的绝对路径
        # （build script exe）在新位置失效，cargo 链接报 LNK1104——先清掉强制重建。
        r"cmd /c if exist target rmdir /s /q target",
        r"cmd /c mkdir .sdd\SR-1\AR-1\rbs-core\.context",
        r'cmd /c copy /Y "C:\tmp\ctx4gate\original-requirement.md" ".sdd\SR-1\original-requirement.md"',
        r'cmd /c copy /Y "C:\tmp\ctx5aa\fixture\software_architecture.md" ".sdd\software_architecture.md"',
        r'cmd /c copy /Y "%s\fixture\模块详细设计说明书.md" ".sdd\SR-1\AR-1\rbs-core\模块详细设计说明书.md"' % STAGE,
        r'cmd /c copy /Y "%s\fixture\模块测试用例设计.md" ".sdd\SR-1\AR-1\rbs-core\模块测试用例设计.md"' % STAGE,
        r'cmd /c copy /Y "%s\fixture\模块设计门禁结果.md" ".sdd\SR-1\AR-1\rbs-core\.context\模块设计门禁结果.md"' % STAGE,
        r'cmd /c copy /Y "%s\fixture\tasks-overview.md" ".sdd\SR-1\AR-1\rbs-core\tasks-overview.md"' % STAGE,
        r'cmd /c copy /Y "%s\preflight_taskdev.py" ".sdd\SR-1\preflight_taskdev.py"' % STAGE,
    ],
    "preflight": [
        r"python .sdd\SR-1\preflight_taskdev.py",
    ],
    "network": False,
    "timeout_seconds": 900,
}

CASE_INPUT = """你使用 task-dev skill，执行 tasks-overview 中的 T1 任务（SM2 验签能力与 Bearer 用户认证）。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace，Rust 工具链可用）。

【输入（已就位，直接读取；权威文档不得修改）】
- 任务计划：.sdd/SR-1/AR-1/rbs-core/tasks-overview.md（当前任务=T1，前置=无）
- 正式说明书：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md
- 测试设计：.sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md
- 门禁结果：.sdd/SR-1/AR-1/rbs-core/.context/模块设计门禁结果.md（结论：通过）
- 架构基线：.sdd/software_architecture.md

【本次执行方式（重要，请严格遵守）】
1. 单独执行（非 aaw-workflow 编排）：跳过状态命令与 done 回调，不读写任何 state.json；
   除此之外的流程与质量边界不变。
2. 无头执行，没有人类在旁；需要用户决策的问题按 skill 规定记录并停在安全状态，
   不要等待回答。
3. 本环境不提供任何 MCP 工具，网络不可用。
4. 本环境无法启动并行 SubAgent：语义 Review 环节由你自行以只读方式按两个视角
   （A：需求一致性/正确性/安全/兼容；B：性能/结构/可读性/过度设计）各出一份报告
   并落盘到 .sdd/SR-1/AR-1/rbs-core/.context/ 下。
5. 本环境无 code-check 扫描器：CodeCheck 环节执行 cargo 的构建/测试与仓库既有检查。
6. 本工作区路径较深，cargo 构建若遇 LNK1104 类链接错误（Windows 长路径限制），
   用 `subst Z: <工作区路径>` 映射短盘符后在 Z:\ 下执行构建与测试，结束后
   `subst Z: /d` 还原。另：vendored OpenSSL 的 Configure 需要原生 Windows perl——
   构建前把 `C:\Strawberry\perl\bin` 前置到 PATH（Git 自带的 MSYS perl 会导致
   OpenSSL 配置失败）。
7. 严格按 skill 的固定流程执行；绝不执行 git add / git commit / push。

【输出要求】
1. 完成 T1 的实现与测试（范围见任务计划的「改哪些文件」「验证哪些用例」两列），
   受影响测试全部通过。
2. 按 skill 规定回填 tasks-overview.md 的执行记录（含必填小节）。
3. 最后回复：给出修改文件清单、测试执行结果、双视角 Review 结论、候选提交信息。
"""

CASE_EXPECTED = """T1 完成后的 workspace 落态：

- git HEAD 不变、无暂存区改动（绝不 git add/commit）。
- tasks-overview.md 的「执行记录」中有 T1 小节：状态 Completed + 必填的
  「实现期补充与残余风险」小节。
- 代码改动不超出 T1 范围（authn/mod.rs、common.rs、sm2.rs、bearer_token.rs 及
  测试位置）；不提前实现 T2/T3。
- 新增 rbs/core/src/auth/authn/sm2.rs；存在新增/修改的自动化测试。
- `cargo test -p rbs-core --lib` 退出码 0。

依据：task-dev SKILL.md 调度边界、固定流程 §1/§5、tasks-overview T1 行。
"""

CASE_GRADERS = [
    {
        "id": "taskdev-assert",
        "type": "command",
        "name": "task-dev 落态黑盒断言（git 纪律/执行记录回填/范围/实现与测试/cargo 验证）",
        "command": r"python C:\tmp\ctx5tdv\assert_taskdev.py",
        "weight": 100,
        "hard_gate": False,
        "timeout_seconds": 1800,
    },
]


def build_payload() -> dict:
    return {
        "name": SUITE_NAME,
        "project_path": RBS,
        "skill_path": SKILL,
        "setup": SETUP,
        "cases": [
            {
                "id": "sr1-rbcore-t1-dev",
                "name": "SR-1 rbs-core T1 SM2 验签能力实现",
                "input": CASE_INPUT,
                "expected": CASE_EXPECTED,
                "weight": 1,
                "agent_context": "",
                "max_turns": 30,
                "graders": CASE_GRADERS,
            }
        ],
    }


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--mode", default="quick", choices=["quick", "formal"])
    args = ap.parse_args()

    payload = build_payload()
    for name in ("模块详细设计说明书.md", "模块测试用例设计.md", "模块设计门禁结果.md",
                 "tasks-overview.md", "preflight_taskdev.py", "assert_taskdev.py"):
        p = os.path.join(STAGE, "fixture", name) if name.endswith(".md") else os.path.join(STAGE, name)
        if not os.path.isfile(p):
            print("MISSING staged file: " + p)
            return 2

    if args.dry_run:
        out = os.path.join(STAGE, "payload-dry.json")
        open(out, "w", encoding="utf-8", newline="\n").write(
            json.dumps(payload, ensure_ascii=False, indent=2))
        print("dry-run payload -> " + out)
        return 0
    if not args.post:
        print("nothing to do")
        return 0

    suite = post("/suites", payload)
    sid = suite.get("id") or suite.get("suite", {}).get("id")
    print("SUITE_ID =", sid)
    exp = post("/experiments", {
        "suite_id": sid,
        "mode": args.mode,
        "profile": EXP_PROFILE,
    })
    eid = exp.get("id") or exp.get("experiment", {}).get("id")
    print("EXPERIMENT_ID =", eid)
    print(json.dumps(exp, ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
