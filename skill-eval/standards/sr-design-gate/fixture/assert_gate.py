#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SR 门禁测评断言脚本（黑盒：只读产物与门禁回传数据，不读 aaw 源码）。"""
import json, os, re, sys

def fail(msg):
    print("ASSERT-FAIL: " + msg)
    sys.exit(1)

def ok(msg):
    print("ASSERT-OK: " + msg)

# --- 1. 工作单契约输出：报告必须存在 ---
rep = ".sdd/SR-1/SR-design-gate.md"
if not os.path.isfile(rep):
    fail("门禁报告缺失: " + rep)
txt = open(rep, encoding="utf-8", errors="replace").read()
if len(txt.strip()) < 200:
    fail("门禁报告近乎为空, %d 字符" % len(txt.strip()))
ok("报告存在 %d 字符" % len(txt))

# --- 2. 门禁回传数据 ---
data_path = ".sdd/SR-1/gate-data.json"
if not os.path.isfile(data_path):
    fail("回传数据文件缺失: " + data_path)
try:
    d = json.load(open(data_path, encoding="utf-8"))
except Exception as e:
    fail("回传数据不是合法 JSON: %r" % e)

for k in ("gate_result", "recommendation", "report", "summary"):
    if k not in d:
        fail("回传数据缺字段: " + k)

if d.get("report") in (None, "", "null"):
    fail("report 为 null —— 违反 SKILL「report 恒为实际报告路径，不得填 null」")
if not str(d["report"]).replace("\\", "/").endswith("SR-design-gate.md"):
    fail("report 未指向门禁报告: %r" % d["report"])
ok("report=%s" % d["report"])

gr = d["gate_result"]
if gr not in ("pass", "fail", "blocked"):
    fail("gate_result 取值非法: %r" % gr)

s = d.get("summary")
if not isinstance(s, dict):
    fail("summary 非对象: %r" % type(s))
NEED = ("unqualified_dimensions", "p0_conflicts", "p1_conflicts",
        "p2_findings", "pending_questions", "blocking_issues")
for k in NEED:
    if k not in s:
        fail("summary 缺计数: " + k)
    if not isinstance(s[k], int):
        fail("summary.%s 非整数: %r" % (k, s[k]))
ok("summary=%s" % json.dumps({k: s[k] for k in NEED}, ensure_ascii=False))

# --- 3. 结论一致性（依据 SKILL 自身规则，非我发明） ---
# 夹具含明确 P0（私钥导出策略缺失），故不得 pass。
if gr == "pass":
    fail("结论为 pass，但夹具存在 crypto §5 明确 P0（私钥导出策略缺失）—— 漏判 P0")
if s["p0_conflicts"] == 0:
    fail("结论 %s 但 p0_conflicts=0，与「夹具含 P0」不符" % gr)
ok("结论 %s 且识别到 P0（p0_conflicts=%d）" % (gr, s["p0_conflicts"]))

# pass 才要求六项全零；这里既然非 pass，要求至少有一项非零，且不得自相矛盾
if gr == "blocked" and s["blocking_issues"] == 0 and s["pending_questions"] == 0:
    fail("结论 blocked 但 blocking_issues/pending_questions 均为 0，结论与计数自相矛盾")
if (s["unqualified_dimensions"] == 0 and s["p1_conflicts"] == 0
        and s["p0_conflicts"] == 0):
    fail("非 pass 结论却无任何未达标维度或冲突，结论与计数自相矛盾")
ok("结论与计数自洽")

# --- 3b. 未达标维度数：夹具恰有 3 个（用户钉死 ==3） ---
# 出处：同一个新增导出接口在三个准入维度上各自独立触发 ——
#   §10 crypto-gate-checklist §5  → 敏感参数安全 (P0)
#   §9  接口契约完整性判定 条3/4  → 契约完整性   (P1，清单明文「未达标」)
#   图表变更表达检查 规则5/规则6   → 图表变更表达 (未达标)
if s["unqualified_dimensions"] != 3:
    fail("unqualified_dimensions=%d，夹具应为 3（敏感参数安全/契约完整性/图表变更表达）"
         % s["unqualified_dimensions"])
ok("unqualified_dimensions=3")

# --- 4. 报告正文必须落到具体维度名（有出处） ---
for dim in ("敏感参数安全", "契约完整性", "图表变更表达"):
    if dim not in txt:
        fail("报告未覆盖维度: " + dim)
ok("报告覆盖 3 个目标维度")
print("GATE-ASSERT-PASS")
