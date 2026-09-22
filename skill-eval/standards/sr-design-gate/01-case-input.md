你使用 sr-design-gate skill，对下面这份已经写好的 SR 设计文档执行 SR 设计门禁检查。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【待检查的输入（均已就位，直接读取，不要修改）】
- 原始需求：.sdd/SR-1/original-requirement.md
- 待检查的 SR 设计：.sdd/SR-1/SR-design.md
- 架构基线：本仓库没有软件架构文档，按 skill 规定处理该情形

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，没有人类在旁回答问题。sr-design-gate 前置工作流确认环节请跳过：不要回调 aaw-workflow，不要选池，直接执行该 skill 正文。
2. 本环境不提供 question-tracker MCP。不要真正调用工具、不要等待回答。
3. 严格按 sr-design-gate skill 正文执行：逐个准入维度判定 达标/未达标/不适用，按 gate-checklist.md
   及其 crypto-gate-checklist.md 定级 P0/P1/P2，给出结论与建议。

【输出要求】
1. 把完整的门禁报告写入 .sdd/SR-1/SR-design-gate.md。报告中的每个维度判定与每条冲突都必须写明依据
   （引用被检查文档的章节/位置或检查清单条款），不得只有结论。
2. 把门禁结论按 sr-design-gate skill 的数据契约写入 .sdd/SR-1/gate-data.json，字段为：
   gate_result（pass / fail / blocked）、recommendation、report（恒为实际报告路径，不得为 null）、
   summary（含 unqualified_dimensions、p0_conflicts、p1_conflicts、p2_findings、
   pending_questions、blocking_issues 六个计数）。
3. 最后回复：给出报告路径与 gate_result，并逐条列出你判定的未达标维度及其理由。
