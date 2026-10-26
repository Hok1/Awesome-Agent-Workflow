# Skill Eval

本地 AI Agent Skill Benchmark 平台。测试套固定业务任务、项目提交和共同评分标准；每次执行独立选择 `no_skill` 或某个 Skill 内容版本。可以先运行 no_skill 并设为基线，再运行 AAW 的不同版本，选择历史记录比较。

- 创建测试套时只输入名称，再进入用例配置。
- Chrys 分阶段生成任务与评价方式；预览、隔离校验、人工确认后锁定。
- 一次执行只测试一个候选；快速模式 1 Trial，正式模式 3 Trial。
- 执行产物与评分记录独立保存；重新评分复用冻结证据，不重新运行 Agent。
- 基线固定到具体评分记录；新评分不会悄悄改变旧基线。
- AAW 流程合规独立展示，不进入共同质量分或共同门禁。

## 运行

```powershell
cd skill-eval
python -m pip install -e ".[test]"
python -m aaw_skill_eval.cli
```

访问 <http://127.0.0.1:18110/>。使用已构建的 React 页面；前端修改后运行：

```powershell
cd skill-eval/frontend
npm ci
npm run build
```

开发模式可使用 `npm run dev`，API 代理至 18110。默认数据目录为启动目录下 `.skill-eval-data/`，可用 `AAW_SKILL_EVAL_DATA_DIR` 指定。模型及凭证来自本机 Chrys；Designer、Runner 和 Judge 的模型分别配置。

## 数据与升级

Runner 每轮 Agent 对话的硬超时默认 180 分钟，通过
`AAW_SKILL_EVAL_RUNNER_TURN_TIMEOUT_SECONDS=10800` 配置（修改后重启服务）。
此预算独立于执行配置中的无活动超时（默认 30 分钟），自动确认后的后续轮次同样适用；
不改变 Judge 的评分预算，也不会自动恢复已超时的执行。

新版使用 `skill-eval-v2.db` 和 `v2/artifacts`、`v2/workspaces`。首次启动只从旧 `skill-eval.db` 导入测试套/草稿定义，不导入执行历史。导入内容均为待确认草稿，需检查业务目标与 Skill 专属要求、重新校验并锁定。旧数据库与证据保留在原位置，不再作为新界面的运行数据。

## 模块与验证

- [产品流程、API 与迁移说明](docs/benchmark-platform.md)
- [模块架构与扩展方式](docs/modular-architecture.md)
- [用例包格式](docs/test-packages.md)

```powershell
cd skill-eval
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe -m ruff check src
cd frontend
npm test
npm run build
```

目前内置 Chrys 适配器，旧 Codex 实现和静态页面已下线。Chrys 使用临时 Git 工作区和独立配置目录，关闭自动加载用户/项目 Skill；仅在选择 Skill 时安装指定内容快照。这是软隔离，网络权限取决于运行时。项目准备与代码检查使用用户确认的本地可信命令。
