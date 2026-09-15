# repo-init 评测标准（判据正文）

来源套件：`repo-init-rbs-eval`
套件 id：8e073c69-8621-4600-88ff-e285280f5ae6
skill：repo-init  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `repoinit-assert` | command | 100.0 | False | 0 |

---

## repoinit-assert

- 名称：repo-init 黑盒断言（架构文档/占位符清零/路径真实/AGENTS 识别）
- 类型：`command`
- 权重：100.0
- 命令：`python C:\tmp\ctx5ri\assert_repoinit.py`（workspace 之外执行）
- 脚本本体：`fixture/assert_repoinit.py`

### rubric

```text

```

> 注：`command` 型 grader 无 `rubric` 字段。全部判据在 `fixture/assert_repoinit.py`：

| # | 断言 | 出处 |
|---|---|---|
| 1 | `.sdd/software_architecture.md` 存在 | Phase 4；下游 module-asis-analysis 的唯一边界来源 |
| 2 | 豁免区（目录/1.2/1.3）之外 `{{` 占位符清零 | Phase 4「Fill in all placeholders……do NOT modify…1.2/1.3/目录」 |
| 3 | 真实模块路径命中 ≥2；产物中「模块根/src/tests/带扩展名」形态的引用全部真实存在 | 模板 2.1「当前代码仓下相对路径」 |
| 4 | 模板固定章节保留（目录/系统概览/模块清单） | 模板结构 |
| 5 | `AGENTS.md` 存在且识别 cargo 与 Rust | Phase 5「Detect: Build/test/lint commands; Languages…」 |

全部通过输出 `REPOINIT-ASSERT-PASS` 并 `exit 0`。

### 断言红绿验证（使用前完成）

9 个合成用例（2 绿 + 7 红），**0 个不符预期**（`fixture/redgreen/`）：

绿：合规文档 / 含「crate 名/职责域」写法（`rbs-core/auth`）的文档（不当作路径）。
红：架构文档缺失 / 豁免区外残留占位符 / 真实路径 <2 / 幻觉路径（`rbs/core/src/ghost`）/
缺「模块清单」章节 / AGENTS.md 缺失 / AGENTS.md 不含 cargo。

### 迭代记录

| 轮 | 缺陷 | 修正 |
|---|---|---|
| v1 | 防伪路径检查误伤「crate名/职责域」写法 | 只核验「模块根深入 src/tests/文件」形态的引用 |
