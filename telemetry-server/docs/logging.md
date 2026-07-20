# 日志规范

Telemetry Server 使用 Python 标准 `logging` 和 `logging.config.dictConfig`，文件轮转由
`concurrent-log-handler` 提供。业务代码负责选择位置、级别、可读说明和检索字段，Handler
负责分流、写入、轮转和压缩。

## 日志文件

生产环境默认写入 `/var/log/aaw-telemetry`：

| 文件 | 内容 | 默认保留 |
|---|---|---|
| `access.log` | HTTP 请求方法、路径、状态码、耗时和客户端地址 | 30 份 |
| `server.log` | 服务生命周期、业务状态变化和后台任务 | 30 份 |
| `error.log` | 所有 `WARNING`、`ERROR` 事件和异常堆栈 | 90 份 |

`access.log` 和 `server.log` 每日零点或达到 100 MiB 时轮转；`error.log` 达到
100 MiB 时轮转。历史文件使用 gzip 压缩。

配置项：

```text
AAW_TELEMETRY_LOGGING_CONFIG_FILE=/opt/aaw-telemetry/config/logging.yaml
AAW_TELEMETRY_LOG_DIRECTORY=/var/log/aaw-telemetry
AAW_TELEMETRY_LOG_LEVEL=INFO
```

修改日志配置后必须重启服务。

## 格式

每条日志先提供可读说明，再附加便于检索的字段：

```text
时间 [级别] [位置] 发生了什么 | key=value key=value
```

示例：

```text
2026-07-20 10:30:02.145 [INFO] [telemetry.sync] 新的步骤上报已保存，并创建了对应工作流 | request_id=req-example event=telemetry.message_processed workflow_id=111... sr=SR-1001 step_type=task-dev
2026-07-20 10:30:03.201 [INFO] [objects.diff] Dev Patch 上传并校验成功，开发步骤已进入归因处理 | request_id=req-example event=objects.upload_confirmed message_id=222... bytes_received=18240
2026-07-20 10:31:20.118 [WARNING] [http.access] GET /api/v1/dashboard/overview 返回 404，耗时 3.2 ms | request_id=req-example event=http.request_completed status_code=404
```

- 时间使用服务器本地时区，精确到毫秒。
- 位置使用稳定的业务名称，例如 `system`、`telemetry.sync`、`objects.diff`、
  `attribution` 和 `client.release`。
- 说明使用完整、可读的中文句子。
- `event` 是稳定事件键，用于脚本检索和统计。
- 请求范围内的业务日志自动带上与响应头一致的 `request_id`。

## 分流规则

- 所有 HTTP 请求完成记录只写入 `access.log`。
- 服务启动、工作流更新、步骤接收、Diff 确认、归因和客户端发布等事件写入
  `server.log`。
- 普通 Dashboard 查询不写业务日志；请求状态和耗时可从 `access.log` 获取。
- `WARNING` 和 `ERROR` 同时写入 `error.log`；异常堆栈紧随事件首行。

## 记录边界

不得记录：

- Authorization、Cookie、密码、数据库连接串或环境变量值；
- 完整请求体、响应体、Diff 内容或仓库凭据；
- Diff SHA-256、对象存储路径和 `object_key`；
- `code_statistics.quality_flags` 原文。

允许记录用于联调和归因的邮箱、用户名、Repository、SR、AR、消息 ID、工作流 ID、
步骤类型和业务状态。

## 运维查看

```bash
tail -f /var/log/aaw-telemetry/access.log
tail -f /var/log/aaw-telemetry/server.log
tail -f /var/log/aaw-telemetry/error.log
```

按请求或业务对象追踪：

```bash
grep 'req-example' /var/log/aaw-telemetry/*.log
grep 'workflow_id=111' /var/log/aaw-telemetry/server.log
grep 'event=telemetry.message_rejected' /var/log/aaw-telemetry/error.log
```
