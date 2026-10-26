# 模块架构

采用模块化单体：一个 FastAPI 服务、一个 SQLite 数据库和一个 React 应用。以业务生命周期划分模块，Agent 与工作流是可替换适配器。

```text
skill-eval/
├─ src/aaw_skill_eval/
│  ├─ app/
│  │  ├─ main.py                 服务生命周期、React 静态资源
│  │  ├─ api.py                  组合业务路由
│  │  └─ composition.py          注册具体 Agent / 工作流实现
│  ├─ contracts/
│  │  ├─ schemas.py              输入与固定测试定义契约
│  │  ├─ http.py                 页面命令 DTO
│  │  ├─ agents.py               Runner / Judge 输入输出
│  │  ├─ providers.py            Designer / Runner / Judge 能力注册
│  │  ├─ workflows.py            可选流程合规扩展
│  │  └─ entities.py             模型统一导出与 ORM 注册
│  ├─ modules/
│  │  ├─ suites/                 固定测试套、包编译、校验、复制
│  │  │  ├─ models.py            Suite / SuiteDraft
│  │  │  ├─ service.py           保存测试套定义
│  │  │  └─ routes.py            测试套命令
│  │  ├─ designer/               分阶段设计、草稿修订、调度
│  │  │  ├─ planning.py          项目摘要和设计协议
│  │  │  ├─ jobs.py              阶段推进、局部修复、revision 防护
│  │  │  └─ dispatcher.py        后台任务与取消信号
│  │  ├─ executions/             候选与执行生命周期
│  │  │  ├─ models.py            SkillRevision / Experiment / Run
│  │  │  ├─ prepare.py           固定提交、候选快照、环境检查
│  │  │  ├─ execution.py         Runner、终态证据、确定性结果采集
│  │  │  ├─ scheduling.py        单候选 Trial 调度与原子领取
│  │  │  └─ skills.py            内容寻址的 Skill 快照
│  │  ├─ evaluations/            独立评分生命周期
│  │  │  ├─ models.py            Assessment / TrialAssessment
│  │  │  ├─ service.py           评分版本、冻结证据校验、错误状态
│  │  │  ├─ judging.py           按维度调度、超时、缓存
│  │  │  ├─ evidence.py          Judge 证据视图
│  │  │  └─ graders.py           确定性检查与分数组合
│  │  └─ results/                只读结果与比较
│  │     ├─ projection.py        执行 + 所选评分的展示投影
│  │     ├─ views.py             API 汇总
│  │     ├─ verdicts.py          用例/维度判定与聚合的唯一实现
│  │     ├─ comparison.py        可比性与分差
│  │     └─ commands.py          固定基线评分
│  ├─ adapters/
│  │  ├─ agents/chrys/           Designer、Runner、Judge、Runtime
│  │  ├─ agents/protocols/acp/   ACP 会话与事件协议
│  │  └─ workflows/aaw/         AAW 提示与流程合规证据
│  ├─ infrastructure/
│  │  ├─ database.py            数据库会话
│  │  ├─ migration.py           旧定义只读导入
│  │  ├─ jobs.py                执行→评分任务衔接、重启恢复
│  │  ├─ storage/               证据持久化、冻结哈希
│  │  ├─ workspace/             Git 克隆、路径、清理
│  │  └─ observability/         日志与会话读取
│  └─ static/benchmark/         唯一 Web 前端构建
├─ frontend/src/
│  ├─ app/main.tsx              路由、全局应用状态
│  ├─ features/
│  │  ├─ suites/                首页、测试套、完整用例
│  │  ├─ designer/              用例配置视图与 useDesigner
│  │  ├─ executions/            执行视图、useSuite、候选选择、日志
│  │  ├─ evaluations/           评分版本选择
│  │  └─ results/               雷达图、趋势图、结果对照
│  └─ shared/                   HTTP、轮询、展示基础组件
└─ tests/                       契约、业务集成、适配器与恢复回归
```

## 依赖规则

业务模块使用契约及基础设施，不直接引用 Chrys。只有 app/composition 注册具体实现。执行模块产出冻结证据，评分模块通过证据接口读取；结果模块投影二者，不修改执行事实。任务调度负责衔接生命周期，不能把 Judge 失败改写成 Agent 失败。

前端的 useSuite/useDesigner 管理请求、轮询及操作状态，页面负责布局。shared/polling 统一禁止请求重叠、支持销毁和终态停止。共同分数、Pass/Failed、维度完整性、门禁和比较由后端返回，前端只格式化展示。

现有 ORM/API 仍使用 Experiment/Run 命名，以维持明确的接口边界；其业务含义为单候选执行及 Trial，不再承担评分版本。

## 扩展 Agent / 工作流

1. 在 adapters/agents 下实现需要的角色。可以只提供 Runner、只提供 Judge 或只提供 Designer。
2. Runtime 提供模型快照、验证和能力信息；Runner/Judge 使用 contracts/agents 的输入输出，Designer 使用 plan/dimension 结构化设计协议。
3. 在 app/composition 调用 register_provider，仅注册实现的能力。通用调度、缓存、评分计算不放进具体模型适配器。
4. 工作流专属提示与合规规则通过 contracts/workflows 注册；不可把专属规则自动加入共同评分或 no_skill 提示。
5. 新增适配器契约测试及集成测试。页面当前默认 Chrys，新增产品选择入口时再暴露新角色能力。

## 关键验证

`test_modular_benchmark.py` 验证 no_skill → Skill v1 → Skill v2、执行和重评分独立计数、基线评分固定、迁移保护、证据篡改拒绝及 AAW 合规不影响共同分数。原有固定标准、脚本协议、Chrys/ACP、阶段生成、取消/重启、缓存与清理测试继续覆盖底层行为。

移除只验证旧静态 DOM、成对 A/B 执行或 Codex 的测试；对应的新业务行为使用接口及状态测试验证。测试中的 FakeRunner/FakeJudge 验证平台生命周期，不替代真实外部模型端到端测评。
