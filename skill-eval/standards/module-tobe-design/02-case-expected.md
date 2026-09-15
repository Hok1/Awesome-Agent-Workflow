产出 .sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md，且：

- 按 tobe-output-template.md 的 9 个一级章节组织（需求背景/外部依赖/整体方案/
  模块详细方案/对外接口/数据库表设计/受影响模块与交互/关键契约清单/附录三方件约束）。
- 不暴露 ASIS 过程性内容（证据编号表、检索过程、追踪矩阵等）；引用 ASIS 事实用
  结论编号（A1–A16 范围内）建立追踪。
- 不含测试用例编号、AICoding 任务拆分、大段可实现代码（TOBE 职责禁区）。
- 承接 ASIS 已查明的现状契约标识符（如 SUPPORTED_ALGORITHMS、auth_value、
  validate_and_derive_alg、BearerTokenVerifier），不概括丢失。
- 含 TOBE 状态字段（完成/部分完成/阻塞）。

依据：module-tobe-design SKILL.md 成果物协作规则、职责边界、§4.1 大纲要求、阻塞规则。
