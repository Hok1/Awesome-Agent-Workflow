#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup 前置校验：module-asis-analysis 测评夹具就位。

用法：python preflight_asis.py with-arch | no-arch
  with-arch：正向用例，.sdd/software_architecture.md 必须存在且 sha1 匹配
  no-arch：  反向用例，.sdd/software_architecture.md 必须不存在
"""
import hashlib
import os
import sys

EXPECTED = {
    "original-requirement.md": "f092a58dcb5e4c7c4bb9ee8cd2bd3817d9d51549",
    "SR-design.md": "dae0b2a9aea7c97421a075b9c0be3e7b5190b54c",
}
ARCH_SHA1 = "a1f1226fca13c9b823083113a6c845e0e6025dc5"


def sha1(path: str) -> str:
    return hashlib.sha1(open(path, "rb").read()).hexdigest()


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("with-arch", "no-arch"):
        print("PREFLIGHT-FAIL: 用法 python preflight_asis.py with-arch|no-arch")
        return 2
    mode = sys.argv[1]

    for name, want in EXPECTED.items():
        path = os.path.join(".sdd", "SR-1", name)
        if not os.path.isfile(path):
            print("PREFLIGHT-FAIL: 夹具缺失 " + path)
            return 1
        got = sha1(path)
        if got != want:
            print("PREFLIGHT-FAIL: %s sha1=%s, 期望 %s" % (name, got[:12], want[:12]))
            return 1

    arch = os.path.join(".sdd", "software_architecture.md")
    if mode == "with-arch":
        if not os.path.isfile(arch):
            print("PREFLIGHT-FAIL: 正向用例缺少 .sdd/software_architecture.md")
            return 1
        got = sha1(arch)
        if got != ARCH_SHA1:
            print("PREFLIGHT-FAIL: 架构文档 sha1=%s, 期望 %s" % (got[:12], ARCH_SHA1[:12]))
            return 1
        print("PREFLIGHT-OK: with-arch 夹具就位")
    else:
        if os.path.isfile(arch):
            print("PREFLIGHT-FAIL: 反向用例要求无 .sdd/software_architecture.md")
            return 1
        print("PREFLIGHT-OK: no-arch 前提成立（架构文档不存在）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
