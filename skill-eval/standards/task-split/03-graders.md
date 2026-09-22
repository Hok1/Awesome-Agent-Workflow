# task-split 评测标准（判据正文）

来源套件：`task-split-SR1-rbcore-eval`
套件 id：46392c6c-8b5c-4abf-8bd8-b68312520cb6
skill：task-split  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `tasksplit-assert` | command | 100.0 | False | 0 |

---

## tasksplit-assert

- 名称：任务拆分黑盒断言（产物/无独立任务文件/骨架/计划表/覆盖完整/存疑清零/输入只读）
- 类型：`command`
- 权重：100.0
- 命令：`python C:\tmp\ctx5ts\assert_tasksplit.py`（workspace 之外执行）
- 脚本本体：`fixture/assert_tasksplit.py`

### rubric

```text

```

> 注：`command` 型 grader 无 `rubric` 字段。全部判据在 `fixture/assert_tasksplit.py`：

| # | 断言 | 出处 |
|---|---|---|
| 1 | `tasks-overview.md` 存在于契约路径 | yaml output required |
| 2 | 无任何 `T\d+-*.md` 独立任务文件 | 任务计划边界·禁止写入 |
| 3 | 三输入 sha1 不变 | 输入只读 |
| 4 | 模板骨架七章节齐全 | overview_template.md；Phase 4「不得从空白文档自由发挥」 |
| 5 | 任务计划表六列形态、编号 T1 起连续、「做什么/改哪些文件」列不空 | 模板；拆分原则 4 |
| 6 | 测试设计 TC 全集（动态提取）⊆ overview 引用集 | 拆分原则 7「覆盖完整」 |
| 7 | 存疑汇总无未决内容 | 拆分原则 8「存疑不放行」 |

全部通过输出 `TASKSPLIT-ASSERT-PASS` 并 `exit 0`。

### 断言红绿验证（使用前完成）

10 个合成用例（1 绿 + 9 红），**0 个不符预期**（`fixture/redgreen/`）：

红：产物缺失 / 生成了 T1-sm2.md / 输入被改写 / 缺「存疑汇总」章节 / 任务表无 T 行 /
编号 T1→T3 跳号 / TC3 未被承接 / 存疑汇总含「待确认」/ 任务行内容近乎为空。
