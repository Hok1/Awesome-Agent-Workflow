#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造并提交 dev-design-gate 测评套件（正向 clean / 反向 defect），然后启动实验。"""
import argparse
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:18110/api/v1"
RBS = r"C:\code\workspace\globaltrustauthority-rbs"
AAW = r"C:\code\workspace\Awesome-Agent-Workflow"
SKILL = os.path.join(AAW, "skills", "dev-design-gate")
STAGE = r"C:\tmp\ctx5dg2"

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

CASE_INPUT = """你使用 dev-design-gate skill，对 SR-2 的轻量设计执行准入门禁。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不得修改）】
- 轻量设计：.sdd/SR-2/dev-design.md
- 测试设计：.sdd/SR-2/test-design.md
- 需求原文：.sdd/SR-2/requirement.md

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过；
   需要用户确认的问题按 skill 规定处理，不要等待回答。
2. 本环境不提供任何 MCP 工具。网络不可用。
3. 严格按 skill 正文规定的 3 项准入检查、结论判定与报告骨架执行；
   本环境无 aaw CLI——data_schema 回传跳过，只在报告中如实给出统计数字。

【输出要求】
1. 按 skill 的产物契约把门禁报告写入对应路径（SR=SR-2）。
2. 最后回复：给出报告路径、结论、建议、未达标项清单。
"""

CASE_EXPECTED_CLEAN = """两份输入为本测评手写的合规轻量文档（无植入缺陷）。门禁应：

- 把报告写入 .sdd/SR-2/.context/dev-design-gate.md（references/gate-report.md 骨架）。
- 结论为 通过/不通过/阻塞 之一；建议为 可进入任务拆分/修正后重新门禁/阻塞 之一。
- 3 项准入检查（决策已收敛/代码论断可回溯/契约与验收可执行）逐项判定。
- 不修改任何输入文件；结论为通过时统计三项计数全 0。

依据：dev-design-gate SKILL.md 3 项准入检查、结论判定、报告边界。
"""

CASE_EXPECTED_DEFECT = """输入被植入两处有明确判定条款的缺陷：

1. dev-design.md 方案中「加法溢出的处理可选 checked_add 转错或直接 wrapping，待定，
   看情况再定」——决策未收敛（检查项 1）。
2. test-design.md 覆盖矩阵缺失验收标准 A3 行——契约与验收不可执行（检查项 3）。

门禁应：结论为「不通过」；需整改项命中检查项 1 与检查项 3；形式契约同正向。

依据：dev-design-gate SKILL.md 3 项准入检查表、结论判定「任一检查项未达标……不得通过」。
"""


def build_payload(variant: str) -> dict:
    defect = variant == "defect"
    prefix = "defect-" if defect else ""
    return {
        "name": "dev-design-gate-SR2-%s-eval" % variant,
        "project_path": RBS,
        "skill_path": SKILL,
        "setup": {
            "commands": [
                r"cmd /c mkdir .sdd\SR-2\.context",
                r'cmd /c copy /Y "%s\fixture\requirement.md" ".sdd\SR-2\requirement.md"' % STAGE,
                r'cmd /c copy /Y "%s\fixture\%sdev-design.md" ".sdd\SR-2\dev-design.md"' % (STAGE, prefix),
                r'cmd /c copy /Y "%s\fixture\%stest-design.md" ".sdd\SR-2\test-design.md"' % (STAGE, prefix),
                r'cmd /c copy /Y "%s\preflight_devgate.py" ".sdd\SR-2\preflight_devgate.py"' % STAGE,
            ],
            "preflight": [r"python .sdd\SR-2\preflight_devgate.py %s" % variant],
            "network": False,
            "timeout_seconds": 900,
        },
        "cases": [
            {
                "id": "sr2-devgate-%s" % variant,
                "name": "SR-2 轻量设计门禁（%s）" % ("带缺陷" if defect else "干净"),
                "input": CASE_INPUT,
                "expected": CASE_EXPECTED_DEFECT if defect else CASE_EXPECTED_CLEAN,
                "weight": 1,
                "agent_context": "",
                "max_turns": 12,
                "graders": [
                    {
                        "id": "devgate-assert",
                        "type": "command",
                        "name": "轻量门禁黑盒断言（形式契约%s）" % ("+缺陷命中" if defect else ""),
                        "command": r"python C:\tmp\ctx5dg2\assert_devgate_defect.py" if defect else r"python C:\tmp\ctx5dg2\assert_devgate_common.py",
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
    for name in ("requirement.md", prefix + "dev-design.md", prefix + "test-design.md"):
        if not os.path.isfile(os.path.join(STAGE, "fixture", name)):
            print("MISSING staged file: " + name)
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
