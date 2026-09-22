# 模块 TOBE 详细设计质量测评标准 —— RBS 国密 SM2 / rbs-core 目标设计（SR-1）

> 版本：v1.0（2026-09-14）
> 用途：作为 skill-eval 测评平台对 `module-tobe-design` skill 打分的输入标准。
> 立场：评审者与 AICoding 的下游使用者视角。不问"设计写没写"，只问
> "这份说明书能不能让 AICoding 不再补做产品或架构决策"。

---

## 0. 被测评需求是什么

- **SR 编号**：SR-1（RBS 国密 SM2 需求链路的第五个测评点）
- **需求原文**：
  1. SR编号：SR-1
  2. 需求人：目前SM2算法没有应用在此代码仓。需要用户认证支持SM2算法、验证 GTA 签发的 SM2 attestation token、rbs-cli 生成 SM2 token。
- **代码仓**：`globaltrustauthority-rbs`（分支 `master`，基线 commit `7ef62cd`）
- **目标模块**：`rbs-core`（`rbs/core/`）
- **交付物**：`.sdd/SR-1/{AR}/{模块组名}/模块详细设计说明书.md`
  （`definitions/module-tobe-design.yaml` 的 required output；
  **TOBE 是正式说明书的唯一写入者**——ASIS 测评禁止创建，本测评要求创建）

**这项任务的业务实质**：TOBE 是 SDD 链路里把「代码事实」收敛为「目标设计」的环节。
它下游是测试设计与 AICoding——说明书里每个接口、错误码、配置项都会被当成实现契约。
因此本 skill 的全部规则围绕四条链：证据链（需求→ASIS 证据→TOBE 决策）、边界链、
执行链、风险链。**凭空设计（脱离 ASIS 证据）与契约失真（上游明确的契约被概括掉）
是两类最典型的爆炸方式。**

**本次测评的输入是真实链路上游产物**：`.sdd/SR-1/AR-1/rbs-core/.context/详细设计上下文.md`
直接采用 module-asis-analysis 正向 v3 测评 `current` 组的真实产出
（16 条结论编号、47 条证据、覆盖验签入口/算法分派/公钥登记/配置/测试现状）——
不是手写夹具。ASIS 结论编号 A1–A16 与 `SUPPORTED_ALGORITHMS`、`auth_value` 等
代码事实都在其中，TOBE 必须以此为基础。

**可测性**：无 MCP、无强制用户交互（`需前置确认` 为合规标记路径）。
硬契约齐全：固定产物路径、9 章大纲、过程性内容隔离（说明书不得暴露证据编号表）、
职责禁区（测试用例/任务拆分/大段实现代码）、契约保真、阻塞规则。

**判据保密纪律（自本次起成为默认）**：断言脚本不进 workspace、task 不复述 skill 规则、
判据只在 suite 定义里给 judge（本套件无 llm grader，expected 仅存档）。

---

## 1. 打分总则

1. **判据全部确定性。** 单条 `command` grader（weight=100），workspace 外执行。
2. **0-100 分锚点**：全过 100，任一失败 0（硬性门槛，非评分曲线）。
3. **一次有效测评即够。** 不取方差；no_skill 组为平台强制对照。
   注意：本模型训练语料含 AAW 体系（module-asis-analysis 测评已实锤），
   `no_skill` 组分数仅作参考，不构成「无 skill 基线」。
4. **诚实记录局限。** 断言能判「章节齐不齐、禁区碰没碰、契约引用在不在」，
   判不了「设计决策对不对」——后者属 llm_rubric，本次刻意不覆盖。

---

## 2. 硬性门槛（对应断言条款）

| # | 断言 | 出处 |
|---|---|---|
| 1 | `.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md` 存在 | `module-tobe-design.yaml` output required；成果物协作规则「文件名固定」 |
| 2 | 9 个一级章节齐全：1 需求背景、2 外部依赖、3 整体方案、4 模块详细方案、5 对外接口、6 数据库/表设计、7 受影响模块与交互、8 关键契约清单、9 附录/三方件约束 | §4.1「正式说明书必须按 tobe-output-template.md 的 9 个一级章节组织」 |
| 3 | 说明书不含证据编号表/检索过程等过程性内容（无「证据索引」章节；`E\d+` 编号出现 ≤3 次；无「检索过程」「查证过程」字样） | 成果物协作规则：「不得写入 ASIS 检索过程、证据编号表、推导过程、反证记录、门禁采样、追踪矩阵等过程性内容」 |
| 4 | 说明书引用 ASIS 结论编号（`A\d+` 形态 ≥2 处），且引用的编号 ≤ A16（不超出 ASIS 输入范围） | 「TOBE 中引用的 ASIS 事实必须……使用已有的 ASIS 结论编号和证据编号建立追踪」「不得脱离 ASIS 证据凭空设计」 |
| 5 | 不含测试用例编号（`TC-\d+`）或任务拆分编号（`TASK-\d+`/`任务拆分`章节） | 职责边界：「测试用例编号、测试矩阵……」「AICoding 任务编号、任务拆分……」不负责 |
| 6 | 不含 ≥10 行的 fenced Rust 代码块 | 职责边界：「完整类或函数实现、可直接运行的业务逻辑……从现有代码复制的大段实现」不负责 |
| 7 | 出现 ≥2 个 ASIS 已查明的真实代码标识符（`SUPPORTED_ALGORITHMS` / `auth_value` / `validate_and_derive_alg` / `BearerTokenVerifier`） | 「契约保真是硬要求」；这些标识符是 ASIS 查明并进入 SR-design 的真实现状契约 |
| 8 | 出现状态字段（`完成`/`部分完成`/`阻塞` 之一） | 阻塞规则：「标记 TOBE 阻塞或部分完成」；质量标准要求状态可判 |

---

## 3. 判据落点

单条 `command` grader：`python C:\tmp\ctx5tb\assert_tobe.py`，cwd = run 工作区，
退出码 0 得 100，非 0 得 0。断言脚本在 workspace 之外。

## 4. 判定纪律

1. **先红后绿。** 断言脚本以合成用例验证（绿：合规说明书骨架；红：逐条违反各断言），
   0 个不符预期后方可用于实测。红绿夹具存 `fixture/redgreen/`。
2. **断言必须有出处。** §2 逐条标注。
3. **范围控制。** 本测评只判产物形态与契约纪律，不判设计优劣。

---

## 5. 实测记录（2026-09-14）

| 项 | 值 |
|---|---|
| 套件 | `module-tobe-design-SR1-rbcore-eval` / `10c7a712-a2db-439c-90be-8dc6876796c0` |
| 实验（定稿轮） | `95b8f3c3-c89a-4d24-ab8e-edf9ca554b83`，`quick` |
| 被测 skill 版本 | `module-tobe-design` revision `ec706d43…`（去 BOM 后） |
| profile | chrys / `e5d1a7b2c901`（DeepSeek 官方端点 `deepseek-flash`）/ high，无网络，5400s |
| 项目基线 | `globaltrustauthority-rbs` @ `7ef62cd3` |

**结果**：

| 组 | 状态 | quality_score | 耗时 |
|---|---|---|---|
| `current`（被测） | completed | 100.0（`TOBE-ASSERT-PASS`） | 170.8 s |
| `no_skill`（平台强制内置） | completed | 100.0（`TOBE-ASSERT-PASS`） | 415.3 s |

两组说明书均合规：9 章大纲齐全、TOBE 区追踪引用 A 编号落在 ASIS 输入合法域（A1–A20）、
四个现状契约标识符全中、无职责禁区内容。current 组快 2.4 倍（skill 的流水线指导
减少了探索时间），但在本模型上形态级区分度仍为零（语料先验，见
`module-asis-analysis/00-source-standard.md` §5 的体系发现 2）。

**断言的四轮迭代（每轮都是出处解读的修正）**：

| 轮 | 缺陷 | 证据 | 修正 |
|---|---|---|---|
| v1 | （环境）chrys 原渠道 API 额度耗尽，current 组 403 | `预扣费额度失败，剩余 ＄0.0656` | 切换到 DeepSeek 官方端点（新建 model profile `e5d1a7b2c901`），skill 本体不动 |
| v2/v3 | 断言 4 对象错：A/E 编号追踪要求在 **context**（C14/C16），不在说明书 | 模板原文「详细 ASIS 证据留在 context」「正式说明书……不暴露……追踪矩阵」；C14 表样例 `D1 \| R1 / A1 / E1` | 断言 4 改判 context 的 TOBE 增量区 |
| v4 | 断言 4 硬编码编号上限 A16，但 ASIS 输入实际含 A1–A20 | 两组均引用 A17–A19，夹具 grep 证实合法域为 20 | 合法集合改为从 ASIS 区动态提取（断言必须有出处——出处=输入数据本身） |
| v4 | 断言 8 只认行内状态字段，漏模板 §3.1 决策表的「状态」列形态 | current 组说明书决策表含「已定稿」 | 断言 8 接受行内字段或决策表状态列 |
| v5 前 | 断言 3 的 `\bE\d+\b` 把 mermaid 图节点 `E401["AuthError → 401"]` 误判为证据编号 | current 组说明书含流程图，E401 是节点 ID | 剥离 fenced 代码块后再计数 |

每轮修正均走红绿验证（最终 17 用例：3 绿 + 14 红，0 不符），夹具与记录见 `fixture/redgreen/`。

**平台与资源备注**：测评中途 chrys 原中转渠道（`d3623a0e450d`）额度耗尽，
DeepSeek 官方 profile 为用户指示切换；`sr-design`、`module-tobe-design` 两个
SKILL.md 的 UTF-8 BOM（git HEAD 引入）经用户批准去除——否则平台拒绝 import
（「SKILL.md must start with YAML frontmatter」）。
