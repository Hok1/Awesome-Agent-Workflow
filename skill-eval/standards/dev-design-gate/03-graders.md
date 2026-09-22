# dev-design-gate 评测标准（判据正文）

来源套件（正向）：`dev-design-gate-SR2-clean-eval` / 85017e9d-31cc-4fbb-9d99-b35d478f6d8a
来源套件（反向）：`dev-design-gate-SR2-defect-eval` / ac681f71-0b60-4995-a004-2c6b891b6de2
skill：dev-design-gate  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `devgate-assert`（正向） | command | 100.0 | False | 0 |
| `devgate-assert`（反向） | command | 100.0 | False | 0 |

---

## devgate-assert（正向，clean）

- 命令：`python C:\tmp\ctx5dg2\assert_devgate_common.py`（workspace 之外执行）
- 脚本本体：`fixture/assert_devgate_common.py`

### rubric

```text

```

> 注：`command` 型 grader 无 `rubric` 字段。全部判据在脚本中：

| # | 断言 | 出处 |
|---|---|---|
| 1 | `.sdd/SR-2/.context/dev-design-gate.md` 存在 | yaml output required |
| 2 | dev-design.md / test-design.md sha1 不变 | 「门禁阶段只读……不修改设计正文」 |
| 3 | 结论 ∈ {通过/不通过/阻塞} | 结论判定表 |
| 4 | 建议 ∈ {可进入任务拆分/修正后重新门禁/阻塞，缺少必要输入或用户决策} | gate-report.md 骨架 |
| 5 | 三检查项名（决策已收敛/代码论断可回溯/契约与验收可执行）逐项出现 | 「每项给出 达标/未达标 判定」「逐项判定，没有跳过」 |
| 6 | 结论-统计一致（通过⇒三计数全 0；不通过⇒unqualified>0 且指明整改对象） | 具体流程 5 + 报告边界 |

## devgate-assert（反向，defect）

- 命令：`python C:\tmp\ctx5dg2\assert_devgate_defect.py`（内部先跑 common）
- 脚本本体：`fixture/assert_devgate_defect.py`

追加：

| # | 断言 | 出处 |
|---|---|---|
| 7 | 结论不得为「通过」 | 「任一检查项未达标……不得通过」 |
| 8 | 「需整改项」章节命中检查项 1 与检查项 3 | 3 项准入检查表 +「未达标项必须指明问题出处与整改方向」 |

### 断言红绿验证（使用前完成）

13 个合成用例（正向 1 绿 + 7 红；反向 1 绿 + 4 红），**0 个不符预期**（`fixture/redgreen/`）。

### 实测亮点

正向 current 组对「干净」夹具判「不通过」且完全正当——抓到夹具自身的
`TokenGenerate`→`GenerateArgs` 命名错误（file:line 核验真实发生）与
「负数/溢出非法输入缺验收项」的覆盖缺口。详见 `00-source-standard.md` §5。
