#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup 前置校验：module-tobe-design 测评夹具就位。

跑在 base 上（被评仓库的克隆），只用外部手段读文件，不 import 被测工程源码。
"""
import hashlib
import io
import os
import re
import sys

EXPECTED = {
    os.path.join(".sdd", "SR-1", "original-requirement.md"): "f092a58dcb5e4c7c4bb9ee8cd2bd3817d9d51549",
    os.path.join(".sdd", "SR-1", "SR-design.md"): "dae0b2a9aea7c97421a075b9c0be3e7b5190b54c",
    os.path.join(".sdd", "software_architecture.md"): "a1f1226fca13c9b823083113a6c845e0e6025dc5",
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", ".context", "详细设计上下文.md"):
        "5c6a158a1ea943659e99bab6c6ade5c6090c1532",
}


def main() -> int:
    for path, want in EXPECTED.items():
        if not os.path.isfile(path):
            print("PREFLIGHT-FAIL: 夹具缺失 " + path)
            return 1
        got = hashlib.sha1(open(path, "rb").read()).hexdigest()
        if got != want:
            print("PREFLIGHT-FAIL: %s sha1=%s, 期望 %s" % (path, got[:12], want[:12]))
            return 1

    # ASIS 输入必须真的含结论编号（否则 TOBE 无证据基础，用例前提不成立）
    ctx = io.open(
        os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", ".context", "详细设计上下文.md"),
        encoding="utf-8",
    ).read()
    conclusions = sorted(set(re.findall(r"\bA(\d+)\b", ctx)))
    if len(conclusions) < 10:
        print("PREFLIGHT-FAIL: ASIS 输入结论编号不足（%d 个），不构成有效 TOBE 输入" % len(conclusions))
        return 1
    print("PREFLIGHT-OK: 4 份夹具就位, ASIS 结论编号 %d 个" % len(conclusions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
