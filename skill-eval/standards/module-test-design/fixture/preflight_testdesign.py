#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup 前置校验：module-test-design 测评夹具就位。"""
import hashlib
import os
import sys

EXPECTED = {
    os.path.join(".sdd", "SR-1", "original-requirement.md"): "f092a58dcb5e4c7c4bb9ee8cd2bd3817d9d51549",
    os.path.join(".sdd", "software_architecture.md"): "a1f1226fca13c9b823083113a6c845e0e6025dc5",
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", "模块详细设计说明书.md"):
        "f409b788cb6872e8d0bdcd532cc6f74ee5140729",
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", ".context", "详细设计上下文.md"):
        "36577b460f1b4c23c55b5cce0915c369922199a9",
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
    print("PREFLIGHT-OK: 4 份夹具就位")
    return 0


if __name__ == "__main__":
    sys.exit(main())
