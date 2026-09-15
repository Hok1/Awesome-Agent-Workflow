# RBS 软件架构（模块边界声明）

> 版本：v1.0（随 SR-1 测评夹具建立）
> 用途：ASIS 分析的模块边界来源。本文档是 `.sdd/software_architecture.md` 的契约角色：
> 模块归属以本文档为准，不得由代码结构推断。

## 仓库形态

单一 Rust workspace（根 `Cargo.toml`，resolver = "2"），多 crate 协作。

## 模块清单

| 模块 | 路径 | 职责 | 边界说明 |
|---|---|---|---|
| `rbs-core` | `rbs/core/` | 核心域逻辑：认证与验签（`src/auth/`，含 `authn/` 各算法 Verifier、`authz/` 鉴权）、用户公钥登记（`src/admin/key.rs`）、attestation 验证（`src/attestation/`）、策略与资源域 | 不直接暴露 HTTP；不读写终端用户私钥 |
| `rbs-rest` | `rbs/rest/` | REST API 层：路由（`src/routes/`）、认证中间件（`src/middleware/auth.rs`）、OpenAPI 文档 | 只编排 `rbs-core` 能力，不实现密码学 |
| `rbs`（二进制/库壳） | `rbs/src/`、`rbs/build.rs`、`rbs/conf/` | 服务装配、配置加载、启动入口 | 不含业务逻辑 |
| `rbs-api-types` | `rbs/api-types/` | 对外 API 类型定义（请求/响应 DTO） | 纯类型，无行为 |
| `rbs-cli` | `tools/` | 命令行工具：`token` 生成（`tools/src/token/`）、管理客户端（`tools/src/admin/`、 `rbs-admin-client`） | 用户侧工具；私钥只在本模块出现 |
| `rbc` | `rbc/` | 资源内容加密（不在 SR-1 范围） | 与认证链路无交互 |

## 关键边界规则

1. 密码学运算只发生在 `rbs-core`（服务端验签）与 `rbs-cli`（客户端签名）两端；
   `rbs-rest` 只做 token 传递与中间件编排。
2. 用户认证公钥的持久化归 `rbs-core`（用户库 `t_user_info`），登记入口为
   `rbs-core` 的 `admin/key`，由 `rbs-rest` 的管理路由暴露。
3. GTA 验签公钥归 `rbs-core` 的 attestation/authn 链路，配置经 `rbs` 壳加载。
