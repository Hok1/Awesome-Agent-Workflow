交付 .sdd/SR-1/SR-design.md，按 aaw sr-design 模板生成完整章节，并满足以下业务标准（详见每个 grader 的 rubric）：
HG-1 钉死交付范围：明确包含 SM2 签名/验签（含作为其内部摘要的 SM3），明确不包含 SM3 独立能力、SM4、双证书，并给出依据。
HG-2 GTA 互操作契约精确到字节：DER SEQUENCE（r,s）编码、签名输入为前两段原始 ASCII 字节且不预哈希、Z 值 UserId 1234567812345678、alg 固定 SM2、jku/kid 不参与验签、exp 等于 iat 加 expired_time（默认600秒）、iss 默认 Global Trust Authority、jti 不做重放跟踪、公钥为 SPKI PEM 静态配置且无 JWKS、时钟容差正负 30 秒。
HG-3 关键规格逐条映射到能证伪它的黑盒用例编号。
HG-4 六个主干章节不得标"不适用"；验收用例覆盖六类对象；三个原始需求触点各有对应用例。
另按 D1-D7 七个加权维度打分，权重合计 100。