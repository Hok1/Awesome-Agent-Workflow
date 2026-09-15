# effective-document-writing 评测标准（判据正文）

来源套件：`effective-document-writing-SM2-eval`
套件 id：fc32df15-fee9-49f4-b79b-9cb10ecb8677
skill：effective-document-writing  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `docwrite-assert` | command | 100.0 | False | 0 |

---

## docwrite-assert

- 名称：文档重写黑盒断言（禁词/对话痕迹/三要素/原稿不动）
- 类型：`command`
- 权重：100.0
- 命令：`python C:\tmp\ctx5dw\assert_docwrite.py`（workspace 之外执行）
- 脚本本体：`fixture/assert_docwrite.py`

### rubric

```text

```

> 注：`command` 型 grader 无 `rubric` 字段。全部判据在 `fixture/assert_docwrite.py`：

| # | 断言 | 出处 |
|---|---|---|
| 1 | `docs/SM2-auth-design.md` 存在 | 任务契约 |
| 2 | 原稿 `.sdd/draft.md` 未被修改 | 「原稿是待审材料」 |
| 3 | 无黑话词（赋能/抓手/拉通/对齐颗粒度/颗粒度） | 「不使用……等词替代可直接说明的动作」 |
| 4 | 无空泛表态（显著提升/全面保障/充分考虑/持续优化） | 「避免……没有对象、条件或验证方式的表态」 |
| 5 | 无对话/生成过程痕迹 | 「隔离对话和修改过程」 |
| 6 | 方案要点落成结论；语义三要素在场：结论 + 支撑/边界 + 诚实标记（待确认/不覆盖） | 「设计文档写结论、依据和取舍」 |

全部通过输出 `DOCWRITE-ASSERT-PASS` 并 `exit 0`。

### 断言红绿验证（使用前完成）

8 个合成用例（1 绿 + 7 红），**0 个不符预期**（`fixture/redgreen/`）。

### 迭代记录

| 轮 | 缺陷 | 修正 |
|---|---|---|
| v1 | 三要素钉死词面（「依据」「取舍」），被正当措辞证伪 | 改语义要素判定 |
