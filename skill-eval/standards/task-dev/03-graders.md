# task-dev 评测标准（判据正文）

来源套件：`task-dev-SR1-rbcore-T1-eval`
套件 id：9ec3e820-e012-470a-a8a0-8301a18bed0a
skill：task-dev  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `taskdev-assert` | command | 100.0 | False | 0 |

---

## taskdev-assert

- 名称：task-dev 落态黑盒断言（git 纪律/执行记录回填/范围/实现与测试/cargo 验证）
- 类型：`command`
- 权重：100.0
- 命令：`python C:\tmp\ctx5tdv\assert_taskdev.py`（workspace 之外执行；内部 subst 短盘符 +
  Strawberry perl 前置跑 cargo）
- 脚本本体：`fixture/assert_taskdev.py`

### rubric

```text

```

> 注：`command` 型 grader 无 `rubric` 字段。全部判据在 `fixture/assert_taskdev.py`：

| # | 断言 | 出处 |
|---|---|---|
| 1 | git HEAD == 基线且暂存区为空 | 调度边界「绝不执行 git add、git commit、push」 |
| 2 | tasks-overview「执行记录」含 T1 小节：状态 Completed + 「实现期补充与残余风险」 | §5「必填小节……缺失会被 done 拒绝」 |
| 3 | 代码改动 ⊆ T1 允许范围（四文件 + 测试位置） | §1.4「不提前实现后续 Task」；范围=任务计划 T1 行 |
| 4 | 新增 `rbs/core/src/auth/authn/sm2.rs` | 任务计划 T1「改哪些文件」 |
| 5 | 存在新增/修改的自动化测试 | §1.5「落实为自动化测试」 |
| 6 | `cargo test -p rbs-core --lib` 退出码 0 | §1.7/§1.8 |

全部通过输出 `TASKDEV-ASSERT-PASS` 并 `exit 0`。

### 断言红绿验证（使用前完成）

8 个合成用例（1 绿 + 7 红，迷你 git 仓），**0 个不符预期**（`fixture/redgreen/`）：

红：HEAD 移动 / 暂存区非空 / 执行记录无 T1 小节 / 缺必填小节 / 改动越出 T1 范围 /
未新增 sm2.rs / 无测试改动。（cargo 断言在迷你仓以 TD_SKIP_CARGO=1 跳过，实测真验。）

### 实测区分度（定稿轮）

current 100 / no_skill 0：两组代码均编译测试全过，唯一差异是 no_skill 组没有回填
「实现期补充与残余风险」必填小节。**增量价值在交接纪律而非编码能力。**
