# chrys 工作流驱动器

本目录存放 AAW 适配 chrys 工作流模式（Workflow mode）的四个驱动器文件。它们由
`generate.py` 生成——共享同一套路由机制，只有阶段节点列表不同。修改机制时改
`generate.py` 后重新运行 `python generate.py`，不要手改生成物。

## 文件与覆盖范围

| 文件 | 阶段 | 适用入口 |
|---|---|---|
| `aaw-sr-design.py` | sr-init → sr-design → sr-design-gate → ar-split | sr |
| `aaw-detail-design.py` | ar-init → ar-clarify → module-boundary-design → detail-design-split → asis → tobe → test-design → module-design-gate | sr（第二段）/ ar（全程） |
| `aaw-code-dev.py` | task-split → task-dev（含 dev-task-split / dev-task-dev） | 所有入口（尾段） |
| `aaw-dev-design.py` | dev-init → dev-design → dev-test-design → dev-design-gate | dev |

每个文件里，图上一种阶段只有一个节点；多个 AR / 模块 / 任务通过路由循环反复经过
相同节点，图的大小与工作量无关。

## 工作原理

```
prep（python）→ negotiate（agent，与用户协商目标）→ pipeline 循环：
  router（python） --switch--> 各阶段 agent 节点 --join--> reporter（python）
        ^                                                        |
        +-------------------- loop until done --------------------+
```

- **prep + negotiate**：run 启动时先由协商 Agent 用 ask_user 与用户自由对话，弄清本次
  目标后输出一行严格格式的决策（`decision:continue/create/rollback/cancel`）。模糊的
  意图理解交给 agent，代码只执行它决定好的动作。
- **新建在 run 内完成**：协商 Agent 收集入口所需信息（sr 入口的原始需求原文、ar 的
  编号与描述、dev 的 SR 号），router 调 `aaw start` 创建并回显核对，全程不需要聊天
  模式配合。回退同样在 run 内：选步骤 → 预览 → preserve/discard 确认 → 执行。
- **router**：调 `aaw next --json` 取当前工作单，组装执行简报，按首行 `step:<type>`
  路由到对应阶段节点；`awaiting_user_confirm` 弹窗问用户，noop/manual 步骤就地完成。
  提问的回答匹配不上选项时只重问一次，然后退向不动作的保守侧（暂停/取消），
  绝不替用户执行任何动作。
- **阶段 agent**：加载工作单点名的 skill 并执行；需要用户决策时用 ask_user；自己执行
  工作单给出的 done / next 命令（task-dev 按阶段机多轮推进）。
- **reporter**：每步后复查 CLI 状态决定循环是否继续；agent 输出 `AAW_STOP` 或 router
  返回 `control:` 前缀时结束 run。

所有持久状态都在 `.sdd/`（aaw CLI 是唯一权威）；chrys 的 run 是可抛弃的执行器，
中断后重新启动即从当前进度继续。`done_argv` 等命令里硬编码的 `python` 前缀会被替换
为运行时探测成功的运行器（uv / 当前解释器 / PATH python，需 typer + pyyaml）。

## 使用

1. `./install.sh --target chrys` 安装（workflow 文件进入 `~/.chrys/workflows/`，
   项目模式进入 `./.chrys/workflows/`）；
2. chrys TUI 打开 Workflows，选择对应段的驱动器，输入可留空（也可以写一句话意图，
   如「继续上次的」「新建一个 dev 的」）；
3. 启动后协商 Agent 会与你确认：继续哪个 SR / 新建（sr / ar / dev）/ 回退 / 取消；
4. 首次运行需在 TUI 里确认信任；run 结束后重新启动即从当前进度继续。

## 环境要求与边界

- chrys ≥ 0.25.2（agent 节点加载 skills 的能力）；结构化提问弹窗需要 ≥ 0.26.1（发布版 0.26.0 及更早上自动退化为纯文本提问，两者兼容）；
- 需要在 TUI（交互模式）运行：含用户确认的步骤在 headless 下无法执行；
- aaw CLI 位置探测失败时，用环境变量 `AAW_SCRIPT` 指定 `aaw.py` 绝对路径；
- run 活跃期间 chrys 全局互斥（不能同时开聊天 turn）；
- 协商 Agent 靠指令约束只用 ask_user（非沙箱级，与 chrys 内置 demo 的做法同级）；
  它输出不合 `decision:` 契约时 run 会带原样输出终止，不会误执行。
