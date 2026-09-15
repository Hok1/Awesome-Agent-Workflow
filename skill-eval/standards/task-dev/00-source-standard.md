# task-dev 质量测评标准 —— RBS 国密 SM2 / rbs-core T1 端到端实现（SR-1）

> 版本：v1.0（2026-09-15）
> 用途：作为 skill-eval 测评平台对 `task-dev` skill 打分的输入标准。
> 立场：串行流水线与代码评审的下游视角。不问"代码写没写"，只问
> "这次实现能不能在不越权、不越界的前提下编译并通过测试"。

---

## 0. 被测评需求是什么

- **SR 编号**：SR-1（RBS 国密 SM2 需求链路的第九个测评点，sr 链终端节点）
- **代码仓**：`globaltrustauthority-rbs`（基线 commit `7ef62cd`）
- **任务**：tasks-overview 的 **T1（SM2 验签能力与 Bearer 用户认证）**——新增
  `authn/sm2.rs` 验签子模块、JWT 头部 `alg` 原始预解析与分派、Bearer 路径接入；
  允许改动 `authn/{mod,common,sm2,bearer_token}.rs` 与测试位置；验证 TC1–TC6、
  TC13–TC16、TC23 共 11 条用例。
- **交付物**：无独立文档（yaml `output: []`）——交付物是**代码与 workspace 落态**。

**这项任务的业务实质**：task-dev 是 SDD 链路里唯一动生产代码的环节，也是唯一
"错了直接进仓库"的环节。它的硬纪律：绝不执行 git add/commit/push（候选提交信息
只生成不落地）；严格按已评审设计实现（不重命名契约、不丢字段、不提前实现后续
Task）；受影响测试必须真跑真过；tasks-overview 执行记录必须回填（含必填小节
「实现期补充与残余风险」，缺失会被 done 拒绝）。

**与前八个测评点的本质区别**：断言对象从「文档形态」变为「**代码落态**」——
git 状态、改动范围、cargo 编译与测试结果。其中 `cargo test -p rbs-core --lib`
是整条链路里最强的确定性判据：代码写不对就是编译不过或测试红。

**输入全部为真实链路产物**：tasks-overview 来自 task-split 实验 `f451a054` 的
current 组；三件套同 module-design-gate 测评。

**harness 适配声明（诚实记录）**：
- 单独执行模式（跳过 CLI 状态协议与 done 回调）——SKILL.md 调度边界明文允许。
- 无并行 SubAgent：语义 Review 由主 Agent 以只读方式按 A/B 双视角完成并落盘——
  SKILL.md 未给该环节的降级条款，此适配写在 task 输入中明示。
- 无 aaw CLI / code-check 扫描器：CodeCheck 环节以 cargo 构建/测试替代——同上。
- 无 MCP、无网络：SM2 测试向量只能自签自验（OpenSSL vendored 具备 SM2 能力），
  这本身就是对「实现期判断」的真实考验。

**判据保密纪律**：断言脚本不进 workspace、task 不复述 skill 规则。

---

## 1. 打分总则

1. **判据全部确定性。** 单条 `command` grader（weight=100），workspace 外执行，
   grader 内部调 git/cargo。
2. **0-100 分锚点**：全过 100，任一失败 0。
3. **一次有效测评即够。** no_skill 组仅作参考。
4. **诚实记录局限。** (a) cargo 断言覆盖编译与 lib 内测试，不覆盖测试质量
   （断言写没写对属语义评审）；(b) 「语义 Review 双视角」在 harness 中由
   主 Agent 兼任，该环节的形态不作硬断言；(c) run 可能因模型编码能力不足而失败
   ——这是有效测量结果，不是体系故障。

---

## 2. 硬性门槛（对应断言条款）

| # | 断言 | 出处 |
|---|---|---|
| 1 | git HEAD == 基线 commit 且暂存区为空 | 调度边界「绝不执行 git add、git commit、push」 |
| 2 | tasks-overview「执行记录」含 T1 小节：状态 Completed + 「实现期补充与残余风险」 | §5「必填小节……缺失会被 done 拒绝」 |
| 3 | 代码改动 ⊆ T1 允许范围（T1 四文件 + 测试位置），不提前实现 T2/T3 | §1.4「不提前实现后续 Task」；范围由 tasks-overview T1 行给出 |
| 4 | 新增 `rbs/core/src/auth/authn/sm2.rs` | tasks-overview T1「改哪些文件」（新增） |
| 5 | 存在新增/修改的自动化测试（`#[test]` / `#[cfg(test)]`） | §1.5「落实为自动化测试」 |
| 6 | `cargo test -p rbs-core --lib` 退出码 0 | §1.7「执行全部非待处理测试，逐项核对预期结果」+ §1.8 |

---

## 3. 判据落点

单条 `command` grader：`python C:\tmp\ctx5tdv\assert_taskdev.py`，
cwd = run 工作区，退出码 0 得 100，非 0 得 0，grader timeout 900s（含 cargo）。

## 4. 判定纪律

1. **先红后绿。** 8 个合成用例（1 绿 + 7 红，迷你 git 仓），0 个不符预期；
   cargo 断言在迷你仓以 `TD_SKIP_CARGO=1` 跳过（红绿不验 cargo，实测真验）。
   见 `fixture/redgreen/`。
2. **断言必须有出处。** §2 逐条标注；范围/基线由 tasks-overview 与 git 自身给出。
3. **范围控制。** 不评实现优雅度，只评纪律与可验证正确性。

---

## 5. 实测记录（2026-09-15）

| 项 | 值 |
|---|---|
| 套件 | `task-dev-SR1-rbcore-T1-eval` / `9ec3e820-e012-470a-a8a0-8301a18bed0a` |
| 实验（定稿轮） | `7af6f97a-6157-4d47-a3c6-699c0491f748`，`quick` |
| 被测 skill 版本 | `task-dev` revision（见 05-meta.json） |
| profile | chrys / `e5d1a7b2c901` / high，无网络 |
| 项目基线 | `globaltrustauthority-rbs` @ `7ef62cd3` |

**结果**：

| 组 | quality_score | cargo test | 耗时 |
|---|---|---|---|
| `current`（被测） | **100.0**（全过） | exit=0（编译+lib 测试通过） | 3,385.7 s |
| `no_skill` | **0.0** | exit=0（同样编译测试全过） | 3,602.6 s |

**本次测到了 skill 的增量价值（真实区分度）**：两组的代码实现质量相当——
都新增了 `authn/sm2.rs`、都接入 Bearer 路径、改动都在 T1 范围内、cargo test
全过。唯一差异：no_skill 组**没有回填「实现期补充与残余风险」必填小节**
（SKILL.md §5 强制交接检查项，「缺失会被 done 拒绝」）。代码能力模型自带，
交接纪律是 skill 教的——这正是本 skill 的存在意义。

**环境排障链（本次最深的三个坑，全部实锤修复）**：

1. `copytree` 复制 target/ → 内嵌绝对路径失效 → LNK1104（workspace 嵌套路径超
   Windows MAX_PATH 260）。修法：setup 清 target + grader 用 `subst Z:` 短盘符构建。
2. vendored OpenSSL 3.6.2 配置失败：registry 缓存的 openssl-src 缺
   `util/providers.num`（crate 包本身缺该文件）。修法：从官方 tarball 补齐
   （用户批准后执行）。
3. Git 自带 MSYS perl 抢 PATH 优先导致 OpenSSL Configure 失败。修法：
   构建时前置 `C:\Strawberry\perl\bin`（runner 侧经 task 明示，grader 侧在断言脚本
   内置）。
4. DeepSeek 官方端点 `deepseek-flash` 池持续过载（900s 服务侧超时 ×4），
   先后切 `deepseek-v4-pro`、再按用户指示切 zybxx 中转（claude-opus-5）。
   定稿轮两组的 run 均在渠道切换前启动（DeepSeek pro 完成），口径如实记录。

**判据迭代**：v1（原渠道额度耗尽）→ v2（target 复制 LNK1104）→
v3（OpenSSL/perl 环境）→ v4 定稿。断言本身在 v2 修过一次解析
（git porcelain 行从 index 2 起取路径并 strip，兼容状态码宽度差异）。
