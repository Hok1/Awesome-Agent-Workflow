#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup 前置校验：module-design-gate 测评夹具就位。

用法：python preflight_gate.py clean | defect
"""
import hashlib
import os
import sys

BASE = {
    os.path.join(".sdd", "SR-1", "original-requirement.md"): "f092a58dcb5e4c7c4bb9ee8cd2bd3817d9d51549",
    os.path.join(".sdd", "SR-1", "SR-design.md"): "dae0b2a9aea7c97421a075b9c0be3e7b5190b54c",
    os.path.join(".sdd", "software_architecture.md"): "a1f1226fca13c9b823083113a6c845e0e6025dc5",
    os.path.join(".sdd", "SR-1", "AR-1", "AR-clarify.md"): "6d6ef0b0ef28c68d8f8bc9631d175f3a9c1d58d7",
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", ".context", "详细设计上下文.md"):
        "36577b460f1b4c23c55b5cce0915c369922199a9",
}
CLEAN = {
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", "模块详细设计说明书.md"):
        "f409b788cb6872e8d0bdcd532cc6f74ee5140729",
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", "模块测试用例设计.md"):
        "fbd4353d8b24a891738123639c730e3524ba2b4a",
}
DEFECT = {
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", "模块详细设计说明书.md"):
        "37078038bbe27a7a6eafe0249e8c5f4800be2068",
    os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", "模块测试用例设计.md"):
        "0415472918dfd1082e37fd76e0914ce8e73877fc",
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("clean", "defect"):
        print("PREFLIGHT-FAIL: 用法 python preflight_gate.py clean|defect")
        return 2
    expected = dict(BASE)
    expected.update(DEFECT if sys.argv[1] == "defect" else CLEAN)
    for path, want in expected.items():
        if not os.path.isfile(path):
            print("PREFLIGHT-FAIL: 夹具缺失 " + path)
            return 1
        got = hashlib.sha1(open(path, "rb").read()).hexdigest()
        if got != want:
            print("PREFLIGHT-FAIL: %s sha1=%s, 期望 %s" % (path, got[:12], want[:12]))
            return 1
    if sys.argv[1] == "defect":
        spec = open(os.path.join(".sdd", "SR-1", "AR-1", "rbs-core", "模块详细设计说明书.md"),
                    encoding="utf-8").read()
        d5 = [l for l in spec.splitlines() if l.startswith("| D5 ")]
        if not d5 or "待定" not in d5[0]:
            print("PREFLIGHT-FAIL: defect 夹具的 D5 缺陷未植入")
            return 1
        print("PREFLIGHT-OK: defect 夹具就位（D5 依据=待定 已确认植入）")
    else:
        print("PREFLIGHT-OK: clean 夹具就位")
    return 0


if __name__ == "__main__":
    sys.exit(main())
