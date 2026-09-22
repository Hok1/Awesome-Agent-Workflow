你使用 module-design-gate skill，对 rbs-core 模块的 SR-1/AR-1 设计三件套执行模块设计门禁。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不得修改）】
- 正式说明书：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md
- 测试设计：.sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md
- 详细设计上下文：.sdd/SR-1/AR-1/rbs-core/.context/详细设计上下文.md
- 上游反查基线：.sdd/SR-1/SR-design.md、.sdd/SR-1/AR-1/AR-clarify.md
- 原始需求：.sdd/SR-1/original-requirement.md

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过；
   需要用户或上游确认的问题，按 skill 规定处理，不要等待回答。
2. 本环境不提供任何 MCP 工具。网络不可用。
3. 严格按 skill 正文规定的强制工作步骤、八维度准入与结论/建议枚举执行。

【输出要求】
1. 按 skill 的产物契约把门禁结果写入对应路径（SR=SR-1，AR=AR-1，模块组名=rbs-core）。
2. 最后回复：给出结果路径、门禁结论、门禁建议、未达标维度清单。
