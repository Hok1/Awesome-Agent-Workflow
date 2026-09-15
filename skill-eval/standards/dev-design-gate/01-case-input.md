你使用 dev-design-gate skill，对 SR-2 的轻量设计执行准入门禁。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【输入（已就位，直接读取，不得修改）】
- 轻量设计：.sdd/SR-2/dev-design.md
- 测试设计：.sdd/SR-2/test-design.md
- 需求原文：.sdd/SR-2/requirement.md

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，由 aaw-workflow 工作单调用，没有人类在旁。前置的工作流确认环节跳过；
   需要用户确认的问题按 skill 规定处理，不要等待回答。
2. 本环境不提供任何 MCP 工具。网络不可用。
3. 严格按 skill 正文规定的 3 项准入检查、结论判定与报告骨架执行；
   本环境无 aaw CLI——data_schema 回传跳过，只在报告中如实给出统计数字。

【输出要求】
1. 按 skill 的产物契约把门禁报告写入对应路径（SR=SR-2）。
2. 最后回复：给出报告路径、结论、建议、未达标项清单。
