# AI Agent Skill Benchmark Platform

## 产品流程

首页以测试套为入口，而不是以单次实验为入口。测试套卡片展示指定历史基准、最新执行分数、状态和能力雷达图；支持搜索、筛选、排序、分页、归档及恢复。

首页点击创建测试套，通过紧凑弹框只填写名称，立即保存待配置草稿并留在首页显示卡片。待配置卡片参与搜索、创建时间排序及分页，可筛选“待配置”；点击“去配置”进入用例配置页，刷新仍保留卡片和已保存内容。

用例配置页填写干净 Git 项目、目标 Skill、需求和固定评价维度，使用独立的生成模型与 Chrys 对话，或按维度导入目录/ZIP。Agent 读取项目副本和 Skill 副本，在独立目录产出真实场景、参考材料及验证代码。平台通过原有标准包导入协议编译，不接受 Agent 改写核心评分标准。

同一场景跨维度共享时，任务、输入文件、预期和流程配置必须一致；只执行一次，分别评分。草稿支持多轮生成与编辑，异步任务期间锁定编辑；revision 防止过期请求覆盖内容。服务重启会将未完成生成/校验标记为中断，保留草稿。

隔离校验克隆固定提交的项目副本，并按正式执行协议运行 Setup 和验证脚本。评分脚本位于独立 evaluator 目录，使用 `AAW_WORKSPACE` 读取被测项目、`AAW_FINAL_RESPONSE` 读取最终回复。没有候选产出的预检中最终回复为空。正常质量失败必须输出低分 JSON 并退出 0；异常退出、JSON 协议错误、缺失检查点或权重改变不能通过试验证。校验只证明结构与脚本可运行，不证明断言合理或 Skill 已通过。用户检查并确认有效性后点击保存测试套。

正式保存锁定项目地址、用例、维度和阈值；需要修改时复制为新草稿。保存和草稿锁定在同一数据库事务完成。保存不自动执行。

执行页使用 Chrys 的执行模型和独立评分模型，仅运行当前 Skill。快速模式 1 Trial，正式模式 3 Trial。每次执行保留项目提交、Skill 内容版本、测试套定义和完整模型/运行配置快照。页面可停止执行，切换历史记录，逐维度查看用例与评分项、Trial 证据、日志和产出文件。硬门禁位于结果对照中，默认折叠；用例定义默认隐藏。

用户选择本套件的执行记录及结果组作为对比基线：Skill 执行（`current`）或已有的无 Skill 结果（`no_skill`）。所选组必须 Trial 齐全、评分完整且门禁通过；新执行仍只运行当前 Skill，不因选择基线而额外执行无 Skill。基线以 `baseline_experiment_id` 与 `baseline_group` 持久保存，旧指针默认指向 `current`。

总分、分差、雷达图、维度、评分项和门禁均比较本次执行与同一所选基线；未选择时只显示本次结果，不额外固定展示无 Skill 列。项目提交、用例定义、运行配置或 Trial 模式变化时，分差作为参考，不给正式提升结论。不完整结果保留暂定得分并标识状态。用例 Pass 要求关联维度全部达到各自阈值且门禁通过；执行错误与未完成分别标识。

测评用例是完整任务，单独展示一次需求、参考材料与预期结果，默认收起；一个任务执行后可由多个维度分别评价。单用例的结果层次为“评价维度 → 检查项 → Trial 评分与证据”，不在各维度内重复嵌套用例定义。多用例时保留用例名称以区分评分来源。

归档保留测试套和执行记录，支持恢复；有活动执行时需要先停止。已有旧数据兼容不是本次验收要求。旧接口暂保留供脚本使用，新界面不提供 Codex 配置。

## 代码目录

```text
skill-eval/
├─ frontend/                         React + TypeScript 应用与构建
│  ├─ src/pages/
│  │  ├─ Dashboard.tsx              测试套管理
│  │  ├─ SuitePage.tsx              执行分析及只读用例设置
│  │  └─ DesignerPage.tsx           草稿、生成、导入、校验、保存
│  ├─ src/components/               shadcn 风格 Radix 基础组件与业务组件
│  │  ├─ TestSuiteCard.tsx
│  │  ├─ ScoreRadar.tsx             Recharts 雷达图
│  │  ├─ EvaluationChart.tsx        Recharts 历史柱状图
│  │  ├─ TestCaseList.tsx           维度→用例→评分项→Trial 证据
│  │  ├─ AgentChat.tsx
│  │  ├─ ProgressSteps.tsx
│  │  └─ ExecutionLog.tsx
│  └─ src/lib/                      API 与用例判定
├─ src/aaw_skill_eval/
│  ├─ benchmark.py                  测试套聚合、历史基准、草稿任务及归档 API
│  ├─ models.py                     SuiteDraft、归档与历史基准指针、执行模式
│  ├─ database.py                   增量数据库迁移
│  ├─ services/catalog/designer.py  包编译、Chrys 设计 Agent、隔离校验
│  ├─ services/providers/
│  │  ├─ __init__.py                Runner / Judge 工厂与公开注册函数
│  │  └─ registry.py                AgentRuntime 扩展协议
│  ├─ services/orchestration/       复用执行管线，支持 current_only
│  └─ static/benchmark/             构建产物，由 FastAPI 提供
└─ tests/test_benchmark.py           新流程的集成测试
```

## 接入其他 Agent

实现既有 `Runner` 与 `Judge` 契约，以及 `AgentRuntime` 的 runtime payload、模型配置 snapshot、snapshot verification；通过 `register_provider` 注册。需要用例生成时另外实现 `DesignerAgent.generate`，注册到 `DESIGNER_PROVIDERS`，输出统一的维度包。Chrys 使用已有 ACP transport；其他 Agent 不必使用 ACP。编排不依赖模型品牌。

当前交付的界面默认使用 Chrys；后续新增 Agent 时，从 `/api/v1/benchmark/agents` 获取可用角色与模型列表。Codex 后端代码保留为旧脚本兼容路径，不属于新产品流程。

## 构建与运行

```powershell
cd skill-eval/frontend
npm ci
npm run build
cd ..
.venv/Scripts/python.exe -m aaw_skill_eval.cli
```

构建产物包含在 Python 包中，不需要生产环境另起 Node 服务。开发可运行 `npm run dev`，代理 API 到 `127.0.0.1:18110`。已有原生前端源码保留用于旧测试参考，根页面优先提供 React 构建产物。

Chrys 的运行时可用不代表每个模型 Profile 的凭证可用；错误会显示在生成对话或执行结果中。默认选中当前激活的模型 Profile。
