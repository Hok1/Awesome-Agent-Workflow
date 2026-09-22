#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 v5 真实三件套生成反向夹具：植入两处有明确判定条款的缺陷。

缺陷 1（决策确定性）：D5 决策行的「设计依据摘要」列改为「待定」——
  出处：SKILL.md 维度未达标常见判定第 1 条「影响实现的……『待定』没有被明确标为
  非阻断改进项」。
缺陷 2（验证闭环性）：测试设计追加一条概要用例 TC99（无四字段）——
  出处：SKILL.md 成果物协作规则「若测试用例只写『补充单测』『验证异常』『覆盖兼容』
  等概要，缺少输入、前置条件、断言、观察点或建议位置，门禁必须判定验证闭环性不通过」。
"""
import io
import re
import sys
from pathlib import Path

FIX = Path(r"C:\tmp\ctx5dg\fixture")


def main() -> int:
    spec = (FIX / "模块详细设计说明书.md").read_text(encoding="utf-8-sig")
    # 缺陷 1（决策确定性）：D5 的「设计结论」列改为「待定」——关键方案未收敛。
    # 出处：SKILL.md 维度表「决策确定性：关键方案是否已定稿」；门禁建议枚举
    #       「先做上游/用户确认：核心方案……仍需外部确认」。
    # 该列内容含 `|`（r||s），split("|") 会错位，用整段子串替换。
    anchor = "JWS `alg=\"SM2\"`；签名段 `r||s` 各 32 字节 base64url 无填充；SM3 摘要；Z 用户标识采用标准默认；JWK `kty=EC,crv=SM2,x,y`"
    d5_line = [l for l in spec.splitlines() if l.startswith("| D5 ")]
    if not d5_line or anchor not in d5_line[0]:
        print("FAIL: 未找到 D5 行或结论列锚点")
        return 1
    spec = spec.replace(anchor, "待定（表示法约定未收敛，待 GTA 确认）", 1)
    (FIX / "defect-模块详细设计说明书.md").write_text(spec, encoding="utf-8")

    test = (FIX / "模块测试用例设计.md").read_text(encoding="utf-8-sig")
    inject = (
        "\n##### TC99\n\n"
        "- 优先级：P1\n"
        "- 场景：补充单测覆盖异常场景\n"
        "- 自动化：是\n"
    )
    (FIX / "defect-模块测试用例设计.md").write_text(test.rstrip() + "\n" + inject, encoding="utf-8")
    print("OK: 反向夹具已生成（D5 依据=待定；TC99 概要用例）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
