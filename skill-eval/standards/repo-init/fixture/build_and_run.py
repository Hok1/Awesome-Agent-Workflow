#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造并提交 repo-init 测评套件，然后启动实验。"""
import argparse
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:18110/api/v1"
RBS = r"C:\code\workspace\globaltrustauthority-rbs"
AAW = r"C:\code\workspace\Awesome-Agent-Workflow"
SKILL = os.path.join(AAW, "skills", "repo-init")
STAGE = r"C:\tmp\ctx5ri"

SUITE_NAME = "repo-init-rbs-eval"
EXP_PROFILE = {
    "schema_version": 2,
    "name": "chrys-deepseek-official-v1",
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
    # RBS 仓无 .sdd/、无 AGENTS.md——repo-init 的全新初始化场景
    "commands": [],
    "preflight": [],
    "network": False,
    "timeout_seconds": 900,
}

CASE_INPUT = """你使用 repo-init skill，对当前代码仓执行 SDD 初始化。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过；
   需要用户确认的问题按 skill 规定处理。
2. 本环境无法启动 SubAgent——各 Phase 的 subagent 派发由你自行完成同等只读勘察与写作。
3. 本环境不提供任何 MCP 工具。网络不可用。
4. 用户确认环节（Phase 7）：输出规定的提醒文本后即视为本轮结束，不等待答复。
5. 本环境无 aaw CLI——跳过工作单 commands 调用。
6. 严格按 skill 正文规定的 Phase 顺序与产物契约执行。

【输出要求】
1. 按 skill 规定产出 .sdd/ 结构与软件架构文档、AGENTS.md。
2. 最后回复：给出产物清单、识别的模块列表、以及 Phase 7 提醒文本。
"""

CASE_EXPECTED = """产出：

- .sdd/software_architecture.md：模板固定章节（文档元数据/目录/系统概览/模块清单）
  保留；豁免区（目录/1.2/1.3）之外的 {{}} 占位符全部填充；模块职责表落到真实
  代码路径（rbs/core、rbs/rest、tools 等），且产物引用的路径全部真实存在。
- AGENTS.md：识别 Rust 语言与 cargo 构建/测试命令。

依据：repo-init SKILL.md Phase 1-7 与 references/software_architecture.md 模板契约。
"""

CASE_GRADERS = [
    {
        "id": "repoinit-assert",
        "type": "command",
        "name": "repo-init 黑盒断言（架构文档/占位符清零/路径真实/AGENTS 识别）",
        "command": r"python C:\tmp\ctx5ri\assert_repoinit.py",
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
                "id": "rbs-repo-init",
                "name": "RBS 仓 SDD 初始化",
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
    if not os.path.isfile(os.path.join(STAGE, "assert_repoinit.py")):
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
