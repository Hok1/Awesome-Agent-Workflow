#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造并提交 effective-document-writing 测评套件，然后启动实验。"""
import argparse
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:18110/api/v1"
RBS = r"C:\code\workspace\globaltrustauthority-rbs"
AAW = r"C:\code\workspace\Awesome-Agent-Workflow"
SKILL = os.path.join(AAW, "skills", "effective-document-writing")
STAGE = r"C:\tmp\ctx5dw"

SUITE_NAME = "effective-document-writing-SM2-eval"
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
    "commands": [
        r"cmd /c mkdir .sdd",
        r'cmd /c copy /Y "%s\fixture\draft.md" ".sdd\draft.md"' % STAGE,
    ],
    "preflight": [],
    "network": False,
    "timeout_seconds": 900,
}

CASE_INPUT = """你使用 effective-document-writing skill，把一份评审讨论草稿重写为面向交付的设计说明。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不得修改）】
- 草稿：.sdd/draft.md（一份带黑话与对话痕迹的讨论纪要，其中只有一条真实方案要点）

【任务】
把草稿重写为正式设计说明，写入 docs/SM2-auth-design.md。
- 读者：需要评审该方案并据此开发的工程师。
- 草稿中的方案要点需要落成明确结论；黑话、空泛表态、对话与生成过程痕迹不得带入。
- 草稿之外的未证实细节不得自行补全；无依据的内容删除或标为待确认。

【本次执行方式】
1. 无头执行，没有人类在旁，不要向用户提问。
2. 严格按 skill 正文的写作原则与交付前检查执行。

【输出要求】
1. 产出 docs/SM2-auth-design.md。
2. 最后回复：给出文档路径与你在重写中删除/改写的要点清单。
"""

CASE_EXPECTED = """产出 docs/SM2-auth-design.md，且：

- 不含黑话（赋能/抓手/拉通/对齐颗粒度）与空泛表态（显著提升/全面保障/充分考虑/
  持续优化）。
- 不含对话与生成过程痕迹（根据你的要求/如前所述/经过讨论/提示词/聊天记录）。
- 草稿的唯一的真实方案要点（authn/sm2 模块）落成明确结论；结论/依据/取舍三要素在场。
- 原稿 .sdd/draft.md 不被修改。

依据：effective-document-writing SKILL.md「控制语言和信息密度」「隔离对话和修改过程」
「确定写作任务」。
"""

CASE_GRADERS = [
    {
        "id": "docwrite-assert",
        "type": "command",
        "name": "文档重写黑盒断言（禁词/对话痕迹/三要素/原稿不动）",
        "command": r"python C:\tmp\ctx5dw\assert_docwrite.py",
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
                "id": "sm2-doc-rewrite",
                "name": "SM2 讨论纪要重写为设计说明",
                "input": CASE_INPUT,
                "expected": CASE_EXPECTED,
                "weight": 1,
                "agent_context": "",
                "max_turns": 8,
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
    if not os.path.isfile(os.path.join(STAGE, "fixture", "draft.md")):
        print("MISSING fixture")
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
