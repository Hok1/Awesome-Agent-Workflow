#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造并提交 module-asis-analysis 测评套件（正向/反向各一个 suite），然后启动实验。

正向 with-arch：.sdd/software_architecture.md 就位，期望完整 ASIS context。
反向 no-arch：刻意无架构文档，期望 fail-closed（中断 + 阻塞标记）。

用法：
    python build_and_run.py --dry-run --variant with-arch
    python build_and_run.py --post --variant with-arch
    python build_and_run.py --post --variant no-arch
"""
import argparse
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:18110/api/v1"
RBS = r"C:\code\workspace\globaltrustauthority-rbs"
AAW = r"C:\code\workspace\Awesome-Agent-Workflow"
SKILL = os.path.join(AAW, "skills", "module-asis-analysis")
STAGE = r"C:\tmp\ctx5aa"

EXP_PROFILE = {
    "schema_version": 2,
    "name": "chrys-deepseek-asis-v1",
    "runner_provider": "chrys",
    "runner_model": "d3623a0e450d",
    "runner_reasoning_effort": "high",
    "judge_provider": "chrys",
    "judge_model": "d3623a0e450d",
    "judge_reasoning_effort": "high",
    "timeout_seconds": 5400,
    "network": False,
    "allowed_mcp_servers": [],
}

COMMON_COMMANDS = [
    r"cmd /c mkdir .sdd\SR-1",
    r'cmd /c copy /Y "C:\tmp\ctx4gate\original-requirement.md" ".sdd\SR-1\original-requirement.md"',
    r'cmd /c copy /Y "C:\tmp\ctx4gate\SR-design.md" ".sdd\SR-1\SR-design.md"',
]

CASE_INPUT = """你使用 module-asis-analysis skill，对目标模块做 SR-1 需求的 ASIS 现状分析。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不要修改）】
- 原始需求：.sdd/SR-1/original-requirement.md
- 上游 SR 设计：.sdd/SR-1/SR-design.md（SM2 接入的总体设计，本次 ASIS 的需求上下文）

【本次分析任务】
- 目标模块：rbs-core（rbs/core/）
- 分析切片：SR-1 中 SM2 用户认证与公钥登记相关部分——现有验签入口、算法分派、
  用户公钥登记链路、配置与测试现状
- SR=SR-1，AR=AR-1（SM2 用户认证），模块组名=rbs-core

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过，
   不要回调 aaw-workflow；执行中需要用户或上游确认的问题，按 skill 规定处理，
   不要等待回答。
2. 本环境无法启动 SubAgent——按 skill 对应该情形的规定处理并留痕。
3. 本环境不提供任何 MCP 工具。网络不可用。
4. 严格按 skill 正文规定的阶段流水线与产物契约执行。

【输出要求】
1. 按 skill 的产物契约产出到对应路径（SR=SR-1，AR=AR-1，模块组名=rbs-core）。
2. 最后回复：给出产物路径、整体状态、主要结论与阻塞/待确认项清单。
"""

CASE_EXPECTED_POS = """产出 .sdd/SR-1/AR-1/rbs-core/.context/详细设计上下文.md，且：

- 含 C1–C8 全部固定目录标题（无内容的章节保留标题并写明原因）。
- C2 模块边界确认标记为「declared by software_architecture.md」——边界只能来自
  .sdd/software_architecture.md，不得由代码结构推断。
- 结论有稳定编号（A1、A2……），证据有编号（E1、E2……）且可在 C7 证据索引反查。
- 产物引用的代码路径（rbs/core/...、rbs/rest/... 等）在仓库中真实存在。
- 未创建《模块详细设计说明书.md》（ASIS 阶段禁止）。
- C3 不含「建议采用」「可以复用」「应新增」等 TOBE 拍板表述（实现方案只能记为
  「TOBE 决策输入」）。

依据：module-asis-analysis SKILL.md 模块边界规则、阶段流水线、职责边界与质量标准。
"""

CASE_EXPECTED_NEG = """本用例刻意不提供 .sdd/software_architecture.md。skill 必须 fail-closed：

- 立即中断 ASIS，不得用代码结构、README 或目录布局推断模块边界。
- 若产出 .context/详细设计上下文.md，其中必须显式标记阻塞
  （blocked / ASIS 阻塞 / 状态：阻塞 / 立即中断），且不得声明确定的模块边界；
  不产出任何文件（中断无残留）同样合规。
- 任何情况下不得创建《模块详细设计说明书.md》。
- 不得把分析写到契约外路径伪装成合规产出。

依据：module-asis-analysis SKILL.md 模块边界规则第 2 条与「阻塞与降级输出」。
"""


def build_payload(variant: str) -> dict:
    if variant == "with-arch":
        setup_commands = COMMON_COMMANDS + [
            r'cmd /c copy /Y "%s\fixture\software_architecture.md" ".sdd\software_architecture.md"' % STAGE,
            r'cmd /c copy /Y "%s\preflight_asis.py" ".sdd\SR-1\preflight_asis.py"' % STAGE,
        ]
        preflight = [r"python .sdd\SR-1\preflight_asis.py with-arch"]
        # 判据脚本放在 workspace 之外，被测对象看不到——断言条款不得泄露
        grader_command = r"python C:\tmp\ctx5aa\assert_asis.py"
        expected = CASE_EXPECTED_POS
        case_id = "sr1-rbscore-asis"
        case_name = "SR-1 rbs-core 模块 ASIS 现状分析（有架构基线）"
        suite_name = "module-asis-analysis-SR1-rbcore-eval-v3"
    else:
        setup_commands = COMMON_COMMANDS + [
            r'cmd /c copy /Y "%s\preflight_asis.py" ".sdd\SR-1\preflight_asis.py"' % STAGE,
        ]
        preflight = [r"python .sdd\SR-1\preflight_asis.py no-arch"]
        grader_command = r"python C:\tmp\ctx5aa\assert_asis_blocked.py"
        expected = CASE_EXPECTED_NEG
        case_id = "sr1-rbscore-asis-blocked"
        case_name = "SR-1 rbs-core 模块 ASIS（无架构基线，期望 fail-closed）"
        suite_name = "module-asis-analysis-noarch-block-eval"

    return {
        "name": suite_name,
        "project_path": RBS,
        "skill_path": SKILL,
        "setup": {
            "commands": setup_commands,
            "preflight": preflight,
            "network": False,
            "timeout_seconds": 900,
        },
        "cases": [
            {
                "id": case_id,
                "name": case_name,
                "input": CASE_INPUT,
                "expected": expected,
                "weight": 1,
                "agent_context": "",
                "max_turns": 20,
                "graders": [
                    {
                        "id": "asis-assert",
                        "type": "command",
                        "name": "ASIS 产物黑盒断言",
                        "command": grader_command,
                        "weight": 100,
                        "hard_gate": False,
                        "timeout_seconds": 120,
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
    ap.add_argument("--variant", required=True, choices=["with-arch", "no-arch"])
    ap.add_argument("--mode", default="quick", choices=["quick", "formal"])
    args = ap.parse_args()

    payload = build_payload(args.variant)

    staged = [
        r"C:\tmp\ctx4gate\original-requirement.md",
        r"C:\tmp\ctx4gate\SR-design.md",
        os.path.join(STAGE, "preflight_asis.py"),
        os.path.join(STAGE, "assert_asis.py" if args.variant == "with-arch" else "assert_asis_blocked.py"),
    ]
    if args.variant == "with-arch":
        staged.append(os.path.join(STAGE, "fixture", "software_architecture.md"))
    for p in staged:
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
