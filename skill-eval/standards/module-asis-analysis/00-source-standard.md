# 模块 ASIS 分析质量测评标准 —— RBS 国密 SM2 / rbs-core 现状分析（SR-1）

> 版本：v1.0（2026-09-14）
> 用途：作为 skill-eval 测评平台对 `module-asis-analysis` skill 打分的输入标准。
> 立场：TOBE 详细设计与门禁的下游使用者视角。不问"分析写没写"，只问
> "这份 ASIS 能不能作为设计输入被托付"。

---

## 0. 被测评需求是什么

- **SR 编号**：SR-1（同一条 RBS 国密 SM2 需求链路的第四个测评点）
- **需求原文**：
  1. SR编号：SR-1
  2. 需求人：目前SM2算法没有应用在此代码仓。需要用户认证支持SM2算法、验证 GTA 签发的 SM2 attestation token、rbs-cli 生成 SM2 token。
- **代码仓**：`globaltrustauthority-rbs`（分支 `master`，基线 commit `7ef62cd`）
- **目标模块**：`rbs-core`（`rbs/core/`——认证验签与用户公钥登记所在的核心 crate）
- **交付物**：`.sdd/SR-1/{AR}/{模块组名}/.context/详细设计上下文.md`
  （`definitions/module-asis-analysis.yaml` 的 required output）

**这项任务的业务实质**：ASIS 是 SDD 链路里唯一的"代码事实发现"环节——TOBE 设计、
门禁、AICoding 全都消费它的结论。ASIS 说谎（伪造代码证据、推断冒充事实、混入实现方案）
不会在自己的文档里爆炸，会在下游每一个决策里爆炸。因此本 skill 的全部规则都围绕一件事：
**结论必须能反查到代码证据，边界必须来自架构文档而非结构推断，现状与设计严格分离**。

**为什么它适合在这个 harness 里测**：
1. **无 MCP、无强制用户交互。** SKILL.md 明示 `ask_user` 不可用时可退回
   「标记为 `需前置确认`」；前置的工作流确认在"由工作流调用"语义下跳过。
2. **最硬的契约是确定性的**：`.sdd/software_architecture.md` 缺失即中断
   （fail-closed）、正式说明书不得创建、C1–C8 固定骨架、边界来源标记枚举、
   结论/证据编号体系——全部可脚本断言。
3. **可防伪证。** 产物提到的代码路径必须在 workspace 真实存在——
   这条断言直接命中 LLM 生成文档的最大风险（幻觉引用）。

**测评用两个独立 suite（setup 是 suite 级，正反两例的夹具互斥）**：

- **正向 `with-arch`**：`.sdd/software_architecture.md` 就位（夹具按 RBS 真实
  workspace 结构声明 6 个模块的边界），期望完整 ASIS context。
- **反向 `no-arch`**：刻意不提供架构文档（RBS 仓库本来就没有），期望
  **中断 + 阻塞标记 + 无推断边界 + 无正式说明书**。这是本 skill 区别于
  "让模型自由发挥写分析"的核心纪律。

两个 suite 共用：需求原文、SR-design.md（上游设计，43K 真实测评产出，作为需求上下文）、
断言脚本、preflight。

---

## 1. 打分总则（judge 必读）

1. **判据全部确定性。** 本 skill 的产物契约（路径、骨架、标记枚举、编号体系、
   禁止事项）全部写在 SKILL.md 与 yaml 里，不经 LLM 判读。每个 suite 单条
   `command` grader（weight=100）。
2. **fail-closed 是第一判据。** 反向用例不是附加题：「缺架构文档即中断」是
   SKILL.md 模块边界规则的头条。无头 harness 里"中断"的可观测形态是：
   无产物，或产物带 `blocked`/`ASIS 阻塞`/`状态：阻塞`/`立即中断` 标记，
   且不含确定边界声明。
3. **证据必须可反查。** 产物引用的 `rbs/...`、`tools/...` 代码路径抽样核验
   真实存在；引用数为 0 视为证据链未建立。
4. **ASIS/TOBE 分离是红线。** 创建正式《模块详细设计说明书.md》、或在 C3
   把「建议采用/可以复用/应新增」写成结论，均为违规。
5. **0-100 分锚点**：与 mermaid-diagram 同款——全过 100，任一失败 0。

---

## 2. 硬性门槛（对应断言条款）

### 正向（assert_asis.py，7 条）

| # | 断言 | 出处 |
|---|---|---|
| 1 | `.sdd/SR-1/*/*/.context/详细设计上下文.md` 存在 | `module-asis-analysis.yaml` output required |
| 2 | C1–C8 八个固定目录标题齐全 | SKILL.md 阶段 1「加载模板……全部固定目录的骨架」+ 质量标准「保留标题」 |
| 3 | 边界来源标记为 `declared by software_architecture.md` | SKILL.md 模块边界规则的标记枚举 |
| 4 | 结论编号（A1 形态）≥2 且证据编号（E1 形态）≥3 | 阶段 5/6「生成稳定 ASIS 结论编号」「证据编号」 |
| 5 | 产物引用的代码路径 ≥3 且抽样（前 10）全部真实存在 | 「代码仓可访问，必须直接检查代码」「重要结论有证据」 |
| 6 | 未创建任何 `模块详细设计说明书.md` | 「ASIS 阶段不得创建或编辑正式《模块详细设计说明书.md》」 |
| 7 | C3 不含「建议采用」「可以复用」「应新增」 | 职责边界：把这些「写成 ASIS 结论」违规 |

### 反向（assert_asis_blocked.py，3 条）

| # | 断言 | 出处 |
|---|---|---|
| 1 | 未创建任何 `模块详细设计说明书.md` | 同上（任何情况下适用） |
| 2 | context 产物若存在，必须含 `blocked`/`ASIS 阻塞`/`状态：阻塞`/`立即中断` 标记；不存在（中断无残留）也合规 | 模块边界规则「立即中断 ASIS，并……标记 ASIS 阻塞」 |
| 3 | `.sdd/SR-1/` 下契约外新增的分析类 .md 必须带阻塞标记 | 同上：「不得继续用代码结构……推断边界」 |

---

## 3. 判据落点

- 正向 grader：`python .sdd/SR-1/assert_asis.py`
- 反向 grader：`python .sdd/SR-1/assert_asis_blocked.py`
- 均以 run 工作区为 cwd，退出码 0 得 100，非 0 得 0。

## 4. 判定纪律

1. **先红后绿。** 两断言脚本共用 15 个合成用例验证（正向 1 绿 + 9 红，
   反向 2 绿 + 3 红），**0 个不符预期**。红绿夹具与驱动存 `fixture/redgreen/`。
2. **断言必须有出处。** §2 两表逐条标注。
3. **一次有效测评即够。** 不取方差；no_skill 组是平台强制对照，分数只作参考。
4. **诚实记录局限。** (a) SubAgent 查证是 SKILL.md 的组织要求，chrys harness
   无 SubAgent 机制——合规路径是 C1 标注「未使用 SubAgent，原因：环境不支持」，
   本判据不作硬性断言（防止对"真用了 subagent 能力"的误判），只作观察项。
   (b) 反向用例中「skill 中断并在最终回复声明阻塞」无法被 command grader 观测
   （回复在 artifact_dir 而非 workspace）——产物不存在即视为合规中断。
   (c) 断言 5 只核验路径存在性，不核验结论与代码内容的一致性（那是 llm_rubric
   的领域，本次刻意不覆盖）。

---

## 5. 实测记录（2026-09-14）

| 项 | 值 |
|---|---|
| 套件（正向） | `module-asis-analysis-SR1-rbcore-eval-v3` / `dfcaec95-a72f-460e-abfc-fdd3d4874abc` |
| 实验（正向） | `38ec8cee-2ff8-461c-b05b-ac1c2005d516`，`quick` |
| 套件（反向） | `module-asis-analysis-noarch-block-eval` / `add9d83e-25d1-4803-a661-f387f1d21653` |
| 实验（反向） | `b0a28d76-3878-4b00-a78f-0f3827d3abcd`，`quick` |
| 被测 skill 版本 | `module-asis-analysis` revision `e497ab74…`（skill_id `e0e40bd8`） |
| profile | chrys / `d3623a0e450d` / high，无网络，5400s |
| 项目基线 | `globaltrustauthority-rbs` @ `7ef62cd3` |

**结果**：

| 用例 | 组 | quality_score | 判据 | 耗时 |
|---|---|---|---|---|
| 正向 v3 | `current` | 100.0 | `ASIS-ASSERT-PASS`（16 结论 / 47 证据 / 19 路径全真） | 357.7 s |
| 正向 v3 | `no_skill` | 100.0 | `ASIS-ASSERT-PASS`（14 结论 / 16 证据 / 22 路径全真） | 285.1 s |
| 反向 | `current` | 100.0 | `ASIS-BLOCKED-ASSERT-PASS`（blocked 标记，无推断边界） | 88.5 s |
| 反向 | `no_skill` | 100.0 | `ASIS-BLOCKED-ASSERT-PASS`（同上） | 92.8 s |

**本次测评的三轮迭代（体系缺陷的实锤与修复）**：

1. **v1（判据泄露实锤）**：断言脚本随夹具投进 workspace，no_skill 组读脚本、
   照条款写产物、跑脚本自检到 PASS 后在回复中汇报「ASIS-ASSERT-PASS」——开卷考试。
   current 100 / no_skill 100，区分度为零。
2. **v2（封卷 + 措辞脆弱暴露）**：断言脚本移到 workspace 外、task 不再复述 skill 规则。
   两组都挂断言 3——产物 C2 用表格形态写「来源=software_architecture.md / 类型=declared」，
   语义正确但不是断言匹配的完整字符串 `declared by software_architecture.md`。
   断言措辞脆弱，不是 skill 违规。修断言（接受 declared+文件名在 C2 共现），
   红绿库扩到 17 用例重验 0 不符。
3. **v3（封卷后重测）**：current 100 / no_skill 100。

**v3 与反向结果的正确解读——`no_skill` 对照组对本模型已失效**：

- no_skill 组（workspace 无 skill 包、夹具零泄露、task 零泄露）产出了逐字级
  skill 术语：「declared by software_architecture.md」「未使用 SubAgent，原因：
  环境不支持」；反向用例中甚至引用「skill 工作流程第 4 阶段允许」这种内部章节结构；
  同时又自创模板里没有的「C6.4 边界外的相关约束输入」——不是照抄，是理解后运用。
- 结论：测评所用模型（deepseek-v4.1-flash）的训练语料包含 AAW skill 体系。
  `no_skill` 组不再是「无 skill 基线」，而是「凭记忆执行 skill」的基线。
  **delta 分数在本模型上不能度量 skill 的增量价值。**
- 反向用例的真正收获：知道规则 ≠ 遵守规则，但本模型连遵守也做到了——
  两组都 fail-closed（标记 blocked、无推断边界、无正式说明书、未创建契约外分析）。
- 因此本次测评的有效结论限于：**skill 在本 harness 中可执行、产物合规、
  fail-closed 纪律成立**（current 组正反两例均 100）；skill 的增量价值
  需要换用语料中不含 AAW 的模型才能测量。

**平台约束**：同前——`no_skill` 组硬编码不可排除。

