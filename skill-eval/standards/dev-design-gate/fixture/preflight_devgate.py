#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup 前置校验：dev-design-gate 测评夹具就位。

用法：python preflight_devgate.py clean | defect
"""
import hashlib
import os
import sys

REQ = {os.path.join(".sdd", "SR-2", "requirement.md"): "6cfad3c618aab06470ab3613ec1dea21a4bc8cde"}
CLEAN = {
    os.path.join(".sdd", "SR-2", "dev-design.md"): "14c919fdfa68069bda06af0cf08be22a24aa71c1",
    os.path.join(".sdd", "SR-2", "test-design.md"): "d2a4185d9a2b16f8ebc7a1a2954634c379061b77",
}
DEFECT = {
    os.path.join(".sdd", "SR-2", "dev-design.md"): "629aa2007841f83a39e86a4127e7676bd361dd61",
    os.path.join(".sdd", "SR-2", "test-design.md"): "d58d9a752fbd31203468e11914caf76c70ec2ab8",
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("clean", "defect"):
        print("PREFLIGHT-FAIL: 用法 python preflight_devgate.py clean|defect")
        return 2
    expected = dict(REQ)
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
        design = open(os.path.join(".sdd", "SR-2", "dev-design.md"), encoding="utf-8").read()
        if "待定，看情况再定" not in design:
            print("PREFLIGHT-FAIL: defect 夹具的方案待定缺陷未植入")
            return 1
        test = open(os.path.join(".sdd", "SR-2", "test-design.md"), encoding="utf-8").read()
        if "A3 非法输入拒绝" in test:
            print("PREFLIGHT-FAIL: defect 夹具的覆盖矩阵漏项缺陷未植入（A3 仍在）")
            return 1
        print("PREFLIGHT-OK: defect 夹具就位（缺陷已确认）")
    else:
        print("PREFLIGHT-OK: clean 夹具就位")
    return 0


if __name__ == "__main__":
    sys.exit(main())
