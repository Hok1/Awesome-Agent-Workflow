#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造并提交 mermaid-diagram 测评套件，然后启动实验。

夹具投递方式：setup.commands 把 C:\\tmp\\ctx5mm\\ 下的文件拷进 base 的 .sdd/SR-1/。
base 在 clone 后被 setup 修改、再 copytree 到每个 run 的工作区，故夹具对每个 run 可见。

关键设计：输入只给业务事实（key-lifecycle-context.md），不给图型答案——
图型选择是 mermaid-diagram 的被测能力（SKILL.md「## 选择图型」）。

用法：
    python build_and_run.py --dry-run     # 只打印 payload，不提交
    python build_and_run.py --post        # 提交 suite + 启动 experiment
"""
import argparse
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:18110/api/v1"
RBS = r"C:\code\workspace\globaltrustauthority-rbs"
AAW = r"C:\code\workspace\Awesome-Agent-Workflow"
SKILL = os.path.join(AAW, "skills", "mermaid-diagram")
STAGE = r"C:\tmp\ctx5mm"

SUITE_NAME = "mermaid-diagram-SR1-key-lifecycle-eval"
EXP_PROFILE = {
    "schema_version": 2,
    "name": "chrys-deepseek-mermaid-v1",
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

SETUP = {
    "commands": [
        r"cmd /c mkdir .sdd\SR-1",
        r'cmd /c copy /Y "%s\fixture\key-lifecycle-context.md" ".sdd\SR-1\key-lifecycle-context.md"' % STAGE,
        r'cmd /c copy /Y "C:\tmp\ctx4gate\original-requirement.md" ".sdd\SR-1\original-requirement.md"',
        r'cmd /c copy /Y "%s\assert_mermaid.py" ".sdd\SR-1\assert_mermaid.py"' % STAGE,
        r'cmd /c copy /Y "%s\preflight_fixture.py" ".sdd\SR-1\preflight_fixture.py"' % STAGE,
    ],
    "preflight": [
        r"python .sdd\SR-1\preflight_fixture.py",
    ],
    "network": False,
    "timeout_seconds": 900,
}

CASE_INPUT = """你使用 mermaid-diagram skill，为下面这个设计问题补充图表表达。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【背景】
SR-1 要求 RBS 支持国密 SM2（用户认证支持 SM2、验证 GTA 签发的 SM2 attestation token、
rbs-cli 生成 SM2 token）。SR 设计门禁判定当前设计在「敏感参数安全」维度未达标，依据之一是
用户 SM2 密钥的生命周期状态及合法转换未被设计表达。本次任务是为这一缺口补充图表，
供设计评审使用。

【输入（均已就位，直接读取，不要修改）】
- 原始需求：.sdd/SR-1/original-requirement.md
- 业务事实清单：.sdd/SR-1/key-lifecycle-context.md（密钥归属、登记、轮换、泄露处置、参与方）

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，没有人类在旁回答问题。不要向用户提问，不要等待确认。
2. 严格按 mermaid-diagram skill 正文执行：从评审问题出发选择图型，遵守编写规则与转义规则，
   交付前完成 skill 规定的编译验证。
3. 本环境网络不可用：不得调用 npx、包管理器或远程渲染服务。

【输出要求】
1. 把图表文档写入 docs/SM2-密钥生命周期-图.md。业务事实清单中的每条事实都应在图中有落点。
   图要回答的评审问题至少包括：密钥从产生到销毁经历哪些状态、什么条件下发生转换；
   轮换时各参与方按什么顺序交互。
2. 交付前按 skill 规定完成离线编译验证，并确认全部通过。
3. 最后回复：给出文档路径、每张图回答的评审问题，以及离线校验的退出码。
"""

CASE_EXPECTED = """文档 docs/SM2-密钥生命周期-图.md 存在，且其中全部 Mermaid 图通过 skill 自带校验器
（scripts/check_mermaid.py）的完全离线校验（退出码 0）。

图型与评审问题匹配：
- 密钥生命周期是状态转换问题，应以状态图表达，覆盖 生成/启用/轮换/吊销/泄露/销毁
  这组状态及其合法转换；泄露这条非主路径不得悬空（泄露后不得回到可用状态，吊销不可逆）。
- 轮换涉及 用户（rbs-cli）、RBS 管理员、RBS 服务 多方按时序的交互，应以时序图表达。

编写规则：
- 节点使用稳定的业务/模块/职责名称（如 用户、RBS 管理员、密钥存储），不得出现
  Foo() 形态的函数调用标识符。
- 不为同一关系重复画图（同类型图不堆砌）；不引入与评审问题无关的图型凑数。

依据：mermaid-diagram SKILL.md「## 选择图型」「## 编写规则」「## 编译验证」「## 完成条件」；
crypto-gate-checklist.md §3 的生命周期状态集合。
"""

CASE_GRADERS = [
    {
        "id": "mermaid-assert",
        "type": "command",
        "name": "图表产物黑盒断言（存在性/可编译/图型匹配/路径覆盖/无自造标识符）",
        "command": "python .sdd/SR-1/assert_mermaid.py",
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
                "id": "sr1-sm2-key-lifecycle",
                "name": "SR-1 用户 SM2 密钥生命周期配图",
                "input": CASE_INPUT,
                "expected": CASE_EXPECTED,
                "weight": 1,
                "agent_context": "",
                "max_turns": 10,
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
        os.path.join(STAGE, "fixture", "key-lifecycle-context.md"),
        r"C:\tmp\ctx4gate\original-requirement.md",
        os.path.join(STAGE, "assert_mermaid.py"),
        os.path.join(STAGE, "preflight_fixture.py"),
    ):
        if not os.path.isfile(p):
            print("MISSING staged file: " + p)
            return 2
    for c in SETUP["commands"] + SETUP["preflight"]:
        if len(c) > 4000:
            print("setup command too long (%d): %s" % (len(c), c[:80]))
            return 2
    print("setup commands max len = %d (limit 4000)"
          % max(len(c) for c in SETUP["commands"] + SETUP["preflight"]))
    print("cases=%d graders=%d" % (len(payload["cases"]), len(CASE_GRADERS)))

    if args.dry_run:
        open(os.path.join(STAGE, "payload-dry.json"), "w", encoding="utf-8", newline="\n").write(
            json.dumps(payload, ensure_ascii=False, indent=2))
        print("dry-run payload -> %s\\payload-dry.json" % STAGE)
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
    print(json.dumps(exp, ensure_ascii=False)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
