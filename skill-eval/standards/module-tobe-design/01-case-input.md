你使用 module-tobe-design skill，基于已完成的 ASIS 现状分析，对目标模块做 SR-1 需求的 TOBE 详细设计。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不要修改）】
- 原始需求：.sdd/SR-1/original-requirement.md
- 上游 SR 设计：.sdd/SR-1/SR-design.md
- ASIS 现状分析：.sdd/SR-1/AR-1/rbs-core/.context/详细设计上下文.md
  （16 条 ASIS 结论、47 条证据，覆盖验签入口、算法分派、公钥登记、配置与测试现状）

【本次设计任务】
- 目标模块：rbs-core（rbs/core/）
- 设计范围：SR-1 中 SM2 用户认证与公钥登记的 rbs-core 侧目标设计——验签算法分派扩展、
  公钥登记链路扩展、配置兼容，以及相关的失败语义、风险与可测试性输入
- SR=SR-1，AR=AR-1（SM2 用户认证），模块组名=rbs-core

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过，
   不要回调 aaw-workflow；执行中需要用户或上游确认的问题，按 skill 规定处理，
   不要等待回答。
2. 本环境不提供任何 MCP 工具。网络不可用。
3. 严格按 skill 正文规定的流程与产物契约执行。

【输出要求】
1. 按 skill 的产物契约产出到对应路径（SR=SR-1，AR=AR-1，模块组名=rbs-core）。
2. 最后回复：给出产物路径、TOBE 状态、输出模式与主要设计决策清单。
