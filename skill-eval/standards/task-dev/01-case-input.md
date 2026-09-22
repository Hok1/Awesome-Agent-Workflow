你使用 task-dev skill，执行 tasks-overview 中的 T1 任务（SM2 验签能力与 Bearer 用户认证）。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace，Rust 工具链可用）。

【输入（已就位，直接读取；权威文档不得修改）】
- 任务计划：.sdd/SR-1/AR-1/rbs-core/tasks-overview.md（当前任务=T1，前置=无）
- 正式说明书：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md
- 测试设计：.sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md
- 门禁结果：.sdd/SR-1/AR-1/rbs-core/.context/模块设计门禁结果.md（结论：通过）
- 架构基线：.sdd/software_architecture.md

【本次执行方式（重要，请严格遵守）】
1. 单独执行（非 aaw-workflow 编排）：跳过状态命令与 done 回调，不读写任何 state.json；
   除此之外的流程与质量边界不变。
2. 无头执行，没有人类在旁；需要用户决策的问题按 skill 规定记录并停在安全状态，
   不要等待回答。
3. 本环境不提供任何 MCP 工具，网络不可用。
4. 本环境无法启动并行 SubAgent：语义 Review 环节由你自行以只读方式按两个视角
   （A：需求一致性/正确性/安全/兼容；B：性能/结构/可读性/过度设计）各出一份报告
   并落盘到 .sdd/SR-1/AR-1/rbs-core/.context/ 下。
5. 本环境无 code-check 扫描器：CodeCheck 环节执行 cargo 的构建/测试与仓库既有检查。
6. 严格按 skill 的固定流程执行；绝不执行 git add / git commit / push。

【输出要求】
1. 完成 T1 的实现与测试（范围见任务计划的「改哪些文件」「验证哪些用例」两列），
   受影响测试全部通过。
2. 按 skill 规定回填 tasks-overview.md 的执行记录（含必填小节）。
3. 最后回复：给出修改文件清单、测试执行结果、双视角 Review 结论、候选提交信息。
