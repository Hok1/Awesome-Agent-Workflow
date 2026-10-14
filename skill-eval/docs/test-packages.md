# 固定维度与用例包

新建测试使用系统统一标准，当前目录版本为 `1`。用户选择适用维度，分别导入用例；不能新增、改名或修改评价方式、核心检查点、检查权重和评分档位。

| 维度分组（可同时选择） | 固定维度 | 方式 |
|---|---|---|
| 软件开发 | 功能正确性 | 代码 |
| 软件开发 | 回归兼容性 | 代码 |
| 软件开发 | 架构约束符合性 | 代码 |
| 软件开发 | 可维护性 | LLM |
| 文档与分析设计 | 内容完整性与约束符合性 | 混合 |
| 文档与分析设计 | 事实与证据质量 | LLM |
| 文档与分析设计 | 分析与设计合理性 | LLM |
| 文档与分析设计 | 表达清晰度 | LLM |

架构维度检查声明的依赖方向、模块边界与循环依赖，不评价整体架构选型。可维护性聚焦代码可读性、职责清晰度和修改便利性。

## 创建流程

1. 填写干净的 Git 项目、Skill 路径和套件名称。
2. 在软件开发、文档与分析设计两组中同时勾选适用维度，不再按 Skill 类型二选一。
3. 查看只读检查点和标准，下载该维度的用例模板。
4. 修改任务、初始文件、项目约束、参考材料及验证代码，导入目录或 ZIP。
5. 编辑场景与运行配置，调整用例权重、维度权重、硬门禁及阈值，确认保存。

导入与保存不执行脚本。最多 500 个文件、20 MB 内容。模板脚本是协议脚手架，默认检查得 0 分并明确标记尚未实现；必须替换为项目实际断言。平台校验检查点关联和结果协议，断言是否合理由用例作者负责。

## 用例包格式

包内必须有唯一的 `suite.json`、`suite.yaml` 或 `suite.yml`。配置版本为 `3`，标准版本与维度必须匹配。新套件 `skill_type=workflow` 表示联合选择；也接受此前单一分组的维度包，检查点标准不变。

```json
{
  "schema_version": 3,
  "catalog_version": 1,
  "skill_type": "workflow",
  "dimension_id": "architecture",
  "cases": [{
    "id": "architecture-scenario",
    "name": "遵守项目架构约束",
    "input": "阅读项目约束，完成指定修改。",
    "expected": "满足任务及项目声明的分层、边界和依赖规则。",
    "weight": 1,
    "files": {"constraints.md": "scene/constraints.md"},
    "graders": [{
      "type": "command",
      "command": "python validate.py",
      "result_format": "json",
      "checkpoint_ids": ["dependency-direction", "module-boundaries", "dependency-cycles"],
      "files": ["validate.py"],
      "setup_commands": [],
      "timeout_seconds": 300
    }]
  }]
}
```

`files` 将包内文件映射到 Agent 工作区。引用以配置文件所在目录为根，禁止绝对路径、上级目录和符号链接。支持包外层包含一个目录，未引用的文件不安装。

纯 LLM 维度的 `graders` 使用空数组，平台自动加入固定标准。混合维度只声明代码检查，平台自动补齐 LLM 检查。禁止导入自定义 Rubric、criteria 或评分档位；模板中的 `standard.json` 仅供阅读，修改它不改变系统标准。

代码可拆成多个脚本，分别声明覆盖的 `checkpoint_ids`。同一场景必须完整覆盖该维度代码检查点，不能重复或包含其他维度的检查点。

`expected` 是评测端参考材料，可补充项目约束和参考答案，也可用 `expected_file` 引用包内 UTF-8 文件。它不改变核心标准。Agent 只接收任务、初始文件、`agent_context` 和 `followups`。

## AAW 工作流场景

同一个场景可以同时导入开发与文档维度的用例包。场景 ID、任务、初始文件、`workflow` 和执行配置一致时只运行一次；冲突时必须修正配置或使用不同 ID。

场景增加以下配置：

```json
{
  "workflow": {
    "entry": "sr",
    "sr": "SR-EVAL-001",
    "confirmation_reply": "确认当前交付件并放行，按提供的需求继续。"
  },
  "max_turns": 30,
  "output_paths": ["src/service.py", "tests/test_service.py"]
}
```

`entry` 支持 `sr/ar/dev`。ar 必须另有 `ar` 编号，并在干净项目或场景文件中提供 `.sdd/software_architecture.md`；sr 的原始需求由适配 Skill 按真实 CLI 的 `--requirement-file` 协议提交。模板入口选择只影响下载，不覆盖已导入场景。

`confirmation_reply` 是用例作者明确提供的流程放行回复，仅在 `AWAITING_EVAL_CONFIRM` 标记出现时重复发送，受 `max_turns` 限制。没有配置时保留等待状态，不自动批准任意澄清。普通 `followups` 默认只使用一次；确需复用可设置 `repeat: true`。

使用当前仓库的自包含候选，避免只导入 aaw-workflow 而缺少其子 Skill：

```powershell
cd skill-eval
python scripts/build_workflow_adapter.py --repository .. --output eval-skills/aaw-workflow-eval-candidate
```

在新建测试的 Skill 路径填写输出目录。构建器打包当前检出的节点与辅助 Skill、生成依赖文件哈希，不联网更新，不覆盖已有候选目录。项目运行环境须预先有 Python、typer、pyyaml；应用环境已声明这些依赖，项目依赖仍通过 Setup 准备。

当前全流程执行要求 Codex Runner，独立 Reviewer 由真实 subagent 完成；Chrys Runner 缺少对应工具会在启动前报错。question-tracker MCP 的缺失必须遵守原 Skill 的失败降级协议并记录；不能伪造调用。

带 Skill 的候选和基准组检查 `.sdd/<SR>/workflow.yaml` 的入口、`status=done`、非空且全部 finished 的步骤、没有待确认、所登记的必需交付件、设计门禁及 task-dev 的实现、Review、重验、CodeCheck、交接记录。未完成标为 Agent 失败，保留分数和缺项证据，不参与有效 Trial 均值。无 Skill 对照组评价相同任务产出，不要求其生成 AAW 专有状态。

收集 Git 变更、声明的 `output_paths`、最终 `.sdd` 文档及验证记录，即使文件被 Git 忽略也保留。`terminal-evidence.json` 保存文本视图和清单；`terminal-outputs.zip` 保存文件。Judge 的文本视图最多 240000 字符、单文件读取最多 30000 字节；归档单文件上限 5 MB、总量 50 MB，超限在清单中标为未归档。原始工作区仍保留。只采集执行结束时的内容，不增加阶段版本快照。

流程状态和报告检查提供完成证据，不能代替代码断言与文档质量评价；用例包仍需提供实际需求、参考事实和项目级检查。

## 代码结果协议

支持任意语言，通过 `command` 声明入口。验证文件在 Agent 完成后安装到独立评测目录，`setup_commands` 在该目录准备依赖。项目依赖使用页面的全局 Setup／Preflight。

环境变量：`AAW_WORKSPACE` 是 Agent 工作区路径；`AAW_FINAL_RESPONSE` 是最终响应 UTF-8 文件路径。

脚本退出 0，stdout 输出完整 JSON，调试日志写 stderr：

```json
{"checks": [
  {"id": "dependency-direction", "score": 100, "weight": 1, "evidence": "依赖均遵守声明的层级方向"},
  {"id": "module-boundaries", "score": 50, "weight": 1, "evidence": "两项规则有一项违反，见 src/example.py:12"},
  {"id": "dependency-cycles", "score": 100, "weight": 1, "evidence": "模块依赖图没有循环"}
]}
```

结果必须恰好覆盖绑定的固定检查点，证据不能为空，权重符合系统定义。代码可返回 0–100 的满足比例。断言失败记低分，仍退出 0；非零退出、超时、缺失／额外检查点或无效结果标为评价失败，显示“不完整”。新固定维度不接受纯退出码检查。

## LLM、快照与汇总

页面以「评价维度 → 关联用例 → 评分项 → Trial 与证据」统一呈现。默认只显示全套件各维度的分数、权重与完成数；点击维度查看关联用例及各组用例分，用例分从该用例已完成 Run 的 `scores.dimensions` 求均值，不能替换为全套件分。只有一个关联用例时，直接展示评分项，减少一层展开。用例详情默认隐藏，输入、预期效果、初始文件、工作流与对话设置在第一层，完整评分配置再折叠一层。展开状态在同一实验的重渲染中保留，切换实验时重置。

主雷达图继续读取整个套件的评价维度汇总，与结果对照的父行使用同一数据和维度权重。硬门禁放在结果对照顶部，默认只显示各组状态，点击展开具体检查和关联用例的流程证据；失败 Run 的流程证据也可查看。门禁仍独立于质量评分，计算与历史分数不变。没有维度定义的旧版实验把用例快照移入结果对照，保留原评分项结果与雷达，并明确标注旧版与当前场景范围。

LLM 检查点、证据要求、权重和 0／60／100 档位由系统提供。各检查点有稳定评分项 ID，分别保存得分和证据；维度内加权均值可出现其他分数。LLM 返回档位外分数会标为评价失败。

保存时固化标准版本、维度定义、检查点、Rubric 和全部文件。实验与重试使用完整快照；后续标准更新或原文件变化不会改写已有结果。

验证文件和参考材料不复制到 Agent 工作区，也不加入 Runner 提示词。这是材料分离，可信命令仍以当前用户身份执行；Chrys 的软隔离不提供操作系统级访问限制。

计算顺序：代码检查项加权 → 场景内同维度检查加权 → 同场景 Trial 均值 → 维度内用例加权 → 维度加权总分。混合维度的代码与 LLM 各占一半，拆分脚本或检查点不改变比例。同一 ID 且任务、初始文件和执行配置一致的场景共用一次 Agent 执行，各维度可独立设置用例权重。

硬门禁维度不计入质量总分，每个关联场景都必须达到配置阈值。失败保留分数，但结论未达标；缺失或失败显示“不完整”，有效部分均值仅作临时参考。

## 旧版兼容

已有 v1／v2 套件没有固定目录版本，页面标记“旧版”，继续按原定义查看、运行和重试。新建 API 只接受固定标准，不能通过省略版本或维度定义创建自由评分套件。旧版 `time_scoring` 保留原逻辑，不与新固定维度总分混用。
