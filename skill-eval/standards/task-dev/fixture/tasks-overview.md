# rbs-core 任务计划

## 元信息

- SR 编号：SR-1
- AR 编号：AR-1
- 来源详细设计文档：.sdd/SR-1/AR-1/rbs-core/模块详细设计说明书.md
- 来源测试用例设计文档：.sdd/SR-1/AR-1/rbs-core/模块测试用例设计.md
- 来源模块设计门禁结果：.sdd/SR-1/AR-1/rbs-core/.context/模块设计门禁结果.md
- 门禁结论：通过
- 任务总数：3
- 生成时间：2026-09-14

## 执行规则

- 详细设计文档是实现设计的唯一事实来源，测试用例设计文档是验证规格的唯一事实来源。开发每个任务前必须完整读取这两份文档和门禁结果。
- 按串行执行顺序逐个执行，编号与顺序一致；同一时刻只开发一个任务。
- 详细设计或测试设计发生变化时，停止开发，返回设计门禁并重新生成、确认任务计划。

## 串行执行顺序

```text
T1 → T2 → T3
```

## 任务计划

| 编号 | 任务 | 做什么 | 改哪些文件 | 验证哪些用例 | 前置 |
|---|---|---|---|---|---|
| T1 | SM2 验签能力与 Bearer 用户认证 | 让 SM2 用户令牌能通过用户认证：新增 JWT 头部算法的原始预解析与按算法分派入口；新增集中承载 SM2（SM3+SM2）验签的认证子模块，复用既有 OpenSSL、不新增密码学依赖；在 Bearer 用户令牌校验路径接入 SM2 分支，使其 claims 校验语义与既有路径一致后返回用户认证上下文。 | `rbs/core/src/auth/authn/mod.rs`、`rbs/core/src/auth/authn/common.rs`、`rbs/core/src/auth/authn/sm2.rs`（新增）、`rbs/core/src/auth/authn/bearer_token.rs` | TC1、TC2、TC3、TC4、TC5、TC6、TC13、TC14、TC15、TC16、TC23 | 无 |
| T2 | GTA attestation SM2 验签与 JWKS EC/SM2 支持 | 让 GTA 用 SM2 签发的 attestation token 能通过资源访问认证：attestation 令牌校验器在构造期接受 SM2 公钥（直连 PEM 或 JWKS）且不因 SM2 曲线在启动期失败，验签期对 SM2 令牌完成 SM3+SM2 验签；扩展 JWKS 解析以支持 EC/SM2 键，其余 EC 曲线仍被拒绝。 | `rbs/core/src/auth/authn/token.rs`、`rbs/core/src/auth/authn/jwks.rs` | TC7、TC8、TC17、TC18、TC19、TC20、TC22、TC24、TC25 | T1 |
| T3 | SM2 用户公钥登记与闭环验签 | 让管理员可通过既有用户登记入口登记 SM2 用户公钥：登记校验与 JWK→PEM 转换支持 SM2 材料，由公钥推导算法标识为 SM2 并落库；随后以该用户的 SM2 令牌完成从登记到认证的闭环验签。 | `rbs/core/src/admin/key.rs`、`rbs/core/src/admin/manager.rs`（测试）、`rbs/core/tests/admin_sm2_registration_tests.rs`（新增） | TC9、TC10、TC11、TC12、TC21、TC26、TC27 | T1 |

> 粒度说明：本次变更集紧凑且复杂度高（SM2 密码学、算法分派、两条验签链路、公钥登记），按“可独立验收的业务结果”划分为 3 个纵向闭包；SM2 核心能力与首个消费链路合并在 T1，避免按技术分层拆分（“核心函数一个任务、接线一个任务”），各任务不刻意填充至行数锚。

计划表不保存阶段进度。`task-dev` 只在「执行记录」中写最终 `Completed` 或 `Blocked` 交接。

## 存疑汇总

任务计划确认前本节必须为空。若存在问题，使用下表记录并返回对应上游阶段处理。

| 编号 | 存疑项 | 涉及任务 | 需要确认的问题 | 回流阶段 |
|---|---|---|---|---|

## 待处理用例登记

仅登记不影响当前任务主要完成状态的补充性验证；核心验证不得待处理。

| 用例编号 | 所在任务 | 依赖任务 | 当前无法执行原因 | 最终责任任务 | 状态 |
|---|---|---|---|---|---|

状态取值：`Pending` / `Passed` / `Failed`。

## 执行记录

由 `task-dev` 在每个任务完成或阻塞时追加一条记录；`task-split` 不预填。
