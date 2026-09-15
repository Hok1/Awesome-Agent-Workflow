# module-asis-analysis 评测标准（判据正文）

来源套件（正向）：`module-asis-analysis-SR1-rbcore-eval-v3` / dfcaec95-a72f-460e-abfc-fdd3d4874abc
来源套件（反向）：`module-asis-analysis-noarch-block-eval` / add9d83e-25d1-4803-a661-f387f1d21653
skill：module-asis-analysis  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `asis-assert`（正向） | command | 100.0 | False | 0 |
| `asis-assert`（反向） | command | 100.0 | False | 0 |

---

## asis-assert（正向，with-arch）

- 名称：ASIS 产物黑盒断言
- 类型：`command`
- 权重：100.0
- 命令：`python C:\tmp\ctx5aa\assert_asis.py`（cwd = run 工作区；**脚本在 workspace 之外**，被测对象不可读）
- 脚本本体：`fixture/assert_asis.py`

### rubric

```text

```

> 注：`command` 型 grader 无 `rubric` 字段。全部判据在 `fixture/assert_asis.py`：

| # | 断言 | 出处 |
|---|---|---|
| 1 | `.sdd/SR-1/*/*/.context/详细设计上下文.md` 存在 | `module-asis-analysis.yaml` output required |
| 2 | C1–C8 八个固定目录标题齐全 | SKILL.md 阶段 1 + 质量标准「保留标题」 |
| 3 | C2 含 `declared` 且含 `software_architecture.md`（或全文含完整标记 `declared by software_architecture.md`） | SKILL.md 模块边界规则的标记枚举 |
| 4 | 结论编号（A1 形态）≥2 且证据编号（E1 形态）≥3 | 阶段 5/6 |
| 5 | 产物引用代码路径 ≥3 且抽样（前 10）在 workspace 真实存在 | 「代码仓可访问，必须直接检查代码」「重要结论有证据」 |
| 6 | 未创建任何 `模块详细设计说明书.md` | 「ASIS 阶段不得创建或编辑正式说明书」 |
| 7 | C3 不含「建议采用」「可以复用」「应新增」 | 职责边界 |

全部通过输出 `ASIS-ASSERT-PASS` 并 `exit 0`。

## asis-assert（反向，no-arch）

- 命令：`python C:\tmp\ctx5aa\assert_asis_blocked.py`
- 前提自检：`.sdd/software_architecture.md` 必须不存在，否则 exit 2（setup 错误）

| # | 断言 | 出处 |
|---|---|---|
| 1 | 未创建任何 `模块详细设计说明书.md` | 职责边界（任何情况适用） |
| 2 | context 产物若存在，必含 `blocked`/`ASIS 阻塞`/`状态：阻塞`/`立即中断`；不存在（中断无残留）亦合规 | 模块边界规则「立即中断……标记 ASIS 阻塞」 |
| 3 | `.sdd/SR-1/` 下契约外新增分析类 .md 必带阻塞标记 | 「不得继续用代码结构……推断边界」 |

全部通过输出 `ASIS-BLOCKED-ASSERT-PASS` 并 `exit 0`。

### 断言红绿验证（使用前完成）

两脚本共用 17 个合成用例，**0 个不符预期**（驱动与夹具：`fixture/redgreen/`）：

正向（assert_asis.py，2 绿 + 9 红）：

| 用例 | 期望 | 实测 |
|---|---|---|
| 合规 context（完整标记形态） | 绿 | `ASIS-ASSERT-PASS` |
| 合规 context（表格形态：来源列+declared 类型列） | 绿 | `ASIS-ASSERT-PASS` |
| 产物缺失 | 红 | 未找到契约路径 |
| 缺 C7/C8 标题 | 红 | 固定目录骨架不完整 |
| 边界来源写「根据代码结构确认」 | 红 | declared 标记缺失 |
| 只给来源文件名、无 declared 类型 | 红 | declared 标记缺失 |
| 证据编号 0 条 | 红 | 证据编号不足 |
| 结论编号仅 1 个 | 红 | 结论编号不足 |
| 引用幻觉路径 `sm9_verify.rs` | 红 | 不存在的代码路径 |
| 全文不引用任何代码路径 | 红 | 证据链未锚定真实代码 |
| 创建《模块详细设计说明书.md》 | 红 | ASIS 阶段创建了正式说明书 |
| C3 含「建议采用」 | 红 | TOBE 拍板短语 |

反向（assert_asis_blocked.py，2 绿 + 3 红）：

| 用例 | 期望 | 实测 |
|---|---|---|
| 无任何产物（中断无残留） | 绿 | `ASIS-BLOCKED-ASSERT-PASS` |
| 产物带 blocked 标记 | 绿 | `ASIS-BLOCKED-ASSERT-PASS` |
| 产物无阻塞标记 | 红 | 不带阻塞标记 |
| 创建正式说明书 | 红 | 正式说明书 |
| 契约外写分析且无阻塞标记 | 红 | 契约外路径 |

### 三轮迭代记录（判据本身的缺陷与修复）

| 轮次 | 缺陷 | 证据 | 处置 |
|---|---|---|---|
| v1 | 断言脚本投进 workspace = 开卷 | no_skill 组 final-response 汇报「自检 assert_asis.py → PASS」 | 脚本移到 workspace 外，grader 用绝对路径 |
| v2 | 断言 3 精确字符串匹配过脆 | 两组产物用「来源/类型」表格列写 `declared`，语义正确但被误判 | 断言改为 C2 章节内共现判定；红绿库 +2 用例 |
| v3 | —（定稿） | current/no_skill 均 PASS | 归档本轮 |
