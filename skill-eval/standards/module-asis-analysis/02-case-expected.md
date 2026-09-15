产出 .sdd/SR-1/AR-1/rbs-core/.context/详细设计上下文.md，且：

- 含 C1–C8 全部固定目录标题（无内容的章节保留标题并写明原因）。
- C2 模块边界确认标记为「declared by software_architecture.md」——边界只能来自
  .sdd/software_architecture.md，不得由代码结构推断。
- 结论有稳定编号（A1、A2……），证据有编号（E1、E2……）且可在 C7 证据索引反查。
- 产物引用的代码路径（rbs/core/...、rbs/rest/... 等）在仓库中真实存在。
- 未创建《模块详细设计说明书.md》（ASIS 阶段禁止）。
- C3 不含「建议采用」「可以复用」「应新增」等 TOBE 拍板表述（实现方案只能记为
  「TOBE 决策输入」）。

依据：module-asis-analysis SKILL.md 模块边界规则、阶段流水线、职责边界与质量标准。
