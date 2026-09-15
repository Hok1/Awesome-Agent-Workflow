# AR-1-SM2用户认证-rbs-core模块详细设计说明书

> 本文档是 `rbs-core` 模块在 SR-1（SM2 国密算法认证与令牌支持）下 AR-1（SM2 用户认证）的 TOBE 详细设计。
> 范围：验签算法分派扩展、公钥登记链路扩展、配置兼容，以及相关的失败语义、风险与可测试性输入。
> 本文只写"实现必须满足什么"，不写测试用例与编码任务拆分。

## 1. 需求背景 / 当前 AR 描述

### 1.1 需求与目标

SR-1 要为国密合规场景补齐认证链路的 SM2（SM3 摘要）能力：用户认证支持 SM2、验证 GTA 用 SM2 签发的 attestation token、`rbs-cli` 生成 SM2 token。本 AR（AR-1，SM2 用户认证）聚焦 `rbs-core` 侧目标设计。

**目标行为**：

- RBS 接受由 SM2 私钥签名、`alg=SM2` 的用户 JWT（BearerToken），并可用该用户的 SM2 公钥完成 SM3+SM2 验签。
- RBS 接受由 GTA 用 SM2 签发的 attestation token（AttestToken），可经 PEM（`public_key_path`）或 JWKS（`jwks_file`，`kty=EC,crv=SM2`）选键完成 SM3+SM2 验签。
- 管理员可通过既有用户登记入口，以 PEM 或 JWK（`crv=SM2`）两种输入登记 SM2 用户公钥；算法标识由公钥推导为 `SM2`。
- SM2 的接入是"新增可接受算法"，不替换、不移除任何既有算法（PS256/PS384/PS512/EdDSA）。

**触发条件**：`Authorization: Bearer <SM2 JWT>`（受保护端点）或 `Authorization: Attest <SM2 JWT>`（资源 GET 类端点）；管理员调用用户创建/更新接口并提交 SM2 公钥材料。

**验收口径**：合法 SM2 令牌通过认证并进入既有业务逻辑；SM2 公钥（PEM/JWK）登记成功且 `auth_alg` 落库为 `SM2`；既有国际算法令牌行为不变；未知算法、跨算法验签、非法 claims、无匹配键等场景按既有 401 语义拒绝；不引入新密码学三方件。

**强约束**：复用仓库既有 vendored OpenSSL（3.x），不引入新密码学依赖。

### 1.2 范围说明

| 编号 | 需求/AR/变更点 | 本模块处理结论 | 关联详细方案 |
|---|---|---|---|
| R1 | 用户认证支持 SM2 算法（Bearer 用户 token 以 SM2 验签） | 本模块实现 | 4.1 / 4.2 |
| R2 | 验证 GTA 签发的 SM2 attestation token | 本模块实现 | 4.1 / 4.3 |
| R3 | 管理员登记 SM2 用户公钥（PEM 与 JWK 两种输入） | 本模块实现 | 4.4 |
| R4 | rbs-cli 生成 SM2 token | 不属于本模块（`tools` 侧）；仅作为验签互操作契约记录 | 2 / 7 |
| R5 | 不引入新密码学依赖，复用现有 OpenSSL | 本模块实现（约束） | 2 / 3.1 / 9 |
| R6 | 保持既有算法（PS*/EdDSA）与未知算法拒绝策略不回退 | 本模块实现（回归约束） | 4.1 / 4.4 / 5 |
| R7 | 错误映射与对外响应语义保持一致 | 本模块实现（约束） | 4.2 / 4.3 / 4.4 |
| R8 | 用户表/持久化结构无需破坏性变更（数据兼容） | 本模块实现（无 DDL 变更，仅算法取值扩展） | 6 |

不负责内容：GTA 侧 SM2 签发实现、`rbs-cli` 的 SM2 签名实现、`rbs-rest` 的中间件与路由改造（本模块仅约定边界与契约）、TLS 国密套件、JWE 资源加密。

## 2. 外部依赖

| 依赖对象 | 本次关联 | 对设计 / 实现的具体影响 | 失败或兼容处理 | 关联设计点 |
|---|---|---|---|---|
| OpenSSL（`openssl` 0.10.79，vendored OpenSSL 3.x） | 提供 SM2/SM3 验签与公钥解析 | 全部 SM2 密码学运算经此底座完成；须使用可提供 SM2 语义（含 Z 值）的验签接口，不得以普通 ECDSA-with-SM3 替代 | 底座缺失 SM2/SM3 时构建/运行失败；仓库已满足 | D1 / 4.1 |
| `jsonwebtoken` 10.3.0 | 既有算法（PS*/EdDSA）JWT 解码 | 无 SM2 算法变体，`decode_header` 对未知 `alg` 直接报错，故 SM2 不能走既有解码路径 | SM2 走独立分支；不得因新增分支弱化其校验 | D2 / 4.1 / 4.2 |
| GTA 侧 SM2 attestation token 与公钥表示法 | 外部输入（`alg` 串、JWK `kty/crv/x/y`、签名编码、Z 默认值） | 决定验签互操作与 JWKS 解析结果 | 本模块按本文约定的表示法实现；GTA 侧最终表示法待前置确认（见 9） | D5 / 4.3 |
| `rbs-cli`（`tools`）SM2 签名 | 令牌生产者（本模块的验签对象） | 生产者与消费者须使用同一 JWS `alg`、签名编码与 Z 值 | 表示法不一致将导致 401；以本模块契约 K3 为准 | D5 / 4.1 / 7 |
| `t_user_info`（用户库） | 用户公钥来源（`auth_value` PEM / `auth_alg`） | 验签期经 `UserKeyProvider` 取 PEM；SM2 公钥复用既有列 | 无结构变更；算法取值扩展 | D4 / 4.2 / 4.4 / 6 |

## 3. 整体方案

### 3.1 方案概述

SM2 作为"新增可接受算法"嵌入既有认证主干，最小侵入、对既有算法零改动：

- **算法分派**：在进入 `jsonwebtoken` 解码前，先对 JWT header 做"原始 `alg` 预解析"（不经 `Algorithm` 枚举），命中 `SM2` 即切换到 SM2 独立验签分支，未命中完全保持既有路径。
- **SM2 能力集中**：新增 `authn::sm2` 子模块，统一承载 SM3+SM2 验签与 `r||s`→DER 签名编码转换；Bearer 与 Attest 两条验签路径复用同一实现，保证语义一致。
- **键识别路径**：SM2 键的识别由令牌的 `alg` 驱动（`alg=SM2`），不依赖用户库 `auth_alg`，因此**不修改 `UserKeyProvider` trait**；跨算法（SM2 令牌 + 非 SM2 公钥）在验签阶段失败。
- **登记与配置**：扩展 `admin::key` 的曲线/键型分支使 SM2 公钥可被登记与推导；**不新增配置项**，SM2 沿用既有 `public_key_path`/`jwks_file`/用户公钥登记。
- **无数据变更**：表结构与 DDL 不变，仅 `t_user_info.auth_alg` 取值域扩展。

| 决策编号 | 设计点 | 设计结论 | 设计依据摘要 | 影响范围 | 评审关注点 | 状态 / 待确认说明 |
|---|---|---|---|---|---|---|
| D1 | SM2 验签能力落点 | 新增 `authn/sm2` 子模块，提供 SM3+SM2 验签与签名编码转换，供 Bearer/Attest 复用 | SM2 无法复用 `jsonwebtoken`，两条路径均需要同一套 SM2 语义，集中一处避免双份实现漂移 | 文件 `authn/sm2.rs` | 是否接受新增子模块（不新增 crate/依赖） | 已定稿 |
| D2 | 算法分派扩展 | 新增"原始 `alg` 预解析"；`alg=SM2` 走独立分支，其余保持既有 `decode_header`+`validate_algorithm` 路径 | `decode_header` 对未知 `alg` 即失败，SM2 无法进入既有解码 | 文件 `authn/common.rs`、`authn/bearer_token.rs`、`authn/token.rs` | 分派是否对既有算法零回归 | 已定稿 |
| D3 | SM2 键识别路径 | 由令牌 `alg` 驱动识别，`UserKeyProvider::get_public_key` 保持仅返回 PEM，trait 不变 | 现状取键入口不返回 `auth_alg`；改 trait 影响面大且无必要 | 接口 `UserKeyProvider`（不变） | 是否接受"以 alg 驱动 + 公钥曲线自识别" | 已定稿 |
| D4 | 公钥登记扩展 | `admin::key` 的 EC 分支增加 SM2 曲线识别，`auth_alg` 推导为 `SM2`；JWK 分支增加 `crv=SM2` | 现状 SM2 曲线落"Unsupported EC curve"；登记链路由 PEM 反推 `auth_alg`，无需新字段 | 文件 `admin/key.rs`、`admin/manager.rs`（复用） | 既有 RSA/EC 登记是否不变 | 已定稿 |
| D5 | SM2 表示法约定 | 待定（表示法约定未收敛，待 GTA 确认） | 与 GTA/rbs-cli 互操作需统一约定；SR 已给出上述约定 | JWS/JWK 线格式、`authn/sm2`、`authn/jwks` | GTA 侧最终表示法 | 已定稿（本模块）；<span style="color:red">GTA 侧外部表示法待前置确认（见 9）</span> |
| D6 | 配置兼容 | 不新增配置字段/开关；沿用既有 `auth.attest_token.public_key_path`/`jwks_file` 与用户登记 | `RbsConfig` 使用 `deny_unknown_fields`，新增字段需同步类型与 yaml；SM2 可复用既有键来源 | `rbs/api-types` 配置类型（不变）、`rbs.yaml`（不变） | 是否需要 SM2 专用开关 | 已定稿（不新增） |
| D7 | 数据兼容 | 不新增表/列/索引；仅 `auth_alg` 取值扩展为可含 `SM2` | `auth_value`/`auth_alg` 为自由文本，天然承载 SM2 PEM | 表 `t_user_info` | 是否需要 DDL 变更 | 已定稿（无 DDL 变更） |

### 3.2 变化触发表

| 变化类型 | 是否涉及 | 说明 / 权威位置 |
|---|---|---|
| 包/模块结构变化 | 是 | 新增 `authn/sm2` 子模块（不新增 crate、不新增三方件）；依赖方向不变 |
| 类/接口变化 | 是 | 新增内部验签函数与原始 header 解析；`UserKeyProvider` 不变；`Jwk` 结构扩展字段 → 4.1.3 / 4.3.3 / 4.4.3 |
| 业务流程变化 | 是 | 验签主流程新增 SM2 分派分支与 SM2 claims 校验 → 4.1.2 / 4.2.2 / 4.3.2 |
| REST 接口变化 | 否 | 不新增/删除路由，Method、Path、认证头不变；仅可接受 `alg` 集合与公钥材料取值扩展（对外契约见第 5 章与 SR 设计 §4） |
| Kafka/MQ 接口变化 | 否 | 本次不涉及消息中间件 |
| 内部 Java 接口/抽象变化 | 否 | 非 Java 仓库；内部 Rust 抽象变化已并入"类/接口变化" |
| 数据库变化 | 否 | 表/字段/索引/约束不变，仅 `auth_alg` 取值扩展 → 第 6 章 |
| 配置/开关变化 | 否 | 不新增配置项与开关；关闭后行为即既有 ASIS 行为 → 3.1 D6 / 第 2 章 |

## 4. 模块详细方案

### 4.1 SM2 算法分派与验签能力

#### 4.1.1 目标与约束

目标：在既有"按 token 类型分派到 verifier"的基础上，于 verifier 内部增加按算法（`alg`）的分派点，使 `alg=SM2` 走独立 SM2 验签分支，其余算法保持既有路径；并把 SM2 密码学运算收敛到单一子模块。

约束（来自现状）：算法白名单硬编码为 PS256/PS384/PS512/EdDSA，`decode_token_header` 走 `jsonwebtoken::decode_header`，对未知 `alg`（含 `SM2`）在头解析阶段即失败；验签侧"算法→密钥类型"分派仅区分 RSA 家族与 Ed25519，无 EC/SM2 分支；OpenSSL 底座具备 SM2/SM3 能力但无高层 SM2 验签封装。

#### 4.1.2 目标设计

实现必须保持的行为与不变量：

- **最小侵入分派**：验签入口先做"原始 header 预解析"（只解 JWT 第 1 段 base64url 的 JSON，取 `alg` 与可选 `kid`），**不经 `jsonwebtoken::Algorithm` 枚举**。`alg == "SM2"` 走 SM2 分支；其余一律回到既有 `decode_token_header`+`validate_algorithm`+`decode` 路径，行为与现状逐字节一致。
- **SM2 能力集中**：新增 `authn::sm2` 子模块，对外提供"SM2 JWS 验签"单一入口，内部完成：`r||s`（各 32 字节）→ DER 的签名编码转换、SM3 摘要 + SM2 验签、失败归一为 401 语义。Bearer 与 Attest 两条路径都调用它，禁止各自实现一份 SM2 运算。
- **算法-密钥一致（防 alg 混淆）**：SM2 令牌必须用 SM2 公钥验证；公钥的 SM2 语义由 OpenSSL 依据公钥曲线的 SM2 语义决定。SM2 令牌配非 SM2 公钥、或非 SM2 令牌配 SM2 公钥，都必须在验签阶段失败并返回统一 401，不得放行。
- **Z 值语义**：SM2 验签须使用 SM2 用户标识（Z）语义（非普通 ECDSA-with-SM3），采用标准默认用户标识，与签名侧及 GTA 对齐（见 K3）。
- **不变量**：`SUPPORTED_ALGORITHMS`（`jsonwebtoken::Algorithm` 列表）保持仅 PS256/PS384/PS512/EdDSA；未知算法（含 `none`、`RS*`、`HS*`）仍被拒绝；`AuthError` 变体与对外 401 语义不变。

**分派与验签主流程**（主路径 + 关键失败路径）：

```mermaid
flowchart TD
    A[验签入口: 收到 JWT 紧凑串] --> B[peek_raw_header<br/>base64url 解第 1 段 JSON, 取 alg 与 kid]
    B -- 解析失败 --> Z[401 invalid token]
    B --> C{alg == SM2 ?}
    C -- 否 --> D[decode_token_header + validate_algorithm<br/>PS*/EdDSA 既有路径]
    D -- 失败 --> Z
    D --> E[jsonwebtoken decode: 验签 + claims]
    E -- 失败 --> Z
    E -- 成功 --> K[返回 BearerContext / AttestContext]
    C -- 是 --> F[SM2 分支]
    F --> G[Bearer: 预解析 sub → 查用户库取 PEM<br/>Attest: 直连 PEM 或按 kid 选 JWKS→PEM]
    G -- 取键失败 --> Z
    G --> H[verify_sm2_jws: r||s→DER, SM3+SM2 验签]
    H -- 失败 --> Z
    H -- 成功 --> I[SM2 claims 校验 exp/iss/sub/aud]
    I -- 过期 --> Y[401: TokenExpired]
    I -- 其他失败 --> Z
    I -- 成功 --> K
```

**依赖变更视图**（仅新增模块内依赖，方向不变；无新增 crate/三方件）：

| 依赖关系 | 变化前 | 变化后 | 允许 / 禁止 | 架构依据 |
|---|---|---|---|---|
| `authn/bearer_token` → `authn/sm2` | 不存在 | 新增（模块内） | 允许 | 架构规则：密码学只发生在 `rbs-core` 内 |
| `authn/token` → `authn/sm2` | 不存在 | 新增（模块内） | 允许 | 同上 |
| `authn/common` → `jsonwebtoken` | 存在 | 不变 | 允许 | 既有 |
| `authn/sm2` → `openssl` | 不存在 | 新增（`rbs-core` 直接用 openssl） | 允许 | SR §11：复用既有 OpenSSL，不新增密码学依赖 |
| `rbs-core` → 新增密码学三方件 | 无 | 无 | 禁止 | D1 / SR §11 |

#### 4.1.3 契约与工程落点

**工程落点**：

- `rbs/core/src/auth/authn/common.rs`（修改）：新增原始 header 解析与 SM2 常量/白名单串；`validate_algorithm`、`decode_token_header`、`create_decoding_key`、`map_jwt_error` 对既有算法保持语义不变。
- `rbs/core/src/auth/authn/sm2.rs`（新增）：SM2 验签子模块；在 `authn/mod.rs` 注册 `pub mod sm2;`。

**方法 / 函数契约**：

| 对象 | 变化 | 完整签名 | 异常 / 错误语义 | 关联契约 |
|---|---|---|---|---|
| `authn::common::peek_raw_header` | 新增 | `pub fn peek_raw_header(token: &str) -> Result<RawJwsHeader, AuthError>` | 段数≠3、base64url 解码失败、JSON 解析失败、缺 `alg` 或 `alg` 非字符串 → `AuthError::TokenInvalid` | K1 |
| `authn::common::RawJwsHeader`（结构） | 新增 | `pub struct RawJwsHeader { pub alg: String, pub kid: Option<String> }` | 仅承载未验签的 header 元信息；`kid` 缺失为 `None` | K1 |
| `authn::sm2::verify_sm2_jws` | 新增 | `pub fn verify_sm2_jws(public_key_pem: &[u8], signing_input: &[u8], signature: &[u8]) -> Result<(), AuthError>` | 公钥非 SM2、签名非 64 字节 `r||s`、验签不通过 → `AuthError::TokenInvalid`（对外归一为 401） | K2 / K3 |

**常量 / 枚举值**：

| 常量名 | 取值 | 说明 | 关联契约 |
|---|---|---|---|
| `authn::common::SM2_ALG` | `"SM2"` | JWS header `alg` 的 SM2 表示串 | K3 |
| `authn::common::SUPPORTED_ALGORITHMS` | `[PS256, PS384, PS512, EdDSA]` | 保持不变，仅覆盖 `jsonwebtoken` 可解码算法 | K1 |
| `authn::common::SUPPORTED_ALGORITHMS_STR` | `"PS256, PS384, PS512, EdDSA, SM2"` | 错误信息展示用，纳入 SM2 | K1 |
| SM2 曲线 OID | `1.2.156.10197.1.301` | SM2 256 位曲线 | K3 |
| SM2 摘要 | SM3（256 位） | SM2 签名摘要 | K3 |

#### 4.1.4 失败语义、风险与验收

| 验证目标 | 覆盖范围 | 输入 / 触发条件 | 预期行为 | 可观察信号 | 关联契约 / 设计点 |
|---|---|---|---|---|---|
| 分派正确性 | 主路径 | header `alg=SM2` 的合法令牌 | 进入 SM2 分支并验签成功 | 返回对应 Context | K1 / K2 / D2 |
| 既有算法回归 | 兼容回归 | header `alg=PS256/PS384/PS512/EdDSA` 的合法令牌 | 走既有路径，行为与改造前一致 | 返回 Context，无新增日志噪声 | K1 / D2 |
| 未知算法拒绝 | 失败路径 | `alg=RS256`/`alg=HS256`/`alg=none`/缺失 `alg` | 401 `unsupported algorithm` 或 `invalid token` | 401 | K1 / R6 |
| 原始 header 解析健壮性 | 边界 | 非 3 段、header base64url 非法、header 非 JSON、`alg` 非字符串 | 401，不 panic | 401 | K1 |
| 算法-密钥一致 | 安全 | SM2 令牌 + RSA/Ed25519 公钥；非 SM2 令牌 + SM2 公钥 | 验签失败 401，不放行 | 401 | K2 / K3 / D3 |
| SM2 验签正确性 | 主路径 / 安全 | 正确签名 vs 篡改签名/SM3 不一致 | 正确通过；篡改 401 | 验签结果 | K2 / K3 |
| Z 值语义 | 安全 | 使用标准默认 Z 的签名 | 验签通过；若用非 SM2 语义实现则失败 | 验签结果 | K3 |

日志/观测：认证失败保持既有 `debug`/`warn` 级别与"不落令牌正文/密钥"约定；SM2 失败与既有失败归入同一 401 语义，日志可含算法维度（`alg`）以便区分。

### 4.2 BearerToken 用户认证 SM2 验签

#### 4.2.1 目标与约束

目标：`BearerTokenVerifier::verify` 在 `alg=SM2` 时，用该用户登记的 SM2 公钥完成 SM3+SM2 验签，并保持既有"先无签名预解析 `sub` → 查用户库取键 → 验签 → 复校 claims"的安全模型。

约束（来自现状）：`sub` 依赖未验签 payload 预解析取得；`UserKeyProvider::get_public_key(sub)` 只返回 `auth_value`（PEM），不返回 `auth_alg`；取键失败必须归一为统一 `invalid token` 以防用户枚举。

#### 4.2.2 目标设计

SM2 分支（在 `peek_raw_header` 判定 `alg=SM2` 后）必须保持与既有路径相同的顺序与安全性质：

1. 预解析 payload 取 `sub`（沿用既有安全说明：仅用于取键，取键后才信任）。
2. `get_public_key(sub)` 取用户公钥 PEM；失败/用户不存在 → 记录详细错误（日志）但对外统一 `AuthError::TokenInvalid{ "invalid token" }`（防用户枚举）。
3. 构造 signing input = `base64url(header) + "." + base64url(payload)` 的 ASCII 字节；解签名段为 `r||s`。
4. `verify_sm2_jws(pem, signing_input, signature)`；失败 → 统一 `invalid token`。
5. 验签通过后解析 payload claims 并复校（见 4.2.3 K4 决策表）。

**关键取舍**：SM2 分支不复用 `jsonwebtoken::decode`（无法对 SM2 验签），故其 claims 校验需独立实现；实现必须使校验语义与既有 `Validation` 路径等价，避免两路径漂移（详见 K4 与风险）。

#### 4.2.3 契约与工程落点

**工程落点**：`rbs/core/src/auth/authn/bearer_token.rs`（修改 `verify`；可抽取一个小工具解析 payload claims 供 SM2 分支使用）。

**契约 K4 — BearerToken SM2 分支 claims 校验规则**（须与既有 `jsonwebtoken::Validation` 等价）：

| claim | 规则 | 失败结果 |
|---|---|---|
| `sub` | 必须存在、非空；且与用于取键的预解析 `sub` 一致 | `AuthError::TokenInvalid`（对外 401 `invalid token`） |
| `iss` | 必须存在且等于 `bearer_token.issuer` | `AuthError::TokenInvalid` |
| `aud` | 必须存在且等于 `bearer_token.audience` | `AuthError::TokenInvalid` |
| `exp` | 必须存在；按既有 `Validation` 的默认时间容差判定过期 | `AuthError::TokenExpired` |
| `nbf`（可选） | 若存在，按既有 `Validation` 语义判定未生效 | `AuthError::TokenNotYetValid` |

> 说明：既有路径的 `Validation` 由 `Validation::new(alg)` 构造后设置必填 `["exp","iss","sub"]`、issuer、audience。SM2 分支的必填集合、issuer/audience 取值与时间容差语义须与之一致（含默认 leeway），以保证同一令牌在两条路径下判定一致。

**变更前后**：

| 变更对象 | 变更前 | 变更后 | 兼容性影响 |
|---|---|---|---|
| `BearerTokenVerifier::verify` | 仅 PS*/EdDSA：`decode_token_header` + `create_decoding_key` + `decode` | 先 `peek_raw_header`；`alg=SM2` 走 SM2 分支，其余走原路径 | 既有算法路径不变；SM2 新增 |
| 取键接口 `UserKeyProvider::get_public_key` | 返回 PEM | 不变 | 无 |

#### 4.2.4 失败语义、风险与验收

| 验证目标 | 覆盖范围 | 输入 / 触发条件 | 预期行为 | 可观察信号 | 关联契约 / 设计点 |
|---|---|---|---|---|---|
| 主路径 | 主路径 | 已登记 SM2 用户 + 合法 `alg=SM2` 令牌 | 认证通过，返回 `BearerContext{sub,iss,role,claims}` | 200 业务响应 | K2 / K4 / D3 |
| 用户无公钥 | 失败路径 | `sub` 在用户库不存在 | 统一 401 `invalid token`（不泄露用户是否存在） | 401 | K4 / D3 |
| 公钥不匹配 | 安全 | SM2 令牌对应非 SM2 公钥 | 401 `invalid token` | 401 | K2 / K4 |
| claims 校验 | 失败路径 | `iss`/`aud` 不符、`exp` 过期、缺 `sub` | 401；过期返回过期语义 | 401 / TokenExpired | K4 |
| 与既有路径一致性 | 兼容/安全 | 同一 payload 分别经既有路径与 SM2 分支判定 | 结论一致 | 认证结果一致 | K4 |
| 重复校验幂等 | 边界 | 同一令牌重复请求 | 结果恒定、无副作用 | 稳定结果 | K2 / K4 |

### 4.3 GTA attestation token SM2 验签与 JWKS EC/SM2 解析

#### 4.3.1 目标与约束

目标：`AttestTokenVerifier` 在 `alg=SM2` 时，用配置的 GTA SM2 公钥（直连 PEM 或按 `kid` 从 JWKS 选键）完成 SM3+SM2 验签，并保持既有 claims 校验（`exp`、`iss`，`aud` 按配置可选）。

约束（来自现状）：验签键来源为 `public_key_path`（PEM）或 `jwks_file`（二选一，缺一即启动失败）；PEM 键型识别仅区分 Ed25519 与 RSA；JWKS 的 `Jwk` 无 `y` 字段，`jwk_to_pem` 仅支持 `kty=RSA` 与 `kty=OKP(Ed25519)`，`kty=EC` 一律拒绝。

#### 4.3.2 目标设计

- **构造期（`new`）**：`public_key_path` 分支读取 PEM 后按 OpenSSL 键型识别并保存为两类键材料之一——`jsonwebtoken` 可用的解码键（RSA/Ed25519）或"EC/SM2 原始 PEM"（用于 SM2 分支）；无法识别为受支持键型时**仍在构造期失败**（保留启动期快速失败语义）。`jwks_file` 分支保持解析逻辑，键在验签期按 `kid`/首键选定后转 PEM。
- **验签期（`verify`）**：先 `peek_raw_header` 取 `alg`/`kid`。
  - `alg=SM2`：取键材料（直连 PEM，或 JWK→PEM），`verify_sm2_jws`；再校验 claims（`exp`、`iss`，`aud` 若配置）。
  - 其余：选键 → JWK→PEM（如为 JWKS）→ `create_decoding_key` → `decode`，与现状一致。
- **JWKS 扩展**：`Jwk` 增加 `y` 字段；`jwk_to_pem` 增加 `kty="EC"` 分支，仅接受 `crv="SM2"` 并输出 SM2 SPKI PEM；其他 EC 曲线仍拒绝（错误语义由"unsupported key type"变为"unsupported curve/EC"）。
- **选键与编码**：`kid` 仅用于选键，不参与路径拼接；SM2 分支签名段按 `r||s` 解码。

#### 4.3.3 契约与工程落点

**工程落点**：`rbs/core/src/auth/authn/token.rs`（修改 `new`、`verify`、键选择逻辑）、`rbs/core/src/auth/authn/jwks.rs`（修改 `Jwk` 与 `jwk_to_pem`）。

**契约 K5 — JWKS EC/SM2 与转换**（JSON 名称须保留）：

| 对象 | 变化 | 字段 / 行为 | 异常 / 错误语义 | 关联契约 |
|---|---|---|---|---|
| `authn::jwks::Jwk` | 修改（新增字段） | 新增 `#[serde(default)] pub y: Option<String>`；原有 `kty,kid,alg,n,e,crv,x` 保留 | — | K5 |
| `authn::jwks::jwk_to_pem` | 修改 | 新增 `kty="EC"` 分支：`crv="SM2"` → 由 `x`/`y` 组装 SM2 公钥并输出 SPKI PEM；其他 EC 曲线 → 错误 | 缺 `y`/`x`、解码失败、非 SM2 曲线 → `AuthError::TokenInvalid` | K5 / K3 |
| JWK JSON 名称 | 新增取值 | `kty`：`RSA`/`OKP`/`EC`；`crv`：`Ed25519`/`SM2`；SM2 为 32 字节 `x`、`y`（base64url 无填充）；`alg` 建议 `SM2` | 非 `SM2` 的 EC 曲线不支持 | K5 |

**契约 K7 — AttestTokenVerifier 构造与选键行为**：

| 场景 | 键来源 | 行为 |
|---|---|---|
| 构造期 | `public_key_path` 缺失且 `jwks_file` 缺失 | 返回 `AuthError::TokenInvalid`（启动失败），语义不变 |
| 构造期 | `public_key_path` 指向不可读/非法 PEM | 构造失败（启动失败），语义不变 |
| 构造期 | `public_key_path` 为 RSA/Ed25519 PEM | 构造期构建 `DecodingKey`（复用既有语义） |
| 构造期 | `public_key_path` 为 EC/SM2 PEM | 保存原始 PEM 供 SM2 分支使用（不因 SM2 曲线在启动期失败） |
| 验签期 | `alg=SM2` + 直连 PEM | `verify_sm2_jws` |
| 验签期 | `alg=SM2` + JWKS | 按 `kid`（缺省首键）→ `jwk_to_pem`（EC/SM2）→ `verify_sm2_jws` |
| 验签期 | `kid` 不存在 / JWKS 无键 | `AuthError::TokenInvalid`（401） |

**契约 K3（摘录，Attest 侧）**：`alg` 取值 `SM2`；签名段 `r||s` 各 32 字节（base64url 无填充）；摘要 SM3；SM2 Z 用户标识采用标准默认；JWK `kty=EC,crv=SM2`。

#### 4.3.4 失败语义、风险与验收

| 验证目标 | 覆盖范围 | 输入 / 触发条件 | 预期行为 | 可观察信号 | 关联契约 / 设计点 |
|---|---|---|---|---|---|
| 主路径（PEM） | 主路径 | 配置 SM2 PEM + 合法 `alg=SM2` attestation token | 验签通过，返回 `AttestContext` | 200 资源响应 | K2 / K3 / K7 |
| 主路径（JWKS） | 主路径 | JWKS 含 `kty=EC,crv=SM2` + 匹配 `kid` | 选键成功并验签通过 | 200 资源响应 | K5 / K7 |
| 选键失败 | 失败路径 | `kid` 不在 JWKS、JWKS 为空、`crv` 非 SM2 | 401 `invalid token` | 401 | K5 / K7 |
| 配置失败 | 失败路径 | 键文件缺失/非法 | 启动期失败并记录原因 | 启动失败 | K7 |
| 既有算法回归 | 兼容回归 | RSA/Ed25519 PEM 或 JWKS + PS*/EdDSA 令牌 | 走既有路径不变 | 通过 | K5 / K7 |
| 既有拒绝语义回归 | 兼容/安全 | `kty=EC,crv=P-256`（非 SM2） | 仍拒绝，但错误走 EC 曲线分支 | 401（错误文案变化） | K5 / R6 |
| claims 校验 | 失败路径 | `iss`/`aud`/`exp` 不符 | 401；过期返回过期语义 | 401 | K7 |

> 回归注意：新增 `kty=EC` 分支后，既有内联用例 `test_unsupported_key_type_ec`（断言 `kty=EC,crv=P-256` 报"unsupported key type"）的断言需同步更新为"EC 曲线不支持"语义（详见 4.4.4），并新增 `crv=SM2` 正/反向用例。

### 4.4 用户 SM2 公钥登记

#### 4.4.1 目标与约束

目标：管理员可通过既有登记入口提交 SM2 公钥（PEM 或 JWK），系统校验其合法性并把 `auth_value`（SM2 公钥 PEM）与 `auth_alg`（`SM2`）落库。

约束（来自现状）：`validate_and_derive_alg(pem)` 对 EC 仅认 P-256/P-384/P-521，SM2 曲线落"Unsupported EC curve"；`jwk_to_pem` 的 EC 分支仅认 P-256/P-384/P-521（`crv=SM2` 落"Unsupported JWK EC curve"）；`auth_alg` **由存储的 PEM 反推**，不采用 JWK 自带的 `alg`；`MAX_KEY_SIZE=10240` 对 PEM/JWK 串做长度上限。

#### 4.4.2 目标设计

- `validate_and_derive_alg` 的 EC 分支增加 SM2 曲线识别：SM2 曲线公钥 → 算法串 `"SM2"`；P-256/384/521 行为不变；其他曲线仍 `Unsupported EC curve`。
- `jwk_ec_to_pem` 增加 `crv="SM2"` 分支：由 `x`/`y`（各 32 字节）组装 SM2 公钥并输出 SPKI PEM；其他曲线仍拒绝。
- 登记链路（`create_user`/`update_user`/`extract_auth_material`）**复用既有事务与校验骨架**：PEM 优先，JWK 兜底转 PEM，再由 PEM 反推 `auth_alg`，事务内写入 `auth_value`/`auth_alg`；SM2 无需新字段或新表。
- 权限与限额语义不变（管理员限制、`max_users`、重复用户校验、`MAX_KEY_SIZE`）。

> 实现注意：OpenSSL 可能将 SM2 曲线公钥标记为 `Id::EC`（以曲线名识别）或专门键型；实现须在保留 P-256/384/521 行为的前提下，确保 SM2 曲线稳定推导为 `SM2`。

#### 4.4.3 契约与工程落点

**工程落点**：`rbs/core/src/admin/key.rs`（修改 `validate_and_derive_alg`、`jwk_ec_to_pem`）；`rbs/core/src/admin/manager.rs` 复用（不改签名）。

**契约 K6**：

| 对象 | 变化 | 输入 | 输出 / 行为 | 异常 / 错误语义 | 关联契约 |
|---|---|---|---|---|---|
| `admin::key::validate_and_derive_alg` | 修改 | PEM 公钥 | SM2 曲线 → `"SM2"`；RSA → `"RS256"`；P-256/384/521 → `"ES256/384/512"` | 其他曲线 → `RbsError::InvalidParameter("Unsupported EC curve")`；其他键型 → `"Unsupported key type"`；超限/非法 PEM 语义不变 | K6 |
| `admin::key::jwk_ec_to_pem` | 修改 | JWK `kty=EC` | `crv="SM2"` → SPKI PEM（由 `x`/`y` 组装）；P-256/384/521 不变 | 其他曲线 → `InvalidParameter("Unsupported JWK EC curve")`；缺 `crv`/`x`/`y`、解码失败语义不变 | K6 |
| `MAX_KEY_SIZE` | 不变 | PEM/JWK 串 | 上限 10240 字节 | 超限 → `InvalidParameter` | K6 |

**关键映射规则**：

| 输入条件 | 输出 `auth_alg` | 说明 |
|---|---|---|
| SM2 曲线 PEM 公钥 | `SM2` | 新增取值 |
| JWK `kty=EC,crv=SM2`（经 `jwk_to_pem` 转 PEM） | `SM2` | `auth_alg` 由转换后的 PEM 反推 |
| RSA PEM | `RS256` | 不变 |
| EC P-256/384/521 PEM | `ES256/384/512` | 不变 |

#### 4.4.4 失败语义、风险与验收

| 验证目标 | 覆盖范围 | 输入 / 触发条件 | 预期行为 | 可观察信号 | 关联契约 / 设计点 |
|---|---|---|---|---|---|
| 主路径（PEM） | 主路径 | 提交 SM2 PEM | 创建/更新成功，`auth_value`=PEM、`auth_alg`=`SM2` | 落库成功 | K6 / D4 |
| 主路径（JWK） | 主路径 | 提交 `kty=EC,crv=SM2,x,y` | 转 PEM 落库，`auth_alg`=`SM2` | 落库成功 | K6 / K5 |
| 非法曲线 | 失败路径 | 提交非 SM2 的 EC 曲线 PEM/JWK | 400，内部原因"Unsupported…"，对外 `invalid parameter` | 400 | K6 |
| 非法/超限材料 | 失败路径 | 缺失 `x`/`y`、base64url 非法、超 10KB | 400 | 400 | K6 |
| 既有登记回归 | 兼容回归 | RSA/P-256/P-384/P-521 PEM/JWK | 行为不变 | 落库成功 | K6 / R6 |
| 既有测试同步 | 兼容 | `jwks.rs::test_unsupported_key_type_ec`、`key.rs` 相关用例 | 断言随 EC 分支语义更新；新增 SM2 用例 | 测试通过 | K5 / K6 |

## 5. 对外接口

本模块不新增/删除对外接口；对外接口变化体现为"认证契约扩展"（可接受 `alg` 新增 `SM2`）与"用户公钥登记契约扩展"（`public_key`/`jwk` 接受 SM2 材料）。字段、错误码与兼容策略的权威定义在对应"契约与工程落点"及 SR 设计第 4 章，此处仅索引。

| 接口编号 | 接口类型 | Method / Topic / Path / 名称 | 调用方 | 提供方 | 本次变化 | 关联契约 |
|---|---|---|---|---|---|---|
| API1 | REST（认证头） | `Authorization: Bearer <JWT>` / `Attest <JWT>`（作用于 `/rbs/v0/**` 受保护端点） | 外部调用方 | RBS（`rbs-core` 验签） | 修改（接受 `alg=SM2`） | K1 / K2 / K3 |
| API2 | REST | `POST /rbs/v0/users`、`PUT /rbs/v0/users/{username}` | 管理员 | RBS（`rbs-core` 登记） | 修改（接受 SM2 公钥 PEM/JWK） | K5 / K6 |

## 6. 数据库 / 表设计

不新增/删除表、字段、索引或约束，无 DDL 变更、无迁移与回填。

| 对象 | 变化类型 | 变化内容 | 兼容策略 | 回滚策略 |
|---|---|---|---|---|
| 表 `t_user_info` | 不变 | 结构不变 | 既有 SQLite 建表脚本无需修改 | 不适用（无结构变更） |
| 字段 `auth_value` | 不变 | 仍存 PEM 文本，新增可存 SM2 公钥 PEM | 既有数据不受影响 | 不适用 |
| 字段 `auth_alg` | 取值扩展 | 取值域扩展到可含 `SM2`（自由文本，无枚举约束） | 旧值 `RS256/ES*` 仍有效 | 回退到旧版本时 SM2 用户不可认证，需以支持 SM2 的版本运行 |

> 环境差异：`mysql_rbs.sql` 为占位脚本，属既有现状，与本需求无关。

## 7. 受影响模块与交互

### 7.1 受影响模块

| 模块 | 本次是否修改 | 边界说明（一句） |
|---|---|---|
| `rbs-core` | 是 | 新增 `authn/sm2`，扩展 `common`/`bearer_token`/`token`/`jwks`/`admin::key`；密码学与算法识别均在本模块 |
| `rbs-rest` | 否 | 仅透传令牌与编排，本次无结构改动（沿用既有中间件） |
| `rbs`（壳） | 否 | 配置加载与装配不变（不新增配置项） |
| `rbs-api-types` | 否 | 配置与 DTO 类型不变 |
| `rbs-cli`（`tools`） | 否（外部，另一模块） | 需产出与本模块契约一致的 SM2 令牌（K3）；不在本模块实现范围 |
| GTA 服务 | 否（外部提供方） | 以 SM2 签发 attestation token 并按 K3/K5 表示法下发公钥资料（待前置确认） |

### 7.2 模块交互概览

| 交互编号 | 发起方 | 接收方 | 交互方式 | 异常与重试 | 防腐 / 隔离说明 | 关联契约 |
|---|---|---|---|---|---|---|
| I1 | 外部调用方 / `rbs-cli` | `rbs-core`（验签） | REST（`Authorization` 头） | 验签失败 401，不重试 | 令牌为不透明串；算法白名单与 alg-密钥一致校验 | K1 / K2 / K3 |
| I2 | `rbs-core`（`AdminManager`） | `t_user_info` | 数据库（按 `sub` 查 `auth_value`） | 查询失败归一 401（对外掩盖） | trait `UserKeyProvider` 仅暴露 PEM，隐藏存储细节 | K4 |
| I3 | GTA（外部签发方） | `rbs-core`（Attest 验签） | 文件（PEM/JWKS 只读配置） | 配置失败启动期失败；选键失败 401 | 外部表示法与 JWK 字段经 K3/K5 收敛，不泄漏进内部结构 | K3 / K5 / K7 |
| I4 | 管理员 | `rbs-core`（登记） | REST 经 `rbs-rest` 路由 → `AdminManager` | 非法材料 400；重复 409 | 登记入口只暴露 PEM/JWK 语义，算法由 PEM 反推 | K5 / K6 |

## 8. 关键契约清单

| 契约编号 | 契约类型 | 名称 / Path / Topic | 权威定义位置 | 可测试性关注点 |
|---|---|---|---|---|
| K1 | Method / Constant | `authn::common::peek_raw_header`、`RawJwsHeader`、`SM2_ALG`、`SUPPORTED_ALGORITHMS_STR` | 4.1.3 | 主路径 / 失败路径 / 兼容 |
| K2 | Method | `authn::sm2::verify_sm2_jws` | 4.1.3 | 主路径 / 失败路径 / 安全 |
| K3 | Field（线格式） | JWS `alg="SM2"`、签名 `r||s`(64B)、SM3、Z 默认；JWK `kty/crv/x/y` | 4.1.3 / 4.3.3 | 兼容 / 互操作 / 安全 |
| K4 | DTO / 规则 | BearerToken SM2 分支 claims 校验规则 | 4.2.3 | 失败路径 / 兼容 / 安全 |
| K5 | DTO / Method | `authn::jwks::Jwk`（新增 `y`）、`jwk_to_pem` EC/SM2 | 4.3.3 | 主路径 / 失败路径 / 兼容 |
| K6 | Method | `admin::key::validate_and_derive_alg`、`admin::key::jwk_ec_to_pem` | 4.4.3 | 主路径 / 失败路径 / 兼容 |
| K7 | 构造 / 选键行为 | `AttestTokenVerifier::new` / 选键 | 4.3.3 | 主路径 / 配置失败 / 选键失败 |

## 9. 附录 / 三方件约束

| 主题 | 内容 | 影响 | 处理方式 |
|---|---|---|---|
| 三方件 | `openssl` 0.10.79（vendored OpenSSL 3.x），Apache-2.0 | 提供 SM2/SM3 能力；须确保验签使用 SM2 语义（含 Z 值） | 复用既有，不新增密码学依赖；SM2 运算统一走 `authn/sm2` |
| 三方件 | `jsonwebtoken` 10.3.0，MIT | 无 SM2 支持 | 仅用于既有算法；SM2 走独立分支，不弱化其校验 |
| 安全 / 密钥 | 令牌传输由 REST TLS 承载；RBS 不存用户私钥；日志不落令牌/密钥 | 密钥材料保护 | 复用既有约定 |
| 权限 / 合规 | 算法严格白名单，拒绝 `none`/跨算法验签；SM2 曲线 OID `1.2.156.10197.1.301`、SM3 摘要 | 国密合规 | 按本设计实现并回归验证 |
| 性能 / SLA | SM2 验签本地纯计算（无网络/无外部依赖） | 认证热路径新增极小 CPU 开销 | 目标与阈值见 SR 设计第 6 章（本模块不重复定义） |
| 已知限制 | `AuthError::UserDisabled` 声明但未使用（禁用状态不影响验签取键），属既有缺口 | 非本次引入 | 保持既有语义，不放大、不顺手治理 |
| 已知限制 | `mysql_rbs.sql` 为占位脚本 | 环境差异 | 属既有现状，与本需求无关 |
| 待确认 | GTA 侧 SM2 attestation token 与公钥的最终外部表示法（JWS `alg` 串、JWK `kty/crv/x/y`、签名 `r||s` 编码、Z 默认值） | 影响联合互操作验收 | <span style="color:red">需前置确认（上游 GTA 契约方）</span>；本模块按 K3/K5 约定实现，待 GTA 确认后复核，不阻断本模块编码与单侧验收 |
| 术语 | SM2（国密椭圆曲线签名，OID `1.2.156.10197.1.301`）、SM3（国密摘要）、Z 值（SM2 用户标识）、JWKS/JWK、JWS 紧凑序列化 | — | — |
