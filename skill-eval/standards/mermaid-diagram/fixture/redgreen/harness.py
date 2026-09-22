#!/usr/bin/env python3
"""assert_mermaid.py 红绿验证：绿夹具必须通过，红夹具必须在预期条款上失败。

每个用例一个目录：<cases>/<name>/docs/SM2-密钥生命周期-图.md，
以该目录为 cwd 运行 assert_mermaid.py，MM_SKILL_DIR 指向被测 skill。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
ASSERT = ROOT.parent / "assert_mermaid.py"
SKILL_DIR = Path(r"C:\code\workspace\Awesome-Agent-Workflow\skills\mermaid-diagram")
DOC_REL = Path("docs") / "SM2-密钥生命周期-图.md"

GREEN_STATE = """stateDiagram-v2
    生成 : 密钥已生成
    启用 : 可用于签名
    轮换 : 新版本替换旧版本
    吊销 : 主动失效
    泄露 : 私钥疑似暴露
    销毁 : 安全擦除
    [*] --> 生成
    生成 --> 启用 : 首次登记
    启用 --> 轮换 : 到达轮换周期
    轮换 --> 启用 : 新密钥启用
    启用 --> 泄露 : 发现泄露
    泄露 --> 吊销 : 应急处置
    吊销 --> 销毁 : 留存期满
    销毁 --> [*]
"""

GREEN_SEQ = """sequenceDiagram
    participant C as 客户端
    participant S as 签名服务
    participant K as 密钥存储
    C->>S: 请求轮换
    S->>K: 生成新 SM2 密钥对
    K-->>S: 新公钥
    S-->>C: 轮换完成
"""


def doc(*blocks: str, prose: str = "# SM2 密钥生命周期图\n") -> str:
    body = "\n".join(f"```mermaid\n{block}\n```" for block in blocks)
    return f"{prose}\n{body}\n"


CASE_LIST: list[dict] = [
    {
        "name": "green",
        "expect": 0,
        "doc": doc(GREEN_STATE, GREEN_SEQ),
    },
    {
        "name": "red-missing-file",
        "expect": 1,
        "doc": None,
        "want": "产物文件不存在",
    },
    {
        "name": "red-no-mermaid-block",
        "expect": 1,
        "doc": "# SM2 密钥生命周期图\n\n这里只有文字，没有任何代码块。\n",
        "want": "没有任何 ```mermaid 代码块",
    },
    {
        "name": "red-syntax-error",
        "expect": 1,
        "doc": doc(GREEN_STATE.replace("[*] --> 生成", "[*] --->>> 生成"), GREEN_SEQ),
        "want": "离线校验器未通过",
    },
    {
        "name": "red-no-state-diagram",
        "expect": 1,
        "doc": doc(
            "flowchart LR\n    生成 --> 启用 --> 轮换 --> 吊销 --> 泄露 --> 销毁\n",
            GREEN_SEQ,
        ),
        "want": "缺少 stateDiagram-v2",
    },
    {
        "name": "red-too-few-transitions",
        "expect": 1,
        "doc": doc(
            """stateDiagram-v2
    生成 : 密钥已生成
    启用 : 可用于签名
    轮换 : 新版本替换旧版本
    吊销 : 主动失效
    泄露 : 私钥疑似暴露
    销毁 : 安全擦除
    [*] --> 生成
    生成 --> 启用
    启用 --> 销毁
""",
            GREEN_SEQ,
        ),
        "want": "条转换",
    },
    {
        "name": "red-too-few-states",
        "expect": 1,
        "doc": doc(
            """stateDiagram-v2
    生成 : 密钥已生成
    启用 : 可用于签名
    销毁 : 安全擦除
    [*] --> 生成
    生成 --> 启用
    启用 --> 销毁
    销毁 --> [*]
""",
            GREEN_SEQ,
        ),
        "want": "只声明了",
    },
    {
        "name": "red-missing-keyword",
        "expect": 1,
        "doc": doc(GREEN_STATE.replace("吊销 : 主动失效", "停用 : 主动失效").replace("吊销", "停用"), GREEN_SEQ),
        "want": "缺少关键节点",
    },
    {
        "name": "red-missing-leak-path",
        "expect": 1,
        "doc": doc(GREEN_STATE.replace("泄露 : 私钥疑似暴露", "冻结 : 临时冻结").replace("泄露", "冻结"), GREEN_SEQ),
        "want": "缺少「泄露」",
    },
    {
        "name": "red-invented-identifier",
        "expect": 1,
        "doc": doc(GREEN_STATE, GREEN_SEQ + "\n", "flowchart LR\n    轮换 --> 导出私钥\n    导出私钥 --> 执行 exportPrivateKey()\n"),
        "want": "私有标识符",
    },
    {
        "name": "red-no-sequence",
        "expect": 1,
        "doc": doc(GREEN_STATE),
        "want": "缺少 sequenceDiagram",
    },
    {
        "name": "red-duplicate-sequence",
        "expect": 1,
        "doc": doc(GREEN_STATE, GREEN_SEQ, GREEN_SEQ, GREEN_SEQ),
        "want": "重复表达同一关系",
    },
    {
        "name": "red-stray-diagram-type",
        "expect": 1,
        "doc": doc(GREEN_STATE, GREEN_SEQ, "pie title 占比\n    \"生成\" : 30\n    \"销毁\" : 70\n"),
        "want": "无关或自造的图型",
    },
]


def run_case(case: dict) -> tuple[bool, str]:
    case_dir = CASES / case["name"]
    if case_dir.exists():
        shutil.rmtree(case_dir)
    (case_dir / "docs").mkdir(parents=True)
    if case["doc"] is not None:
        (case_dir / DOC_REL).write_text(case["doc"], encoding="utf-8")

    env = os.environ.copy()
    env["MM_SKILL_DIR"] = str(SKILL_DIR)
    result = subprocess.run(
        [sys.executable, str(ASSERT)],
        cwd=case_dir,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    output = result.stdout + result.stderr
    ok = result.returncode == case["expect"]
    detail = ""
    if ok and case["expect"] == 1:
        want = case.get("want", "")
        ok = want in output
        detail = f"命中条款[{want}]" if ok else f"退出码正确但未命中条款[{want}]"
    elif ok:
        detail = "MERMAID-ASSERT-PASS"
    else:
        detail = f"期望退出码 {case['expect']} 实得 {result.returncode}"
    return ok, f"{detail} | out={output.strip()[-400:]}"


def main() -> int:
    mismatches = 0
    for case in CASE_LIST:
        ok, detail = run_case(case)
        mark = "OK " if ok else "BAD"
        print(f"[{mark}] {case['name']}: {detail}")
        if not ok:
            mismatches += 1
    print(f"\n共 {len(CASE_LIST)} 用例，不符预期 {mismatches} 个")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
