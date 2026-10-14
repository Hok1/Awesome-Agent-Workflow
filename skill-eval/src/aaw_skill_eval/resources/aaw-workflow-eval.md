---
name: aaw-workflow-eval
version: "1.0.0"
description: AAW sr/ar/dev 三入口的自包含测评适配，联合交付文档、分析设计、代码及流程验证记录。
---

# AAW Workflow Eval

用于隔离评测。整个目录及 vendor 是一个候选快照。先完整读取 `vendor/aaw-workflow/SKILL.md`，遵守真实工作流语义。

## 依赖与环境

- 所有子 Skill 均从 `vendor/<工作单 Skill 名>/SKILL.md` 加载，相对资源从对应目录解析。这里包含 sr/ar/dev 的全部节点依赖，以及文档、图表和问题追踪辅助资源。禁止从宿主 Skill 目录或网络加载其他版本。
- CLI 使用 `python <本目录>/vendor/aaw-workflow/scripts/aaw.py ...`，需要预先安装 typer、pyyaml。不要用 uv 临时联网安装，不运行 update。
- 每个 CLI 进程必须继承 `AAW_UPDATE_CHECK=off`、`AAW_TELEMETRY_ENABLED=false`；执行前核实。另写 `.aaw/telemetry.yaml` 为 `enabled: false`。
- question-tracker MCP 可用时按子 Skill 原协议调用；不可用时严格遵循其连续失败降级规则，并保留降级记录，不能伪造 MCP 返回。不能通过声明评测环境跳过澄清、门禁或验收。
- task-dev 要求两个独立只读 Reviewer。必须实际调用 subagent，并保留报告及引用；运行时没有此能力则明确报告阻塞。

## 场景与执行

读取任务中声明的 `entry`、SR、AR 与需求，不默认把 sr/ar 转成 dev。将需求保存为 `.sdd/<SR>/requirement.md`。

按入口启动真实 CLI：

```text
python <本目录>/vendor/aaw-workflow/scripts/aaw.py start --entry <sr|ar|dev> --sr <SR> --json
```

sr 入口额外传 `--requirement-file .sdd/<SR>/requirement.md`。ar 入口额外传 `--ar <AR> --title <需求描述>`，必须使用场景提供的 `.sdd/software_architecture.md`。其他参数以实际 CLI 帮助与工作单为准。

循环 `next → 完整读取工作单及子 Skill → started → 交付件检查 → done`，使用 CLI 给出的命令，不自造状态、跳过步骤或直接改 workflow.yaml。设计门禁失败时按原流程修正；task-dev 按真实 phase 指引完成实现、独立 Review、修复重验、CodeCheck 和交接。

CLI 返回 `awaiting_user_confirm` 时，汇报已完成步骤、待放行步骤及交付件，在最终回复末尾单独输出 `AWAITING_EVAL_CONFIRM`，停止本轮。只有收到后续确认回复，才执行 CLI 提供的 `commands.user_confirm`。同一流程可多次确认。

工作流 `status=done`、全部步骤 finished、没有待确认，并且任务验证证据完整才可报告完成。保留最终文档、代码、测试、workflow.yaml 和 task-dev 报告。不要提交或推送 Git。最终回复列出交付件、实际验证命令及结果、降级或残余风险。
