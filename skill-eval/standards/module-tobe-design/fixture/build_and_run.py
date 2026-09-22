#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造并提交 module-tobe-design 测评套件，然后启动实验。

判据保密：断言脚本不进 workspace（grader 命令引用 workspace 外绝对路径）；
task 不复述 skill 内部规则。

用法：
    python build_and_run.py --dry-run
    python build_and_run.py --post
"""
import argparse
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:18110/api/v1"
RBS = r"C:\code\workspace\globaltrustauthority-rbs"
AAW = r"C:\code\workspace\Awesome-Agent-Workflow"
SKILL = os.path.join(AAW, "skills", "module-tobe-design")
STAGE = r"C:\tmp\ctx5tb"

SUITE_NAME = "module-tobe-design-SR1-rbcore-eval"
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
        r'cmd /c copy /Y "C:\tmp\ctx4gate\SR-design.md" ".sdd\SR-1\SR-design.md"',
        r'cmd /c copy /Y "C:\tmp\ctx5aa\fixture\software_architecture.md" ".sdd\software_architecture.md"',
        r'cmd /c copy /Y "%s\fixture\详细设计上下文.md" ".sdd\SR-1\AR-1\rbs-core\.context\详细设计上下文.md"' % STAGE,
        r'cmd /c copy /Y "%s\preflight_tobe.py" ".sdd\SR-1\preflight_tobe.py"' % STAGE,
    ],
    "preflight": [
        r"python .sdd\SR-1\preflight_tobe.py",
    ],
    "network": False,
    "timeout_seconds": 900,
}

CASE_INPUT = """你使用 module-tobe-design skill，基于已完成的 ASIS 现状分析，对目标模块做 SR-1 需求的 TOBE 详细设计。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不要修改）】
- 原始需求：.sdd/SR-1/original-requirement.md
- 上游 SR 设计：.sdd/SR-1/SR-design.md
- ASIS 现状分析：.sdd/SR-1/AR-1/rbs-core/.context/详细设计上下文.md
  （16 条 ASIS 结论、47 条证据，覆盖验签入口、算法分派、公钥登记、配置与测试现状）

【本次设计任务】
- 目标模块：rbs-core（rbs/core/）
- 设计范围：SR-1 中 SM2 用户认证与公钥登记的 rbs-core 侧目标设计——验签算法分派扩展、
  公钥登记链路扩展、配置兼容，以及相关的失败语义、风险与可测试性输入
- SR=SR-1，AR=AR-1（SM2 用户认证），模块组名=rbs-core

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过，
   不要回调 aaw-workflow；执行中需要用户或上游确认的问题，按 skill 规定处理，
   不要等待回答。
2. 本环境不提供任何 MCP 工具。网络不可用。
3. 严格按 skill 正文规定的流程与产物契约执行。

【输出要求】
1. 按 skill 的产物契约产出到对应路径（SR=SR-1，AR=AR-1，模块组名=rbs-core）。
2. 最后回复：给出产物路径、TOBE 状态、输出模式与主要设计决策清单。
"""

CASE_EXPECTED = """产出 .sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md，且：

- 按 tobe-output-template.md 的 9 个一级章节组织（需求背景/外部依赖/整体方案/
  模块详细方案/对外接口/数据库表设计/受影响模块与交互/关键契约清单/附录三方件约束）。
- 不暴露 ASIS 过程性内容（证据编号表、检索过程、追踪矩阵等）；引用 ASIS 事实用
  结论编号（A1–A16 范围内）建立追踪。
- 不含测试用例编号、AICoding 任务拆分、大段可实现代码（TOBE 职责禁区）。
- 承接 ASIS 已查明的现状契约标识符（如 SUPPORTED_ALGORITHMS、auth_value、
  validate_and_derive_alg、BearerTokenVerifier），不概括丢失。
- 含 TOBE 状态字段（完成/部分完成/阻塞）。

依据：module-tobe-design SKILL.md 成果物协作规则、职责边界、§4.1 大纲要求、阻塞规则。
"""

CASE_GRADERS = [
    {
        "id": "tobe-assert",
        "type": "command",
        "name": "TOBE 说明书黑盒断言（契约路径/9章大纲/过程隔离/职责禁区/契约保真）",
        "command": r"python C:\tmp\ctx5tb\assert_tobe.py",
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
                "id": "sr1-rbcore-tobe",
                "name": "SR-1 rbs-core 模块 TOBE 详细设计",
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
        r"C:\tmp\ctx4gate\original-requirement.md",
        r"C:\tmp\ctx4gate\SR-design.md",
        r"C:\tmp\ctx5aa\fixture\software_architecture.md",
        os.path.join(STAGE, "fixture", "详细设计上下文.md"),
        os.path.join(STAGE, "preflight_tobe.py"),
        os.path.join(STAGE, "assert_tobe.py"),
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
        print("nothing to do (pass --post or --dry-run)")
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
    print(json.dumps(exp, ensure_ascii=False)[:800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
