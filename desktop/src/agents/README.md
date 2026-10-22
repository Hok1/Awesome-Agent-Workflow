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
  - 解析走严格的宽收窄（缺关键字段整条丢弃），版本不匹配 / 读不到一律
    返回空；
  - 返回空**不等于**「该 agent 没有会话」，调用方不得据此清空任何缓存
    （见 `ui/workbench/sessionHistory.ts` 的「只补不覆盖」）；
  - 有大小上限保护，超限不解析。
    接入第二个 agent 时，这里应当升成 `AgentAdapter` 上的一个可选能力
    （如 `listSessionHistory?`），而不是再加一个并列模块。
- **chrys 是第一个注册项**，其行为以
  `D:/dev/workspace-ai/chrys/src/chrys/app/acp/server.py` 为权威：
  `initialize` 返回的 agentCapabilities 含 `loadSession`、
  `promptCapabilities.embeddedContext`、`mcpCapabilities.http`、
  `sessionCapabilities.{close,list,additionalDirectories}`。

## 扩展方式（本项目的硬性要求）

接入第二种 agent = 在注册表加一个 `AgentAdapter` 项 + （若该 agent 有
私有扩展）在注册项里提供 `createDialect` 方言钩子（协议层的 `AcpDialect`
挂接点：通知翻译返回 null 则交回协议层兜底，反向请求按 method 精确
匹配）。`src/acp` 协议层与 `src/ui` 一行不改。

## 边界

- 不实现 JSON-RPC 收发细节（那是 `src/acp`）；
- 不直接 spawn 进程：产出启动描述，由 acp 层执行；
- 不依赖 UI / store。
