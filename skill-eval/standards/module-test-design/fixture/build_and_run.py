#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造并提交 module-test-design 测评套件（严格模式），然后启动实验。"""
import argparse
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:18110/api/v1"
RBS = r"C:\code\workspace\globaltrustauthority-rbs"
AAW = r"C:\code\workspace\Awesome-Agent-Workflow"
SKILL = os.path.join(AAW, "skills", "module-test-design")
STAGE = r"C:\tmp\ctx5td"

SUITE_NAME = "module-test-design-SR1-rbcore-eval"
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
        r'cmd /c copy /Y "C:\tmp\ctx5aa\fixture\software_architecture.md" ".sdd\software_architecture.md"',
        r'cmd /c copy /Y "%s\fixture\模块详细设计说明书.md" ".sdd\SR-1\AR-1\rbs-core\模块详细设计说明书.md"' % STAGE,
        r'cmd /c copy /Y "%s\fixture\详细设计上下文.md" ".sdd\SR-1\AR-1\rbs-core\.context\详细设计上下文.md"' % STAGE,
        r'cmd /c copy /Y "%s\preflight_testdesign.py" ".sdd\SR-1\preflight_testdesign.py"' % STAGE,
    ],
    "preflight": [
        r"python .sdd\SR-1\preflight_testdesign.py",
    ],
    "network": False,
    "timeout_seconds": 900,
}

CASE_INPUT = """你使用 module-test-design skill，基于已定稿的 TOBE 详细设计，为 rbs-core 模块的 SR-1/AR-1 做测试用例设计（严格模式）。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不要修改）】
- 原始需求：.sdd/SR-1/original-requirement.md
- TOBE 正式说明书：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md
- 详细设计上下文：.sdd/SR-1/AR-1/rbs-core/.context/详细设计上下文.md
  （含 ASIS 证据与 TOBE 推导、追踪矩阵）

【本次任务】
- 严格模式（SR/AR 入口）：把 TOBE 已定稿的设计目标、契约、流程、异常边界、风险和
  可测试性输入转化为可执行的最小充分验证集
- SR=SR-1，AR=AR-1（SM2 用户认证），模块组名=rbs-core

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过；
   需要用户或上游确认的问题，按 skill 规定处理，不要等待回答。
2. 本环境不提供任何 MCP 工具。网络不可用。
3. 严格按 skill 正文规定的模式判定、工作法与产物契约执行。

【输出要求】
1. 按 skill 的产物契约产出到对应路径（SR=SR-1，AR=AR-1，模块组名=rbs-core）。
2. 最后回复：给出产物路径、用例总数与分层分布、覆盖矩阵摘要、缺口清单。
"""

CASE_EXPECTED = """产出 .sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md，且：

- 每条用例为 `##### TCn` 条目，含 优先级/覆盖目标/场景/建议位置/自动化 与
  「前置 / 输入 / 预期 / 断言」四个行为字段；用例正文不使用任何表格。
- 断言条件精确但语言无关，不含可直接粘贴的断言代码、fixture 或 mock 实现。
- 用例正文之前有用例总览（按验证场景分组的树状概览）；声明采用最小充分验证集。
- 覆盖矩阵：TOBE 决策/契约（D 编号）→ 优先级 → 覆盖用例（TC 编号）→ 覆盖状态 →
  未覆盖原因。
- TOBE 正式说明书不被改写（测试设计是独立成果物）。
- 不替 TOBE 补设计：发现设计不足时输出缺口与回流，不自行发明错误码/字段语义。

依据：module-test-design SKILL.md §3/§4、成果物协作规则、质量标准、阻塞规则。
"""

CASE_GRADERS = [
    {
        "id": "testdesign-assert",
        "type": "command",
        "name": "测试设计黑盒断言（产物/TC形态/无表格/四字段/覆盖矩阵/说明书未动/语言无关）",
        "command": r"python C:\tmp\ctx5td\assert_testdesign.py",
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
                "id": "sr1-rbcore-testdesign",
                "name": "SR-1 rbs-core 模块测试用例设计（严格模式）",
                "input": CASE_INPUT,
                "expected": CASE_EXPECTED,
                "weight": 1,
                "agent_context": "",
                "max_turns": 20,
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
    for p in (
        os.path.join(STAGE, "fixture", "模块详细设计说明书.md"),
        os.path.join(STAGE, "fixture", "详细设计上下文.md"),
        os.path.join(STAGE, "assert_testdesign.py"),
    ):
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
