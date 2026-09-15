# module-design-gate 评测标准（判据正文）

来源套件（正向）：`module-design-gate-SR1-rbcore-clean-eval` / 66dbb318-47a9-4752-a83a-8bef09539050
来源套件（反向）：`module-design-gate-SR1-rbcore-defect-eval` / 512121a7-cc58-415f-b790-d301e630847a
skill：module-design-gate  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `mdg-assert`（正向） | command | 100.0 | False | 0 |
| `mdg-assert`（反向） | command | 100.0 | False | 0 |

---

## mdg-assert（正向，clean）

- 命令：`python C:\tmp\ctx5dg\assert_gate_common.py`（workspace 之外执行）
- 脚本本体：`fixture/assert_gate_common.py`

### rubric

```text

```

> 注：`command` 型 grader 无 `rubric` 字段。全部判据在脚本中：

| # | 断言 | 出处 |
|---|---|---|
| 1 | `.context/模块设计门禁结果.md` 存在 | yaml output required |
| 2 | 三输入（说明书/测试设计/context）sha1 不变 | 成果物协作规则「不得创建、编辑或覆盖」 |
| 3 | 结论 ∈ {通过， 不通过， 阻塞}（行内或表格形态；交替序「不通过」在前防截断） | 门禁结论「结论只能是」 |
| 4 | 建议 ∈ 七值枚举 | 「还必须给出明确的门禁建议」 |
| 5 | 结论-建议一致（通过 ⇔ 建议含「可进入 AICoding」；不通过 ⇎ 仅「可进入」） | 「只要存在任一适用维度未达标，门禁结论不得为 通过」 |
| 6 | 报告引用的 D/TC/A/E 编号 ⊆ 对应输入的实际编号域 | 「必须来自正式说明书……必须能在证据索引中反查」 |

## mdg-assert（反向，defect）

- 命令：`python C:\tmp\ctx5dg\assert_gate_defect.py`（内部先跑 common 再判缺陷条款）
- 脚本本体：`fixture/assert_gate_defect.py`

在共用 6 条之上追加：

| # | 断言 | 出处 |
|---|---|---|
| 7 | 结论不得为「通过」 | 夹具含必须整改缺陷；「不通过：存在必须整改的问题」 |
| 8 | 「未达标维度」**字段值**含「验证闭环性」（防「七个维度达标」式过程表骗检） | 「结果文件只列未达标维度及其问题」+ 概要用例「门禁必须判定验证闭环性不通过」 |

### 断言红绿验证（定稿时）

14 个合成用例，**0 个不符预期**（`fixture/redgreen/`）：

正向（2 绿 + 6 红）：行内/表格两种结论形态均绿；红=结果缺失/输入被改写/结论缺失/
建议缺失/结论通过但建议回 TOBE/引用不存在的 D99/引用不存在的 TC88。

反向（2 绿 + 4 红）：两形态绿；红=判「通过」/未达标维度字段缺验证闭环性/
字段写「无」但正文承认 TC99 问题（骗检）/字段写「决策确定性」缺验证闭环性。

### 迭代记录

| 轮 | 缺陷 | 修正 |
|---|---|---|
| v1/v2 | 结论只认行内形态；GBK 控制台 UnicodeEncodeError 掩盖判据 | 双形态容差；stdout reconfigure UTF-8 |
| v2/v3 | setup 漏投架构文档，被 gate 抓为「证据不可反查」（夹具组装缺陷，gate 行为正确） | 双 suite 加投 software_architecture.md |
| v3/v4 | 断言 8 按全文含维度名判定，被达标过程表骗检 | 改判「未达标维度」字段值 |
| v3/v4 | 缺陷 1 初版只改 D5 依据列（被合规降级为非阻断项） | 提升到设计结论列（「待定」） |
