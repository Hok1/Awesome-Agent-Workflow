产出 .sdd/SR-1/AR-1/rbs-core/tasks-overview.md，且：

- 遵循 overview_template.md 骨架（元信息/执行规则/串行执行顺序/任务计划/存疑汇总/
  待处理用例登记/执行记录）。
- 任务计划表六列齐全（编号|任务|做什么|改哪些文件|验证哪些用例|前置），
  编号 T1 起连续且与执行顺序一致。
- 不生成任何独立 T[N]-*.md 任务文件。
- 测试设计中的每个 TC 编号都有任务承接（覆盖完整）。
- 存疑汇总无未决项（存疑不放行）。
- 三份输入不被改写。

依据：task-split SKILL.md 拆分原则、任务计划边界、Phase 1-4、overview_template.md。
