# AAW Skill Eval

AAW Skill Eval 是本地 AI Agent Skill Benchmark 平台。新版以固定测试套为入口，
通过 Chrys 生成可编辑用例草稿、隔离校验，保存后锁定用例与项目地址。
每次只执行当前 Skill，以指定历史执行作为基准，展示多维度分数、运行趋势、日志和证据。
生成、执行与评分模型分别配置；Agent 接口支持扩展其他提供方。

新版流程、前端构建和目录说明见 [Benchmark 平台说明](docs/benchmark-platform.md)。
下文旧 A/B 接口说明保留供脚本参考，新界面不提供 Codex 配置。

创建测试时，“软件开发”和“文档与分析设计”两组固定维度同时可选。
维度名称、代码／LLM／混合评价方式、核心检查点、检查权重和评分档位由系统统一规定，
不能自定义。软件开发增加“架构约束符合性”，通过代码检查依赖方向、模块边界和循环依赖。
每个维度分别导入目录／ZIP 用例包；用户可配置任务、项目约束、参考材料、验证脚本、
用例与维度权重及硬门禁。相同场景可由多个维度共用一次 Agent 执行。
页面提供每个固定维度的用例模板，保存时固化标准版本和全部文件快照。
AAW 场景声明 `sr/ar/dev` 入口；流程结束后联合评价保留的文档、代码和验证记录。
流程未完成、门禁不通过或任务验证记录缺失时不能显示正常完成；不保存阶段快照。
详见 [用例包格式与评分规则](docs/test-packages.md)。已有自由维度和旧版套件标记为旧版，
继续使用原定义运行；新建 API 只接受固定标准套件。

## 启动

```powershell
cd skill-eval
python -m pip install -e ".[test]"
aaw-skill-eval
```

浏览器访问 `http://127.0.0.1:18110`。服务默认只监听本机。

数据保存在 `skill-eval/.skill-eval-data/`。可通过环境变量
`AAW_SKILL_EVAL_DATA_DIR` 指向其他目录。

## Runner 与 Judge

- Codex 与 Chrys 都可独立担任 Runner 或 Judge；仅安装其中一个也可以运行；
- 声明 `workflow` 的 AAW 场景当前要求 Codex Runner，开启真实独立 Reviewer 能力。
  Chrys Runner 未提供 subagent，启动前明确拒绝这类场景；普通场景与 Chrys Judge 不受影响。
- Chrys 模型从 `chrys models --json` 自动加载，实验创建时会固化模型、Runtime 版本、
  Agent 配置哈希、隔离和评分配置；排队后配置发生变化会让实验明确失败；
- Chrys 会维护 `%APPDATA%\chrys\agents\AAW-Eval-Runner.yaml` 与
  `AAW-Eval-Judge.yaml`，不会修改用户的 Code 或 QA Agent；
- Chrys Runner 继承当前有效 Code Agent 的指令和脚本扩展，但关闭子 Agent、外部 MCP
  与 `ask_user`；Judge 不配置工具、Skill 或工作区访问；
- 仪表盘按 `Skill × 项目 × 完整 Profile` 展示最近得分，不混合不同 Runner、Judge、
  模型、版本或隔离配置的结果；历史 Codex 实验按 legacy Profile 继续展示。

## 当前范围

- 正式实验每组 3 次，快速检查每组 1 次；
- 项目必须是干净的 Git 工作区；
- Skill 以完整目录快照和 SHA-256 内容哈希标识；
- 执行 Agent 看不到预期效果、Rubric、隐藏验证器或其他组结果；
- 自动分、hard gate 与人工复核彼此独立保存；
- 可选执行时间计分：用例配置 `time_scoring`（`target_seconds` / `limit_seconds` / `weight`）后，
  run 总耗时线性折算为「执行效率」分量计入质量分（≤target 满分、≥limit 零分，超时未完成 0 分）；
  未配置不计分，历史实验不受影响；
- 实验详情提供固定的实时日志控制台：可查看实验准备与每个 run/重试的阶段、Runner、验证器和 Judge 输出，并支持通道筛选、暂停、搜索、复制和原始日志下载；
- 工作区现场默认保留在盘上，由用户在页面手动清理（run 卡与实验标题栏均有入口，显示占用大小）；
  取消/中断的实验现场随收尾自动删除，服务启动时清理数据库无记录的孤儿目录；
  清理只删除 workspaces/ 目录，实验记录、评分与证据包（artifacts/）永不因此删除；
- 仅基础设施错误允许由调用方重新排队，Agent 失败不会被静默丢弃。

## 安全边界

Codex 默认使用 `workspace-write` 沙箱、`approval_policy=never`、禁用网络、Web Search、
Apps、远程插件、自动安装 Skill 依赖和多 Agent。测试定义中的 setup、preflight 与
command grader 是用户明确配置的本地可信命令，运行前会在页面展示。
AAW 工作流场景仅对带 Skill 的 Runner 开启多 Agent，以满足 task-dev 的两名只读 Reviewer。

Chrys 使用一次性 Git 工作区和受管 Agent Profile 做软隔离，但 Chrys Runtime 当前
不提供与 Codex 等价的强制网络沙箱，因此页面会明确标记 `soft / uncontrolled`。
不要把不可信项目或需要严格断网的任务交给 Chrys Runner。
