# module-test-design 评测标准（判据正文）

来源套件：`module-test-design-SR1-rbcore-eval`
套件 id：260d8640-67b9-407b-b3c3-15d4f1129092
skill：module-test-design  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `testdesign-assert` | command | 100.0 | False | 0 |

---

## testdesign-assert

- 名称：测试设计黑盒断言（产物/TC形态/无表格/四字段/覆盖矩阵/说明书未动/语言无关）
- 类型：`command`
- 权重：100.0
- 命令：`python C:\tmp\ctx5td\assert_testdesign.py`（cwd = run 工作区；脚本在 workspace 之外）
- 脚本本体：`fixture/assert_testdesign.py`

### rubric

```text

```

> 注：`command` 型 grader 无 `rubric` 字段。全部判据在 `fixture/assert_testdesign.py`：

| # | 断言 | 出处 |
|---|---|---|
| 0 | TOBE 说明书 sha1 不变（`f409b788…`） | 成果物协作规则「不得把测试用例写回 TOBE 正式说明书」 |
| 1 | `.sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md` 存在 | yaml output required |
| 2 | ≥3 条 `##### TCn` 用例条目 | §4「每个用例一个条目（##### TCn）」 |
| 3 | 用例正文无表格 | §4 明文「用例正文不得使用任何表格」 |
| 4 | 每条 TC 含 前置/输入/预期/断言 四字段 | §3「至少包含」+ §4 |
| 5 | 覆盖矩阵章节（标题形态定位）存在、为表格、引用 TC 与 D 编号 | §4 覆盖矩阵五列定义 |
| 6 | 用例正文无可直接粘贴的断言/测试代码 | 质量标准「断言条件精确但保持语言无关」 |
| 7 | 含用例总览且声明「最小充分」 | §4「用例总览」+「测试范围与策略摘要」 |

全部通过输出 `TESTDESIGN-ASSERT-PASS` 并 `exit 0`。

### 断言红绿验证（使用前完成）

11 个合成用例（1 绿 + 10 红），**0 个不符预期**（`fixture/redgreen/`）：

红：产物缺失 / TC 条目 1 条 / 用例正文含表格 / 缺「断言」字段 / 无覆盖矩阵章节 /
矩阵无 D 编号 / 用例含 `#[test]` 断言代码 / 说明书被改写（sha1 变动）/
无「最小充分」声明 / 无用例总览。

### 迭代记录

| 轮 | 缺陷 | 修正 |
|---|---|---|
| v1 | 断言 5 从全文首次出现处截取「覆盖矩阵」，命中摘要句而非矩阵章节 | 按标题形态 `^#{2,4} …覆盖矩阵` 定位章节 |
