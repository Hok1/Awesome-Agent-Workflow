# src/agents — Agent 适配注册层

「协议」与「具体某个 agent」解耦的关键层：`src/acp` 只会说 ACP，
本层回答「这条 ACP 连接对面是谁、怎么启动、有什么 peculiarities」。

## 职责

- **适配器注册表**：一个 `AgentAdapter` 描述一种 agent——
  - 标识：`id`（如 `chrys`）、`displayName`；
  - 启动：`buildLaunch(context)` 产出 argv（chrys 即 `["chrys", "acp"]`）、
    额外 env、工作目录（真实运行 `src/ui/realRuntime.ts` 与冒烟脚本
    `scripts/acp-smoke.ts` 都从这里取启动描述，不手写 argv）；
  - 方言：`createDialect(hooks)` 产出协议层的 `AcpDialect` 挂接——私有
    通知翻译（如 `_chrys/*` → 类型化事件）与私有反向请求处理器
    （如 `_chrys/request_input` 结构化提问），见 `chrysDialect.ts`；
  - 初始化参数：`clientInfo.name`、capabilities 协商偏好。
- **展示名的单一来源**：`DEFAULT_AGENT_ID` + `defaultAgentLabel()`。
  界面文案需要指代「这一侧」时从这里取，不写死 `"chrys"`——写死的话，
  接入第二个 agent 时它们会散落成一批需要逐个找出来的硬编码。
- **历史会话索引**（`chrysSessions.ts`）：读 agent 自己的会话索引
  （chrys 为 `<sessions>/.cache/session_catalog.json`），把「这个项目
  有过哪些会话」提供给左栏树。这条读取**不需要 agent 进程**，因此树在
  项目未连接时也能显示历史。它是 agent 的私有格式，所以：
  - 索引缺失、损坏、版本不兼容或超限时，扫描直接子目录的 `session.json`，
    提取 `meta` 中的会话摘要；四路并发，坏文件单独跳过，不启动 ACP；
  - 兼容 `schema_version=1` 且缺少 `kind` 的旧版对话；显式非 chat 类型
    和缺少关键字段的记录不展示，按项目归组、会话 ID 去重、更新时间排序；
  - 返回空**不等于**「该 agent 没有会话」，调用方不得据此清空任何缓存
    （见 `ui/workbench/sessionHistory.ts` 的「只补不覆盖」）；
  - 有效空索引不触发扫描；连接后的 `session/list` 覆盖本地摘要，迟到的
    扫描不得覆盖该权威快照（含空列表）。
    接入第二个 agent 时，这里应当升成 `AgentAdapter` 上的一个可选能力
    （如 `listSessionHistory?`），而不是再加一个并列模块。
- **chrys 是第一个注册项**，其行为以
  `D:/dev/workspace-ai/chrys/src/chrys/app/acp/server.py` 为权威：
  `initialize` 返回的 agentCapabilities 含 `loadSession`、
  `promptCapabilities.embeddedContext`、`mcpCapabilities.http`、
  `sessionCapabilities.{close,list,additionalDirectories}`。

## 扩展方式（本项目的硬性要求）

接入第二种 agent 有**三种形态**，统一经 `resolveAgentAdapter(id, customAgents)`
解析为 AgentAdapter 形状的启动面（真实运行 realRuntime 与诊断页协议
探查 agentProbe 共用）：

1. **内置适配项**：在 `agentAdapters` 追加一项（见下）；
2. **本机发现**：`nativeAcpCandidates` 收录子命令直接说标准 ACP 的 CLI
   （如 `opencode acp`），设置页扫描 PATH 命中即用，无需改代码；
3. **自定义**：设置页分别填写程序或路径与启动参数，条目持久化在
   settingsStore（`CustomAgentEntry`）。OpenCode 和 CodeAgent 未填写参数时
   分别使用 `acp` 和 `--acp`；程序路径中的空格无需加引号。

上述方式均通过 stdio 连接 ACP agent；暂不支持通过 HTTP 地址连接 ACP。

内置项的扩展约束（docs/architecture.md「扩展第二种 agent」）：接入新
agent = 在 `agentAdapters` 加一个注册项；`src/acp` 协议层与 `src/ui`
一行不改。讲标准 ACP 的 agent 到此即完成；带私有扩展的 agent 在注册项
里提供 `createDialect`（协议层的 `AcpDialect` 挂接点），私有消息的解析
留在本层，同样不动协议层。

## 边界

- 不实现 JSON-RPC 收发细节（那是 `src/acp`）；
- 不直接 spawn 进程：产出启动描述，由 acp 层执行；
- 不依赖 UI / store。
