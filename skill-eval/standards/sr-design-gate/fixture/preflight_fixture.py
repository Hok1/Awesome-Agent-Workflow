#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup 前置校验：确认夹具已就位且仍然带有预期的 P0 缺陷。

跑在 base 上（被评仓库的克隆），只用外部手段读文件，不 import 被测工程源码。
"""
import hashlib
import io
import os
import sys

EXPECTED = {
    "SR-design.md": "dae0b2a9aea7c97421a075b9c0be3e7b5190b54c",
    "original-requirement.md": "f092a58dcb5e4c7c4bb9ee8cd2bd3817d9d51549",
}


def main() -> int:
    for name, want in EXPECTED.items():
        path = os.path.join(".sdd", "SR-1", name)
        if not os.path.isfile(path):
            print("PREFLIGHT-FAIL: 夹具缺失 " + path)
            return 1
        got = hashlib.sha1(open(path, "rb").read()).hexdigest()
        if got != want:
            print("PREFLIGHT-FAIL: %s sha1=%s, 期望 %s" % (name, got[:12], want[:12]))
            return 1

    text = io.open(os.path.join(".sdd", "SR-1", "SR-design.md"),
                   encoding="utf-8").read()
    # 夹具约 43,117 字符（65,919 字节）。用字符数量级校验，防截断。
    if len(text) < 40000:
        print("PREFLIGHT-FAIL: 夹具疑似被截断, %d 字符" % len(text))
        return 1
    # 植入的 P0：存在私钥导出接口，且全文没有任何导出策略声明
    if "--export-private-key" not in text:
        print("PREFLIGHT-FAIL: 夹具未植入私钥导出接口（预期的 P0 缺失）")
        return 1
    if "导出策略" in text:
        print("PREFLIGHT-FAIL: 夹具意外声明了导出策略，P0 不再成立")
        return 1
    print("PREFLIGHT-OK: 夹具就位, %d 字符, 私钥导出接口无导出策略(P0)" % len(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
