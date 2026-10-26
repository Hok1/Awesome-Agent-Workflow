# Benchmark 平台流程

## 测试套与执行对象

测试套保存业务任务、参考材料、预期结果、固定评价维度、验证脚本、项目地址和创建时提交。软件开发及文档与分析设计维度可以组合，同一个完整任务只执行一次，各维度评价同一份产出。维度标准、核心检查项和评分档位由平台规定。

创建时只需名称，首页即出现待配置卡片。配置中的 Skill 路径是可选设计参考，不决定之后的执行对象。配置锁定后不可原地修改，修改需复制成新草稿。

每次执行选择：

| 选择 | 行为 |
| --- | --- |
| no_skill | 相同业务任务、Runner、模型及基础工具，不加载任何 Skill |
| Skill 路径 | 导入目录内容快照，记录内容哈希，再执行 |
| 已保存 Skill 版本 | 使用所选历史快照，不读取当前目录的新内容 |

快速模式执行 1 Trial，正式模式 3 Trial。一次执行只有一个候选，不附带无 Skill 对照运行。更新 Skill 后再次选择路径，会保存新内容版本。项目始终从测试套锁定的提交克隆。

## 用例设计

顶部持续展示四步：分析项目 → 设计用例 → 配置评价方式 → 确认使用。保留对话和结构化预览，各阶段、各维度显示状态与耗时。

先发布完整任务草案，再逐维度准备评价方式。LLM 维度采用固定规则；代码/混合维度独立生成脚本、隔离试运行。内容错误最多局部修复两次，成功维度不重做。超时、连接失败可停止/重试；普通讨论不取消正在生成的脚本。操作 ID 与 revision 防止旧任务或过期请求覆盖新内容。

校验克隆固定项目，运行 Setup 与检查脚本。脚本通过 `AAW_WORKSPACE` 和 `AAW_FINAL_RESPONSE` 读取产出；预检没有候选最终回复。低分但协议正确属于有效检查，不因低分自动降低标准。校验仅证明结构和脚本协议有效，用户仍需审核断言。确认后锁定，不自动执行。

## 执行、评分和基线

```text
固定测试套
├─ Execution 1：no_skill       → Assessment 1（可设为基线）
├─ Execution 2：AAW 内容版本 1 → Assessment 2
│                            └─ Assessment 3（重新评分）
└─ Execution 3：AAW 内容版本 2 → Assessment 4
```

执行记录保存候选、模型/运行环境、项目提交、Trial、Agent 输出和冻结证据。评分记录保存 Judge 配置、每个 Trial 的评分状态、分数、日志和证据引用。重新评分只新增 Assessment；执行次数及趋势中的运行条目不会增加。评分启动/执行失败不改写 Agent 已完成状态。

基线指向 `baseline_experiment_id` 和 **`baseline_assessment_id`**。可以选择任何符合完整性要求的历史评分，包括 no_skill、旧 Skill、新 Skill；重新评分不会移动基线。总分、雷达图、维度及评分项均与同一基线比较。项目、用例、模型/环境配置、Trial 模式不一致时仅展示参考分差。评分不完整时显示有效的部分维度，不把缺失评分当作零分。

结果页面保留紧凑布局：能力图/趋势图 → 测评用例（默认收起，只出现一次）→ 结果对照（维度展开检查项、评分、证据）。共同门禁在结果对照中；AAW Reviewer/工作流合规单独展示，不改变共同质量分及共同门禁。

## 失败恢复

- **重新执行**：从相同测试套、项目提交及候选快照重新运行，创建新执行，保留旧记录；刷新运行环境快照。
- **重新评分**：读取已完成 Trial 的冻结证据和确定性检查结果，不运行 Runner、Setup 或验证器。源证据哈希不符会拒绝评分。
- **评分版本选择**：查看同一次执行的任一历史评分，可独立设为基线。
- **服务重启**：排队任务恢复；活动执行和评分分别标记中断，保留可恢复的证据。执行完成但尚未开始评分的中断也记录为评分失败，可重新评分。

Judge 按评价维度最多并发两组，默认单维度 300 秒、单 Trial 整体 900 秒。每维度保存进度、输入规模、文件选择、耗时及错误；允许一次全文证据补充。相同模型配置、判据及证据指纹才复用成功维度缓存，更换模型会重新评分全部 LLM 维度。两名 AAW Reviewer 使用独立只读上下文，模型跟随 Runner。

## HTTP 边界

保留 `experiments` 作为执行的 API 路径名称；它不再表示配对 A/B 执行。

| 接口 | 职责 |
| --- | --- |
| `POST /api/v1/benchmark/drafts` | 名称创建草稿 |
| `/api/v1/benchmark/drafts/{id}/messages` | 分阶段设计与对话 |
| `POST /api/v1/benchmark/suites/{id}/execute` | `candidate_kind`、`skill_path` 或 `skill_revision_id` 启动执行 |
| `GET /api/v1/benchmark/skill-revisions` | 可复用的候选快照 |
| `GET /api/v1/experiments/{id}?assessment_id=...` | 指定评分的结果投影；省略时使用最新评分 |
| `POST /api/v1/benchmark/suites/{id}/experiments/{execution}/rejudge` | 新增评分；返回原执行 ID 与新 assessment_id |
| `POST /api/v1/benchmark/suites/{id}/experiments/{execution}/retry` | 新增执行 |
| `POST /api/v1/benchmark/suites/{id}/baseline` | 固定执行及评分 ID |
| `/api/v1/benchmark/assessments/{id}/runs/{run}/logs` | 评分日志 |
| `/api/v1/benchmark/assessments/{id}/runs/{run}/artifacts` | 评分产物 |

## 数据切换与回退

新版数据库为 `.skill-eval-data/skill-eval-v2.db`，执行目录为 `v2/workspaces`，证据目录为 `v2/artifacts`。历史定义的迁移在单个事务中完成并记录版本，只执行一次；原数据库以只读方式打开。已保存测试套和未保存草稿均转为未确认草稿，保留原定义和迁移提醒，不复制历史执行。

导入后先检查任务/预期中是否夹带 AAW 指定目录、Reviewer 或入口等专属要求，把共同质量要求留在任务中，专属规则放到流程合规检查；勾选确认、重新校验、锁定后才能执行。迁移不会自动改写这些语义。

回退时先停止新版服务，恢复升级前源码及原 `skill-eval.db`，使用旧数据目录启动。新版数据库和 `v2` 目录单独保留；不要用新版数据库覆盖旧文件。升级前应保存源码和数据库备份，新旧服务不同时写同一数据目录。
