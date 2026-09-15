T1 完成后的 workspace 落态：

- git HEAD 不变、无暂存区改动（绝不 git add/commit）。
- tasks-overview.md 的「执行记录」中有 T1 小节：状态 Completed + 必填的
  「实现期补充与残余风险」小节。
- 代码改动不超出 T1 范围（authn/mod.rs、common.rs、sm2.rs、bearer_token.rs 及
  测试位置）；不提前实现 T2/T3。
- 新增 rbs/core/src/auth/authn/sm2.rs；存在新增/修改的自动化测试。
- `cargo test -p rbs-core --lib` 退出码 0。

依据：task-dev SKILL.md 调度边界、固定流程 §1/§5、tasks-overview T1 行。
