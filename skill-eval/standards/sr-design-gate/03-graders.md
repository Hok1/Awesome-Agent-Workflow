# sr-design-gate 评测标准（判据正文）

来源套件：`sr-design-gate-SR1-sm2-eval`
套件 id：7ea9bb80-e7a9-4255-85f3-e058216b87ae
skill：sr-design-gate  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `gate-assert` | command | 100.0 | False | 0 |

---

## gate-assert

- 名称：门禁结论黑盒断言（读报告与回传数据）
- 类型：`command`
- 权重：100.0
- 硬门槛：False
- 命令：`python .sdd/SR-1/assert_gate.py`（cwd = run 工作区；退出码 0 得满分 100，非 0 得 0 分）
- 脚本本体：`fixture/assert_gate.py`（sha1 `0747ae43f4c360ed1a6f89f0ce9a249d4f18f641`）

### rubric

```text

```

> 注：本 grader 类型为 `command`，无 `rubric` 字段——导出脚本只渲染 `rubric`，故上方为空块。
> 该 grader 的全部判据在 `fixture/assert_gate.py` 中，其断言条款与出处如下（黑盒：脚本只读
> `.sdd/SR-1/SR-design-gate.md` 与 `.sdd/SR-1/gate-data.json`，不 import 任何被测源码）：

| # | 断言 | 出处 |
|---|---|---|
| 1 | 报告文件存在且 >= 200 字符 | `definitions/sr-design-gate.yaml` 输出 `.sdd/{SR}/SR-design-gate.md` 为必填 |
| 2 | `gate-data.json` 存在且为合法 JSON | `definitions/sr-design-gate.yaml` data 字段 |
| 3 | 四个必备字段齐备：`gate_result`/`recommendation`/`report`/`summary` | `definitions/sr-design-gate.yaml` |
| 4 | `report` 非 null 且指向 `SR-design-gate.md` | `SKILL.md`「report 恒为实际报告路径、不得填 null」 |
| 5 | `gate_result` ∈ {pass, fail, blocked} | `flow.yaml` choice 节点取值域 |
| 6 | `summary` 六个计数齐备且均为整数 | `flow.yaml` summary 定义 |
| 7 | `gate_result != pass` | `crypto-gate-checklist.md` §5：存在私钥导出接口但无导出策略 = P0；有 P0 不得 pass |
| 8 | `p0_conflicts > 0` | 同上（夹具含该 P0） |
| 9 | `blocked` 时 `blocking_issues` 或 `pending_questions` 至少一项非 0 | 结论与计数自洽（`flow.yaml` 六计数语义） |
| 10 | 非 pass 时不得 `unqualified_dimensions`/`p0`/`p1` 全零 | 结论与计数自洽 |
| 11 | `unqualified_dimensions == 3` | **准入维度表粒度**下的未达标维度数，见 `00-source-standard.md` §2 HG-3 |
| 12 | 报告正文覆盖 `敏感参数安全`/`契约完整性`/`图表变更表达` 三个维度名 | `gate-checklist.md` 准入维度表 + 依据可复核要求 |

全部通过则输出 `GATE-ASSERT-PASS` 并 `exit 0`。

### 断言红绿验证（使用前完成）

断言脚本在用于实测之前，已用 12 个合成用例验证它能红也能绿，**0 个不符预期**：

| 用例 | 期望 | 实测 |
|---|---|---|
| 正确产物（3 维度 / fail / 1 P0） | 绿 | `GATE-ASSERT-PASS` |
| 报告缺失 | 红 | `ASSERT-FAIL: 门禁报告缺失` |
| `report=null` | 红 | `ASSERT-FAIL: report 为 null` |
| 漏判 P0 判 pass | 红 | `ASSERT-FAIL: 漏判 P0` |
| 维度数=2 | 红 | `ASSERT-FAIL: unqualified_dimensions=2` |
| 维度数=4 | 红 | `ASSERT-FAIL: unqualified_dimensions=4` |
| 报告缺「契约完整性」 | 红 | `ASSERT-FAIL: 报告未覆盖维度` |
| fail 但 p0=0 | 红 | `ASSERT-FAIL: 与「夹具含 P0」不符` |
| 回传数据非 JSON | 红 | `ASSERT-FAIL: 不是合法 JSON` |
| summary 缺计数 | 红 | `ASSERT-FAIL: summary 缺计数` |
| blocked 但无阻塞项 | 红 | `ASSERT-FAIL: 结论与计数自相矛盾` |
| blocked 且有 2 阻塞项 | 绿 | `GATE-ASSERT-PASS` |
