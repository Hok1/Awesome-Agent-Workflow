#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造并提交 task-split 测评套件，然后启动实验。"""
import argparse
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:18110/api/v1"
RBS = r"C:\code\workspace\globaltrustauthority-rbs"
AAW = r"C:\code\workspace\Awesome-Agent-Workflow"
SKILL = os.path.join(AAW, "skills", "task-split")
STAGE = r"C:\tmp\ctx5ts"

SUITE_NAME = "task-split-SR1-rbcore-eval"
EXP_PROFILE = {
    "schema_version": 2,
    "name": "chrys-deepseek-official-flash-v1",
    "runner_provider": "chrys",
    "runner_model": "e5d1a7b2c901",
    "runner_reasoning_effort": "high",
    "judge_provider": "chrys",
    "judge_model": "e5d1a7b2c901",
    "judge_reasoning_effort": "high",
    "timeout_seconds": 5400,
    "network": False,
    "allowed_mcp_servers": [],
}

SETUP = {
    "commands": [
        r"cmd /c mkdir .sdd\SR-1\AR-1\rbs-core\.context",
        r'cmd /c copy /Y "C:\tmp\ctx4gate\original-requirement.md" ".sdd\SR-1\original-requirement.md"',
        r'cmd /c copy /Y "%s\fixture\模块详细设计说明书.md" ".sdd\SR-1\AR-1\rbs-core\模块详细设计说明书.md"' % STAGE,
        r'cmd /c copy /Y "%s\fixture\模块测试用例设计.md" ".sdd\SR-1\AR-1\rbs-core\模块测试用例设计.md"' % STAGE,
        r'cmd /c copy /Y "%s\fixture\模块设计门禁结果.md" ".sdd\SR-1\AR-1\rbs-core\.context\模块设计门禁结果.md"' % STAGE,
    ],
    "preflight": [],
    "network": False,
    "timeout_seconds": 900,
}

CASE_INPUT = """你使用 task-split skill，基于已通过门禁的详细设计和测试设计生成薄任务计划。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不得修改）】
- 正式说明书：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md
- 测试设计：.sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md
- 门禁结果：.sdd/SR-1/AR-1/rbs-core/.context/模块设计门禁结果.md（结论：通过）

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过；
   需要用户确认的问题按 skill 规定处理；成果在无用户确认前视为草案，
   不启动任何后续实现工作。
2. 本环境不提供任何 MCP 工具。网络不可用。
3. 严格按 skill 正文规定的流程与产物契约执行。

【输出要求】
1. 按 skill 的产物契约产出到对应路径（SR=SR-1，AR=AR-1，模块组名=rbs-core）。
2. 最后回复：给出产物路径、任务数量与标题列表、覆盖核对结论、存疑状态。
"""

CASE_EXPECTED = """产出 .sdd/SR-1/AR-1/rbs-core/tasks-overview.md，且：

- 遵循 overview_template.md 骨架（元信息/执行规则/串行执行顺序/任务计划/存疑汇总/
  待处理用例登记/执行记录）。
- 任务计划表六列齐全（编号|任务|做什么|改哪些文件|验证哪些用例|前置），
  编号 T1 起连续且与执行顺序一致。
- 不生成任何独立 T[N]-*.md 任务文件。
- 测试设计中的每个 TC 编号都有任务承接（覆盖完整）。
- 存疑汇总无未决项（存疑不放行）。
- 三份输入不被改写。

依据：task-split SKILL.md 拆分原则、任务计划边界、Phase 1-4、overview_template.md。
"""

CASE_GRADERS = [
    {
        "id": "tasksplit-assert",
        "type": "command",
        "name": "任务拆分黑盒断言（产物/无独立任务文件/骨架/计划表/覆盖完整/存疑清零/输入只读）",
        "command": r"python C:\tmp\ctx5ts\assert_tasksplit.py",
        "weight": 100,
        "hard_gate": False,
        "timeout_seconds": 120,
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
                "id": "sr1-rbcore-tasksplit",
                "name": "SR-1 rbs-core 任务拆分",
                "input": CASE_INPUT,
                "expected": CASE_EXPECTED,
                "weight": 1,
                "agent_context": "",
                "max_turns": 12,
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
    for name in ("模块详细设计说明书.md", "模块测试用例设计.md", "模块设计门禁结果.md"):
        p = os.path.join(STAGE, "fixture", name)
        if not os.path.isfile(p):
            print("MISSING staged file: " + p)
            return 2
    if not os.path.isfile(os.path.join(STAGE, "assert_tasksplit.py")):
        print("MISSING assert script")
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
