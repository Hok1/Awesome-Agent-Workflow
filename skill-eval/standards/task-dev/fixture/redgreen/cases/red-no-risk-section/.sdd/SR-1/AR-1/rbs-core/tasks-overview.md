# rbs-core 任务计划

## 执行记录

### T1：SM2 验签能力与 Bearer 用户认证

- 状态：Completed
- 修改文件：rbs/core/src/auth/authn/sm2.rs（新增）
- 核心实现：SM3+SM2 验签
- 设计偏差：无
- 待处理：无

#### 其他

- 补测：签名 r||s 长度异常的拒绝路径
- 残余风险：无
