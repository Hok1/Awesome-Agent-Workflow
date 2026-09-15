# rbs-cli token gen 支持 --expires-in · dev 设计

## 1. 需求

- 目标：`rbs-cli token gen` 新增 `--expires-in <秒>` 相对过期参数。
- 范围边界：只改 `tools`（rbs-cli）的 token gen 命令参数与 exp 计算；不改 JWT 签名逻辑、不改其他命令。
- 不做什么：不引入配置文件项；不改变 `--exp` 的既有语义与默认值。

## 2. 现状摘要

`token gen` 的 clap 参数结构 `TokenGenerate` 已有 `exp: Option<u64>`（tools/src/token/cmd.rs:177）；
exp 的实际取值在 cmd.rs:329 由 `args.exp.unwrap_or_else(default_exp)` 完成；时间合法性由
`validate_time_claims`（cmd.rs:506）校验（exp 必须晚于当前时间，cmd.rs:512-513）。
本仓无软件架构文档（无架构基线，按代码取证为准）。

## 3. 方案

在 `TokenGenerate` 新增 `expires_in: Option<u64>`，clap 上用 `conflicts_with = "exp"`
表达互斥（选择 clap 互斥而非运行时校验，因为参数冲突属使用错误，应尽早由参数解析拒绝，
且与 CLI 既有错误风格一致）。exp 计算点（cmd.rs:329）改为：

- 给了 `--exp`：维持现状（直接使用）。
- 给了 `--expires-in`：`exp = now + expires_in`，随后复用 `validate_time_claims`
  统一校验（0 与负数因 `now + 0 <= now` 自然命中既有的「exp 必须晚于当前时间」错误；
  加法溢出用 `checked_add` 转为同一错误语义）。

不修改 `default_exp` 与签名路径。

## 4. 契约变更

| 名称 | 位置 | 签名/字段 | 类型 | 调用方 | 错误语义 | 兼容策略 |
|---|---|---|---|---|---|---|
| `--expires-in` | tools/src/token/cmd.rs（TokenGenerate，cmd.rs:177 相邻） | `expires_in: Option<u64>`，clap `conflicts_with="exp"` | CLI 参数 | 终端用户 | 与 `--exp` 同给时 clap 报参数冲突并退出码 2；exp 不晚于 now 时报「exp must be a Unix timestamp later than the current time」 | 纯新增可选参数，既有调用不受影响 |

## 5. 影响面

- tools/src/token/cmd.rs:177（`TokenGenerate` 增加字段，经 clap derive 取证确认该结构即命令参数表）
- tools/src/token/cmd.rs:216（`Default` 实现需补 `expires_in: None`）
- tools/src/token/cmd.rs:329（exp 计算点）
- tools/src/token/cmd.rs:506（`validate_time_claims` 复用，无改动）

## 6. 验收标准

- A1： `--expires-in 3600` 生成的 JWT 其 `exp` = 生成时刻 + 3600 秒（±2 秒容差）。
- A2：`--exp <ts> --expires-in 3600` 同给时命令以退出码 2 拒绝并提示参数冲突。
- A3：`--expires-in 0` 被拒绝，错误文案与既有 exp 校验一致。
- A4：仅给 `--exp`（不带 `--expires-in`）的既有用法输出不变（回归）。

## 7. 存疑

无。

改写
