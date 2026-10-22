# src/acp — ACP 协议层

ACP（Agent Client Protocol）是 JSON-RPC 2.0 over stdio 的**行分帧**协议
（chrys 所用 Python SDK 读写两侧均为 readline，非 LSP Content-Length）。
本层是**与协议本身打交道的唯一地方**：进程怎么拉起、请求怎么超时、
通知怎么解析，全部收敛在这里。接入第二种 agent 时本层不动，只在
`src/agents` 加注册项。

## 文件结构（已落地）

| 文件                              | 职责                                                                                                                                                                                                                                                                                                            |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `types.ts`                        | chrys 方言线上类型：请求/响应、`session/update` 全部变体（以 chrys 实际运行的 Python SDK v0.12.2 为准）、`_chrys/*` 扩展通知、反向请求 payload。不 re-export JS SDK 类型（其 v1/unstable 已含 chrys 未发的 `plan_update` 等变体，方言有出入）                                                                   |
| `errors.ts`                       | 错误分类（machineCode 对齐 skill-eval Python 参考的 InfrastructureError 码）                                                                                                                                                                                                                                    |
| `framing.ts`                      | `LineDecoder` 行分帧：字节级找 `\n`、跨 chunk 半包拼接、CRLF 兼容、单行上限防爆内存                                                                                                                                                                                                                             |
| `transport/acpTransport.ts`       | transport 接口（写行 / 收行 / stderr / 退出 / close / kill）——未来 webview 侧换 Tauri IPC 实现，协议层不动                                                                                                                                                                                                      |
| `transport/nodeStdioTransport.ts` | Node 子进程实现：spawn 三管道、行分帧、stderr 旁路、Windows `taskkill /PID <pid> /T /F` 进程树终止、POSIX SIGTERM→SIGKILL；子进程 `exit` 时主动关父端 stdin（否则 Node 的 `close` 事件会因父端写端未关而悬置）                                                                                                  |
| `transport/inMemoryTransport.ts`  | 进程内对连管道（协议层单测的测试替身）                                                                                                                                                                                                                                                                          |
| `parse.ts`                        | unknown → 基础类型的收窄守卫（asRecord / asString / asNumber / asBoolean），connection / session 与各 agent 方言共用                                                                                                                                                                                            |
| `connection.ts`                   | JSON-RPC 收发：自增 id 匹配、每请求独立超时（默认 90s）、迟到响应 no-op、error 传播、断线唤醒全部挂起请求、逐行登记 `acpTraffic`；反向请求的响应回写在通道已断时降级为日志（不逃逸 unhandled rejection）                                                                                                        |
| `session.ts`                      | 会话生命周期（initialize→new/load/list→prompt→cancel→set_mode/set_model→close），wire 通知守卫收窄为类型化事件 `AcpSessionEvent`；方言扩展点 `AcpDialect`（私有通知翻译 + 私有反向请求，由 `src/agents` 注入）；标准反向请求回调注入（未注入时**安全默认**：权限自动取消，表外 kind 回落 `unknown` 而非 allow） |
| `mock/echo-agent.ts`              | 进程内仿真 agent（测试替身）：讲同一套方言，可编程轮次脚本（通知序列 / 反向请求 / 挂起等取消），供协议层单测使用                                                                                                                                                                                                |

## 职责要点

- **连接生命周期**：spawn agent 子进程（如 `chrys acp`），接管 stdin/stdout，
  stderr 单独落盘；进程树终止（Windows 必须 `taskkill /PID <pid> /T /F`，
  单杀父进程会留下孤儿子进程）。
- **请求-响应关联**：自增 id → pending map → Event/Promise 唤醒；每个请求有
  超时（参考实现为 90s），超时清理挂起项并报 `ACP_REQUEST_TIMEOUT` 类错误。
- **通知流解析**：`session/update` 的各类 `sessionUpdate`（agent_message_chunk /
  agent_thought_chunk / tool_call / tool_call_update / plan / usage_update /
  session_info_update…），以及 chrys 扩展通知（`_chrys/runtime_update`、
  `_chrys/usage_update`、`_chrys/error` 等）。chunk 流需要缓冲合并再上抛，
  不能每个 chunk 都打一条日志。
- **服务端反向请求**（agent → client 的请求，客户端必须实现）：
  - `request_permission`：权限审批，chrys 固定给 `allow` / `reject` 两个
    optionId（`allow_once` / `reject_once`），600s 未答复视为拒绝；
  - `chrys/request_input`：结构化提问，payload 为
    `{ sessionId, requestId, questions: [{ question, header, options: [{ label, description }], multiSelect }], callerName }`。
- **wire 流量登记**：每读入/写出一行，调用 `core/logger` 的 `acpTraffic`
  通道登记（`recordIn` / `recordOut`），这是诊断页流量视图的数据源。

## 边界（不允许做的事）

- 不解析具体 agent 的业务语义（那是 `src/agents` 适配器的事）；
- 不读写 `.sdd/`、不调用 aaw CLI（那是 `src/aaw` 的事）；
- 不 import React / zustand / 任何 UI 代码；
- 不含任何 `any`：wire 数据以 `unknown` 进入，用类型守卫收窄。

## 权威参考（动手前必读）

- 已跑通的 Python 客户端（请求超时、通知分发、Windows 进程树终止的全部细节）：
  - `skill-eval/src/aaw_skill_eval/services/providers/protocols/acp/session.py`
  - `skill-eval/src/aaw_skill_eval/services/providers/protocols/acp/wire.py`
- 协议对面（chrys 服务端，权威定义）：
  - `D:/dev/workspace-ai/chrys/src/chrys/app/acp/server.py` — `initialize`
    能力声明、`_request_permission` / `_request_input` payload；
  - `session_manager.py` — 会话生命周期（new / load / list / cancel / close）；
  - `content.py` — prompt content block 的受支持类型（audio 不支持、
    image 需会话开启 vision）。

## SDK

优先使用 `@agentclientprotocol/sdk`（主入口 = ACP v1 stable，与 chrys 的
protocolVersion 1 对应；Node stdio 传输在 `@agentclientprotocol/sdk/experimental/node`）。
SDK 覆盖不到的部分（如 chrys 扩展通知、进程树终止）在本层手写。
当前实现以 chrys 服务端源码为权威自研类型与连接逻辑（见 `types.ts`
头注释的方言差异说明），SDK 仅作协议演进对照。
