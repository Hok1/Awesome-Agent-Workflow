# AR-1 需求澄清（SM2 用户认证）

> 本文件为 ar-clarify 阶段的确认记录（测评夹具，模拟已澄清完成态）。

## AR 拆分决定

SR-1（RBS 支持国密 SM2）拆分为单个 AR：

- **AR-1：SM2 用户认证与令牌支持**——rbs-core 验签与用户公钥登记、rbs-cli SM2 令牌生成。
  （范围较小且高内聚，记录免拆分决定，仅一个 AR。）

## AR-1 已确认决策

1. 用户认证接受 SM2 私钥签名的用户 JWT（BearerToken），管理员可登记 SM2 公钥。
2. RBS 验证 GTA 签发的 SM2 attestation token（AttestToken）。
3. rbs-cli `token gen` 支持 SM2（属 rbs-cli 模块范围，与 rbs-core 的互操作约定保持一致）。
4. 已确认约束：SM2 作为新增可接受算法接入，不替换、不移除任何既有算法；
   不引入新的密码学三方件（复用 vendored OpenSSL）；用户私钥不进入 RBS 服务。
5. 验收口径：`alg=SM2` 用户令牌与 GTA SM2 attestation token 均可验签通过；
   既有算法行为与错误语义不变；无数据库结构变更。

## 待上游确认项（不阻断本模块设计）

- GTA 侧 SM2 JWK/JWS 表示法与 Z 用户标识的最终一致性，由 GTA 侧确认为准。
