#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造并提交 module-design-gate 测评套件（正向 clean / 反向 defect），然后启动实验。

判据保密：断言脚本不进 workspace；task 不复述 skill 规则、不提示夹具是否有缺陷。
"""
import argparse
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:18110/api/v1"
RBS = r"C:\code\workspace\globaltrustauthority-rbs"
AAW = r"C:\code\workspace\Awesome-Agent-Workflow"
SKILL = os.path.join(AAW, "skills", "module-design-gate")
STAGE = r"C:\tmp\ctx5dg"

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

CASE_INPUT = """你使用 module-design-gate skill，对 rbs-core 模块的 SR-1/AR-1 设计三件套执行模块设计门禁。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不得修改）】
- 正式说明书：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md
- 测试设计：.sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md
- 详细设计上下文：.sdd/SR-1/AR-1/rbs-core/.context/详细设计上下文.md
- 上游反查基线：.sdd/SR-1/SR-design.md、.sdd/SR-1/AR-1/AR-clarify.md
- 原始需求：.sdd/SR-1/original-requirement.md

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过；
   需要用户或上游确认的问题，按 skill 规定处理，不要等待回答。
2. 本环境不提供任何 MCP 工具。网络不可用。
3. 严格按 skill 正文规定的强制工作步骤、八维度准入与结论/建议枚举执行。

【输出要求】
1. 按 skill 的产物契约把门禁结果写入对应路径（SR=SR-1，AR=AR-1，模块组名=rbs-core）。
2. 最后回复：给出结果路径、门禁结论、门禁建议、未达标维度清单。
"""

CASE_EXPECTED_CLEAN = """三件套为本链路真实合规产物（无植入缺陷）。门禁应：

- 把结果写入 .sdd/SR-1/AR-1/rbs-core/.context/模块设计门禁结果.md。
- 结论为 通过/不通过/阻塞 之一；建议为七值枚举之一，且与结论一致。
- 不修改任何输入文件。
- 报告中引用的 D/TC/A/E 编号必须能在对应输入中反查。

依据：module-design-gate SKILL.md 门禁结论、成果物协作规则、工作流程。
"""

CASE_EXPECTED_DEFECT = """三件套被植入两处有明确判定条款的缺陷：

1. 说明书 D5 决策的「设计依据摘要」为「待定」（影响实现的待定项未标为非阻断改进项）
   ——属「决策确定性」维度。
2. 测试设计存在概要用例 TC99（只写「补充单测覆盖异常场景」，无输入/前置/断言/建议位置）
   ——SKILL.md 明文「门禁必须判定验证闭环性不通过」。

门禁应：

- 结论为「不通过」，不得放行。
- 报告命中「决策确定性」与「验证闭环性」两个维度。
- 形式契约同正向（结果路径/枚举/一致性/输入不改写/编号可反查）。

依据：module-design-gate SKILL.md 维度表、成果物协作规则、门禁结论。
"""


def build_payload(variant: str) -> dict:
    defect = variant == "defect"
    prefix = "defect-" if defect else ""
    setup_commands = [
        r"cmd /c mkdir .sdd\SR-1\AR-1\rbs-core\.context",
        r'cmd /c copy /Y "C:\tmp\ctx4gate\original-requirement.md" ".sdd\SR-1\original-requirement.md"',
        r'cmd /c copy /Y "C:\tmp\ctx4gate\SR-design.md" ".sdd\SR-1\SR-design.md"',
        r'cmd /c copy /Y "C:\tmp\ctx5aa\fixture\software_architecture.md" ".sdd\software_architecture.md"',
        r'cmd /c copy /Y "%s\fixture\AR-clarify.md" ".sdd\SR-1\AR-1\AR-clarify.md"' % STAGE,
        r'cmd /c copy /Y "%s\fixture\%s模块详细设计说明书.md" ".sdd\SR-1\AR-1\rbs-core\模块详细设计说明书.md"' % (STAGE, prefix),
        r'cmd /c copy /Y "%s\fixture\%s模块测试用例设计.md" ".sdd\SR-1\AR-1\rbs-core\模块测试用例设计.md"' % (STAGE, prefix),
        r'cmd /c copy /Y "%s\fixture\详细设计上下文.md" ".sdd\SR-1\AR-1\rbs-core\.context\详细设计上下文.md"' % STAGE,
        r'cmd /c copy /Y "%s\preflight_gate.py" ".sdd\SR-1\preflight_gate.py"' % STAGE,
    ]
    return {
        "name": "module-design-gate-SR1-rbcore-%s-eval" % ("defect" if defect else "clean"),
        "project_path": RBS,
        "skill_path": SKILL,
        "setup": {
            "commands": setup_commands,
            "preflight": [r"python .sdd\SR-1\preflight_gate.py %s" % variant],
            "network": False,
            "timeout_seconds": 900,
        },
        "cases": [
            {
                "id": "sr1-rbcore-gate-%s" % variant,
                "name": "SR-1 rbs-core 模块设计门禁（%s）" % ("带缺陷三件套" if defect else "干净三件套"),
                "input": CASE_INPUT,
                "expected": CASE_EXPECTED_DEFECT if defect else CASE_EXPECTED_CLEAN,
                "weight": 1,
                "agent_context": "",
                "max_turns": 20,
                "graders": [
                    {
                        "id": "mdg-assert",
                        "type": "command",
                        "name": "模块门禁黑盒断言（形式契约%s）" % ("+缺陷命中" if defect else ""),
                        "command": r"python C:\tmp\ctx5dg\assert_gate_defect.py" if defect else r"python C:\tmp\ctx5dg\assert_gate_common.py",
                        "weight": 100,
                        "hard_gate": False,
                        "timeout_seconds": 180,
                    }
                ],
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
    ap.add_argument("--variant", required=True, choices=["clean", "defect"])
    ap.add_argument("--mode", default="quick", choices=["quick", "formal"])
    args = ap.parse_args()

    payload = build_payload(args.variant)
    prefix = "defect-" if args.variant == "defect" else ""
    for p in (
        os.path.join(STAGE, "fixture", prefix + "模块详细设计说明书.md"),
        os.path.join(STAGE, "fixture", prefix + "模块测试用例设计.md"),
        os.path.join(STAGE, "fixture", "详细设计上下文.md"),
        os.path.join(STAGE, "fixture", "AR-clarify.md"),
        os.path.join(STAGE, "assert_gate_common.py"),
        os.path.join(STAGE, "preflight_gate.py"),
    ):
        if not os.path.isfile(p):
            print("MISSING staged file: " + p)
            return 2

    if args.dry_run:
        out = os.path.join(STAGE, "payload-dry-%s.json" % args.variant)
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
