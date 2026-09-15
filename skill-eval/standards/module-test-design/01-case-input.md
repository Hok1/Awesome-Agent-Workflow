你使用 module-test-design skill，基于已定稿的 TOBE 详细设计，为 rbs-core 模块的 SR-1/AR-1 做测试用例设计（严格模式）。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不要修改）】
- 原始需求：.sdd/SR-1/original-requirement.md
- TOBE 正式说明书：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md
- 详细设计上下文：.sdd/SR-1/AR-1/rbs-core/.context/详细设计上下文.md
  （含 ASIS 证据与 TOBE 推导、追踪矩阵）

【本次任务】
- 严格模式（SR/AR 入口）：把 TOBE 已定稿的设计目标、契约、流程、异常边界、风险和
  可测试性输入转化为可执行的最小充分验证集
- SR=SR-1，AR=AR-1（SM2 用户认证），模块组名=rbs-core

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过；
   需要用户或上游确认的问题，按 skill 规定处理，不要等待回答。
2. 本环境不提供任何 MCP 工具。网络不可用。
3. 严格按 skill 正文规定的模式判定、工作法与产物契约执行。

【输出要求】
1. 按 skill 的产物契约产出到对应路径（SR=SR-1，AR=AR-1，模块组名=rbs-core）。
2. 最后回复：给出产物路径、用例总数与分层分布、覆盖矩阵摘要、缺口清单。
