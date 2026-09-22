#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup 前置校验：确认夹具已就位、node 可用于离线校验。

跑在 base 上（被评仓库的克隆），只用外部手段读文件，不 import 被测工程源码。
注意：preflight 先于 skill 安装执行，不能校验 .aaw-eval/skills 下的内容。
"""
import hashlib
import os
import shutil
import sys

EXPECTED = {
    "key-lifecycle-context.md": "2e6289efe9e7a801809f389604d01e69a15b79e4",
    "original-requirement.md": "f092a58dcb5e4c7c4bb9ee8cd2bd3817d9d51549",
}


def main() -> int:
    for name, want in EXPECTED.items():
        path = os.path.join(".sdd", "SR-1", name)
        if not os.path.isfile(path):
            print("PREFLIGHT-FAIL: 夹具缺失 " + path)
            return 1
        got = hashlib.sha1(open(path, "rb").read()).hexdigest()
        if want is not None and got != want:
            print("PREFLIGHT-FAIL: %s sha1=%s, 期望 %s" % (name, got[:12], want[:12]))
            return 1

    text = open(os.path.join(".sdd", "SR-1", "key-lifecycle-context.md"),
                encoding="utf-8").read()
    # 夹具只给事实、不得泄露图型答案（图型选择是被测能力）
    for leaked in ("stateDiagram", "sequenceDiagram", "flowchart", "classDiagram", "erDiagram"):
        if leaked.lower() in text.lower():
            print("PREFLIGHT-FAIL: 夹具泄露图型答案 " + leaked)
            return 1
    for fact in ("生成", "启用", "轮换", "吊销", "泄露", "销毁"):
        if fact not in text:
            print("PREFLIGHT-FAIL: 夹具缺少业务事实 " + fact)
            return 1

    if shutil.which("node") is None:
        print("PREFLIGHT-FAIL: node 不在 PATH，离线校验器无法运行")
        return 1
    print("PREFLIGHT-OK: 夹具就位且未泄露图型, node=" + shutil.which("node"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
