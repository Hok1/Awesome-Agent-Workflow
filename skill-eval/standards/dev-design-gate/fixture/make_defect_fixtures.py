#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 dev-design-gate 反向夹具：植入两处有明确判定条款的缺陷。

缺陷 1（检查项 1 决策已收敛）：方案中插入「待定」——出处：「方案是明确选择，
  不存在『可选/待定/看情况』」。
缺陷 2（检查项 3 契约与验收可执行）：test-design 覆盖矩阵删除 A3 行——出处：
  「覆盖矩阵覆盖全部验收标准与契约变更项，缺口已清零或已登记回流」。
"""
import sys
from pathlib import Path

FIX = Path(r"C:\tmp\ctx5dg2\fixture")


def main() -> int:
    design = (FIX / "dev-design.md").read_text(encoding="utf-8-sig")
    anchor = "加法溢出用 `checked_add` 转为同一错误语义）。"
    if anchor not in design:
        print("FAIL: 方案锚点不存在")
        return 1
    design = design.replace(
        anchor,
        "加法溢出的处理可选 `checked_add` 转错或直接 wrapping，待定，看情况再定）。",
        1,
    )
    (FIX / "defect-dev-design.md").write_text(design, encoding="utf-8")

    test = (FIX / "test-design.md").read_text(encoding="utf-8-sig")
    row = "| A3 非法输入拒绝 | P1 | TC3 | 已覆盖 |  | — |\n"
    if row not in test:
        print("FAIL: 覆盖矩阵 A3 行不存在")
        return 1
    test = test.replace(row, "", 1)
    (FIX / "defect-test-design.md").write_text(test, encoding="utf-8")
    print("OK: 反向夹具已生成（方案待定 + 覆盖矩阵漏 A3）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
