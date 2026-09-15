# 模块详细设计上下文（ASIS）

> 本文件为 ASIS 阶段过程上下文。ASIS 阶段不创建、不编辑、不覆盖正式《模块详细设计说明书.md》；正式说明书只能由 TOBE 阶段基于本文件的证据与结论生成。

## C1. ASIS 状态与阅读说明

| 项目 | 内容 |
|---|---|
| 本次需求/AR/变更点 | SR-1：用户认证支持 SM2、验证 GTA 签发的 SM2 attestation token、rbs-cli 生成 SM2 token；本次切片为 AR-1（SM2 用户认证）——现有验签入口、算法分派、用户公钥登记链路、配置与测试现状 |
| 变更类型 | 混合变更（初步判断，仅依据需求文本；因 ASIS 在阶段 1 中断，未做代码查证，见 C6.2） |
| 目标模块 | rbs-core（`rbs/core/`） |
| 仓库范围 | 当前工作目录 `globaltrustauthority-rbs`（Rust workspace） |
| 模块边界来源 | `.sdd/software_architecture.md` |
| 边界来源类型 | blocked |
| 本次 ASIS 分析范围 | 未确定（阶段 1 边界确认失败即中断） |
| 是否发生范围扩展 | 否 |
| ASIS 状态 | 阻塞 |
| 分析置信度 | 不适用（未进入事实查证） |
| 后续 TOBE 可引用结论 | 无（本次未产生任何 ASIS 结论编号 A*） |
| 不得定稿的结论 | 本次全部模块边界、需求切片与现状事实均不得定稿；TOBE 不得基于本文件推进依赖 rbs-core 边界的 AR-1 详细设计 |
| 阻塞或待确认项 | ASIS-阻塞-1：`.sdd/software_architecture.md` 缺失（见 C6.2）；C6.1 待确认问题 1 项 |

阅读说明：

- 本 skill 由 aaw-workflow 工作单无头调用，按 skill 规定跳过「前置操作：工作流编排检查」环节。
- 本环境无法启动 SubAgent，主 Agent 自行实施阶段 1 边界检查；**未使用 SubAgent，原因：环境不支持**（skill 工作流程第 4 阶段允许，并要求在 C1 标注）。
- 本环境不提供 MCP 工具，网络不可用；本次未依赖任何网络或 MCP 能力。

## C2. 模块边界确认

| 来源 | 发现 | 边界来源类型 | 影响 |
|---|---|---|---|
| `.sdd/software_architecture.md` | 文件不存在：`Test-Path .\.sdd\software_architecture.md` → `False`；`find . -iname "*software_architecture*"` 无结果；`python .sdd/SR-1/preflight_asis.py no-arch` → `PREFLIGHT-OK`（确认架构文档不存在） | blocked | 无合规模块边界来源，ASIS 阶段 1 立即中断，不进入 C3 事实查证 |

### C2.1 模块边界

未完成，原因：唯一允许的模块边界来源 `.sdd/software_architecture.md` 缺失，按 skill「模块边界规则」第 2 条立即中断，禁止用代码结构、README、根目录架构文档或用户口述推断边界；影响：无法将 `rbs/core/` 下文件与组件分类为「确定属于模块 / 疑似属于模块 / 外部依赖」；下一步需要：上游提供 `.sdd/software_architecture.md` 并显式声明 rbs-core 边界。

| 分类 | 路径或组件 | 判断依据 | 证据编号 |
|---|---|---|---|
| 确定属于模块 | 未确定 | 边界来源 blocked | E1 |
| 疑似属于模块 | 未确定 | 边界来源 blocked | E1 |
| 外部依赖 | 未确定 | 边界来源 blocked | E1 |

### C2.2 本次需求相关分析范围

未完成，原因：模块边界未确认，需求切片无法收敛；影响：AR-1 的验签入口、算法分派、用户公钥登记链路、配置与测试现状均未纳入/排除判定；下一步需要：先解除 ASIS-阻塞-1 后重跑本阶段。

| 分类 | 路径、组件或行为 | 纳入/排除原因 | 证据编号 |
|---|---|---|---|
| 需求相关 | 未确定 | 边界来源 blocked | E1 |
| 疑似相关 | 未确定 | 边界来源 blocked | E1 |
| 本次不分析 | 未确定 | 边界来源 blocked | E1 |

## C3. 关键 ASIS 事实

未完成，原因：阶段 1 边界确认失败即中断，未进入阶段 2（需求转代码线索）、阶段 3（探索任务清单）、阶段 4（分任务查证）与阶段 5（复核吸收）；影响：不产出任何 ASIS 结论编号，TOBE 无现状事实可引用；下一步需要：补齐 `.sdd/software_architecture.md` 并声明 rbs-core 边界后重跑 ASIS。

（无内容。边界未确认前，禁止用代码结构或 README 推断现状事实。）

## C4. 调用链与数据流

未完成，原因：未进入查证阶段，未追踪任何调用链或数据流；影响：无法给出 SM2 验签入口、算法分派、用户公钥登记等现状链路；下一步需要：解除 ASIS-阻塞-1 后按 AR-1 切片补做（届时如涉及多入口/跨组件协作需补现状时序图）。

## C5. 配置、数据、测试与依赖现状

未完成，原因：未进入查证阶段；影响：认证算法白名单配置、用户库字段与算法取值、既有测试覆盖、OpenSSL 等依赖现状均未核实；下一步需要：解除 ASIS-阻塞-1 后补做。

### C5.1 测试覆盖现状

未完成，原因：未进入查证阶段，未定位任何与 AR-1 相关的测试文件或套件；影响：无法评估 SM2 认证相关测试缺口；下一步需要：解除 ASIS-阻塞-1 后补做。

## C6. 规格漂移、待确认与阻塞

| 编号 | 类型 | 现状/漂移/风险 | 影响 | 后续关注点 | 证据编号 |
|---|---|---|---|---|---|
| D1 | 隐藏约束 / 流程 | 仓库缺少 `.sdd/software_architecture.md`，但上游 `SR-design.md` 以「代码现状为架构基线」继续设计 | ASIS 无合规边界来源，按 skill 规则必须中断，无法产出被 TOBE/Gate 引用的结论 | 补齐架构文档后重新评估 rbs-core 模块边界 | E1, E2 |

### C6.1 待确认问题

| 问题 | 类型 | 为什么影响 TOBE/AICoding | 当前线索 | 建议确认对象 |
|---|---|---|---|---|
| `.sdd/software_architecture.md` 缺失，rbs-core 模块边界无法确定 | 需前置确认 | 模块边界是 ASIS 唯一依据；缺失导致 AR-1 分析切片无法定义，TOBE 无法定位 rbs-core 受影响区域，AICoding 无边界约束可依 | `SR-design.md` 1.2 亦记录「仓库无 `software_architecture.md`」 | 上游设计 / 仓库负责人 |

### C6.2 ASIS 阻塞项

| 阻塞项 | 阻塞原因 | 已完成分析范围 | 不能确认的结论 | 需要补充的输入 | 对 TOBE/AICoding 的影响 |
|---|---|---|---|---|---|
| ASIS-阻塞-1 | `.sdd/software_architecture.md` 不存在，不满足 skill「模块边界规则」第 2 条，触发立即中断 | 阶段 1：读取原始需求与 SR 设计、核验工作区文件清单、确认架构文档缺失 | rbs-core 模块边界；AR-1 需求切片；验签入口/算法分派/用户公钥登记/配置/测试现状 | 提供 `.sdd/software_architecture.md`，并显式声明 rbs-core（及相邻模块）边界 | TOBE 不得基于本文件推进依赖 rbs-core 边界的 AR-1 详细设计；Gate 无 ASIS 结论编号可采样 |

## C7. 证据索引

| 编号 | 证据类型 | 位置 | 检索方式 | 支撑结论 |
|---|---|---|---|---|
| E1 | 命令输出摘要 | `Test-Path .\.sdd\software_architecture.md` → `False`；`find . -iname "*software_architecture*"` → 无结果；`python .sdd/SR-1/preflight_asis.py no-arch` → `PREFLIGHT-OK: no-arch 前提成立（架构文档不存在）` | 直接执行命令 | C2, D1, C6.1, ASIS-阻塞-1 |
| E2 | 文档 | `.sdd/SR-1/SR-design.md:87`：「仓库无 `software_architecture.md`，缺少显式架构文档（详见第 10 章）；本设计以代码现状为架构基线。」 | 直接阅读 | D1, C6.1 |
| E3 | 文档 | `.sdd/SR-1/original-requirement.md:1-2`（SR-1 需求原文） | 直接阅读 | C1 |

## C8. 需求/AR 追溯矩阵

| 编号 | 需求/AR/功能点/影响点 | 本模块相关性 | ASIS 结论编号 | 证据编号 | 覆盖状态 |
|---|---|---|---|---|---|
| R1 | AR-1 SM2 用户认证：现有验签入口与算法分派 | 未判定（边界阻塞） | 无 | E1 | 待确认 |
| R2 | AR-1 SM2 用户认证：用户公钥登记链路 | 未判定（边界阻塞） | 无 | E1 | 待确认 |
| R3 | AR-1 SM2 用户认证：配置与测试现状 | 未判定（边界阻塞） | 无 | E1 | 待确认 |

未覆盖原因：模块边界未确认，ASIS 在阶段 1 中断，未进入事实查证；须先解除 ASIS-阻塞-1。
