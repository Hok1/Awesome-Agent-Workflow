#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup 前置校验：task-dev 测评夹具就位 + Rust 工具链可用。"""
import hashlib
import os
import shutil
import sys

EXPECTED = {
    os.path.join(".sdd", "SR-1", "original-requirement.md"): "f092a58dcb5e4c7c4bb9ee8cd2bd3817d9d51549",
    os.path.join(".sdd", "software_architecture.md"): "a1f1226fca13c9b823083113a6c845e0e6025dc5",
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", "模块详细设计说明书.md"):
        "f409b788cb6872e8d0bdcd532cc6f74ee5140729",
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", "模块测试用例设计.md"):
        "fbd4353d8b24a891738123639c730e3524ba2b4a",
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", ".context", "模块设计门禁结果.md"):
        "cb9fa1a8e42bf59306561ae25cb3705ac0ac6fbf",
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
    if shutil.which("cargo") is None:
        print("PREFLIGHT-FAIL: cargo 不在 PATH，task-dev 的实现验证无法执行")
        return 1
    print("PREFLIGHT-OK: 5 份夹具就位, cargo=" + shutil.which("cargo"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
