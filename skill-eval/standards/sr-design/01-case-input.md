你使用 sr-design skill 为下面这个 SR 产出功能/模块设计文档。

【SR 编号】SR-1

【原始需求原文】
1. SR编号：SR-1
2. 需求人：目前SM2算法没有应用在此代码仓。需要用户认证支持SM2算法、验证 GTA 签发的 SM2 attestation token、rbs-cli 生成 SM2 token。

【第一步：先落地原始需求文件】
先创建目录 .sdd/SR-1/，把上面的原始需求原文完整写入 .sdd/SR-1/original-requirement.md（sr-design 规定该文件为权威需求来源）。然后读取该文件，以其为基准开展工作。

【工作目录】当前目录（globaltrustauthority-rbs，Rust workspace）。

【本次执行方式（重要，请严格遵守）】
1. 你是无头执行，没有人类在旁回答问题。sr-design 前置工作流确认环节请跳过：不要回调 aaw-workflow，不要选池，直接执行该 skill 正文。
2. 模板：读取本仓库 .aaw-eval/skills/sr-design/reference/design-template.md，严格按该模板的章节结构与占位符要求产出文档。
3. 本环境不提供 question-tracker MCP。问题澄清环节不要真正调用工具、也不要等待回答：本提示末尾【预设答案】给出的就是全部设计决策的最终答案，直接采用，视同已由需求人确认。
4. 【预设答案】与原始需求文件同为权威输入。凡预设答案已明确的事项，直接据此刻画；不要另行推断，不要标注"待确认"，不要留占位符或 TODO。
5. 最终交付：把完整的 SR 设计文档写入 .sdd/SR-1/SR-design.md，严格遵循模板的全部章节与占位符要求。
6. 最后回复：给出文档路径、章节清单，以及你在设计过程中做出的关键取舍（尤其是功能合规范围边界、与 GTA 的互操作契约、为何新增/收敛模块）。

【预设答案（全部设计决策，直接采用）】
按工程默认值继续，不要再次向我确认。以下为逐条决策，请据此刻画完整设计并直接产出文档。

【用户认证侧】复用现有用户注册与更新接口，不新增端点。token 仍只支持 jwt 一种 auth_type，auth_alg 取值域扩展为 HMAC-SHA256 与 SM2 两种；SM2 令牌沿用现有的 token derive 接口签发。一个令牌只使用一种签名算法，本次不支持同一令牌多算法。算法选择落在 auth_alg 字段。

【GTA attestation token 侧】GTA 签发的 SM2 token 是 JWT，签名算法 SM2 with SM3。签名值编码为 ASN.1 DER SEQUENCE r,s，不是裸 r 与 s 拼接。Z 值取 OpenSSL 默认 UserId 1234567812345678。签名输入是 token 前两段 JWS Signing Input 的原始 ASCII 字节，不预先哈希。header.alg 固定为 SM2，typ 为 JWT；jku 与 kid 有默认值但不参与验签。exp 等于 iat 加上 expired_time，按 auth.attest_token.expired_time 配置，未配置时取 GTA 默认 600 秒。iss 默认 Global Trust Authority。jti 为 UUID v4，不做重放跟踪。时钟容差正负 30 秒。attestation 公钥为静态配置，由 auth.attest_token.public_key_path 指向 SPKI PEM 文件，GTA 不提供 JWKS。

【rbs-cli 侧】在 rbs-cli 的 token 子命令下新增生成能力，通过参数选择算法，SM2 在其中。

【合规边界】本次只交付 SM2 签名与验签，以及作为其内部摘要的 SM3。SM3 的独立对外能力、SM4 加解密、双证书体系均不在本次范围，依据是原始需求只提出 SM2 用于认证、attestation 校验与令牌生成三处。该边界请在设计文档中显式声明。

请直接生成完整的 SR-design.md 并写入 .sdd/SR-1/SR-design.md。不要再提问，不要再等待确认。