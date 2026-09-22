# module-tobe-design 评测标准（判据正文）

来源套件：`module-tobe-design-SR1-rbcore-eval`
套件 id：10c7a712-a2db-439c-90be-8dc6876796c0
skill：module-tobe-design  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `tobe-assert` | command | 100.0 | False | 0 |

---

## tobe-assert

- 名称：TOBE 说明书黑盒断言（契约路径/9章大纲/过程隔离/职责禁区/契约保真）
- 类型：`command`
- 权重：100.0
- 硬门槛：False
- 命令：`python C:\tmp\ctx5tb\assert_tobe.py`（cwd = run 工作区；**脚本在 workspace 之外**，被测对象不可读）
- 脚本本体：`fixture/assert_tobe.py`

### rubric

```text

```

> 注：`command` 型 grader 无 `rubric` 字段。全部判据在 `fixture/assert_tobe.py`：

| # | 断言 | 出处 |
|---|---|---|
| 1 | `.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md` 存在 | `module-tobe-design.yaml` output required；成果物协作规则「文件名固定」 |
| 2 | 9 个一级章节齐全（需求背景/外部依赖/整体方案/模块详细方案/对外接口/数据库表设计/受影响模块与交互/关键契约清单/附录三方件约束） | §4.1「必须按 tobe-output-template.md 的 9 个一级章节组织」 |
| 3 | 说明书不含「证据索引」章节；剥离 fenced 代码块后 `E\d+` ≤3 处；不含「检索过程/查证过程/反证记录/门禁采样/追踪矩阵」字样 | 成果物协作规则「不得写入 ASIS 检索过程、证据编号表、推导过程、反证记录、门禁采样、追踪矩阵等过程性内容」 |
| 4 | context 的 TOBE 增量区（C14/C16）引用 ASIS 结论编号 ≥2，且全部落在 ASIS 区（C14 之前）实际出现的编号集合内 | 「TOBE 中引用的 ASIS 事实必须在详细设计上下文中使用已有的 ASIS 结论编号和证据编号建立追踪」+ tobe-context-template.md C14/C16 |
| 5 | 不含测试用例编号（`TC-\d+`）、任务拆分（`TASK-\d+` 或任务拆分章节） | 职责边界：测试用例与任务拆分不属 TOBE |
| 6 | 不含 ≥10 行的 fenced Rust 代码块 | 职责边界：大段可实现代码不属 TOBE |
| 7 | 出现 ≥2 个 ASIS 已查明的现状契约标识符（`SUPPORTED_ALGORITHMS`/`auth_value`/`validate_and_derive_alg`/`BearerTokenVerifier`） | 「契约保真是硬要求」 |
| 8 | 含状态表达：行内状态字段（完成/部分完成/阻塞/已定稿），或决策表状态列（表头含「状态」且表体出现 已定稿/需前置确认） | 输出模式「至少保留 TOBE 状态」+ 阻塞规则 + 模板 §3.1 决策表 |

全部通过输出 `TOBE-ASSERT-PASS` 并 `exit 0`。

### 断言红绿验证（定稿时）

17 个合成用例，**0 个不符预期**（3 绿 + 14 红；驱动与夹具 `fixture/redgreen/`）：

绿：完整合规矩（行内状态）/「文档状态：**部分完成**」形态/决策表「状态」列形态 /
mermaid 图含 `E401` 节点ID（剥离代码块后不计入证据编号）。

红：产物缺失 / 缺第 6 章 / 含证据索引章节 / 正文 E 编号 >3 / 含「检索过程」/
含 TC-01 / 含 TASK-1 任务拆分 / ≥10 行 Rust 代码块 / 四标识符全无 /
无任何状态表达 / context 缺 C14-C16 / context TOBE 区无 A 引用 / context 引用
ASIS 区不存在的编号（A23）。

### 迭代记录（判据缺陷与修复）

| 轮 | 缺陷 | 修正 |
|---|---|---|
| v1 | chrys 原渠道额度耗尽（环境问题，非判据问题） | 切 DeepSeek 官方 profile |
| v2/v3 | 断言 4 对象错：A/E 追踪应在 context（C14/C16）非说明书 | 改判 context TOBE 增量区 |
| v4 | 断言 4 硬编码 A16 上限（实际合法域 A1–A20）；断言 8 漏决策表状态列形态 | 合法域动态提取；状态接受两种形态 |
| v5 前 | 断言 3 把 mermaid 节点 `E401` 误判为证据编号 | 剥离代码块再计数 |
