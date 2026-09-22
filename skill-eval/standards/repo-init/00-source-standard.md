# repo-init 质量测评标准 —— RBS 仓 SDD 初始化（全新场景）

> 版本：v1.0（2026-09-15）
> 用途：作为 skill-eval 测评平台对 `repo-init` skill 打分的输入标准。
> 立场：下游 module-asis-analysis 的视角——它把 `.sdd/software_architecture.md`
> 当作唯一模块边界来源，这份文档写错，下游全部爆炸。

---

## 0. 被测评需求是什么

- **代码仓**：`globaltrustauthority-rbs`（基线 commit `7ef62cd`）——**无 `.sdd/`、
  无 `AGENTS.md`**，全新初始化场景（非复用已有基线）。
- **交付物**：`.sdd/software_architecture.md` + `AGENTS.md`（+ spec.md 视语言而定）
- **链路价值**：本测评链路的 ASIS/TOBE/门禁全靠架构文档做边界基线——此前四个
  测评点用的架构文档是手写夹具；repo-init 若工作正常，它本该是这份文档的
  生产者。这是对「初始化质量」的直接检验。

**可测性与适配**：无 MCP。SKILL.md 各 Phase 假定可派发 SubAgent——harness 无
SubAgent，task 明示由主 Agent 完成同等只读勘察。Phase 7 的用户确认在无头环境
改为「输出提醒即结束」（task 明示）。spec.md 的语言模板表无 Rust 分支——
观察 runner 如何处理（记录，不硬断言）。

**判据保密纪律**：断言脚本不进 workspace、task 不复述 skill 规则。

---

## 1. 打分总则

1. **判据全部确定性。** 单条 `command` grader（weight=100）。
2. **0-100 分锚点**：全过 100，任一失败 0。
3. **no_skill 组仅作参考**。

---

## 2. 硬性门槛（对应断言条款）

| # | 断言 | 出处 |
|---|---|---|
| 1 | `.sdd/software_architecture.md` 存在 | Phase 4；下游 module-asis-analysis 的唯一边界来源 |
| 2 | 豁免区（目录/1.2/1.3）之外 `{{` 占位符清零 | Phase 4「Fill in all placeholders……do NOT modify or fill in section 1.2/1.3/目录」 |
| 3 | 模块职责表落到真实路径 ≥2，且产物引用的 rbs/rbc/tools 形态路径全部真实存在 | 模板 2.1「当前代码仓下相对路径」列 + 边界来源必须真实 |
| 4 | 模板固定章节保留（目录/系统概览/模块清单） | 模板结构 |
| 5 | `AGENTS.md` 存在且识别 cargo 命令与 Rust 语言 | Phase 5「Detect: Build, test, and lint commands; Languages…」 |

---

## 3. 判据落点

单条 `command` grader：`python C:\tmp\ctx5ri\assert_repoinit.py`，
cwd = run 工作区，退出码 0 得 100，非 0 得 0。

## 4. 判定纪律

1. **先红后绿。** 8 个合成用例（1 绿 + 7 红，含豁免区边界与伪造路径），
   0 个不符预期；见 `fixture/redgreen/`。
2. **断言必须有出处。** §2 逐条标注。

---

## 5. 实测记录（2026-09-15）

| 项 | 值 |
|---|---|
| 套件 | `repo-init-rbs-eval` / `8e073c69-8621-4600-88ff-e285280f5ae6` |
| 实验（定稿轮） | `e8571363-7df2-4e6a-9e1f-05c7b0a8630c`，`quick` |
| 被测 skill 版本 | `repo-init` revision `80d0a95b…` |
| profile | chrys / `e5d1a7b2c901`（DeepSeek 官方 `deepseek-v4-pro`）/ high，无网络 |
| 项目基线 | `globaltrustauthority-rbs` @ `7ef62cd3` |

**结果**：

| 组 | quality_score | 产物 | 耗时 |
|---|---|---|---|
| `current` | 100.0 | 架构文档 6,222 字符 + AGENTS.md | 293.3 s |
| `no_skill` | 100.0 | 架构文档 6,197 字符 + AGENTS.md | 538.7 s |

两组均满足全部断言：豁免区外占位符清零、5 个真实模块路径全中、AGENTS.md
识别 cargo/Rust。current 组快 1.8 倍（模板与 Phase 指引减少勘察往返）。

**断言的一轮修正**：初版防伪路径检查把「crate 名/职责域」写法（`rbs-core/auth`）
误判为文件路径引用。修正为只核验「模块根深入 src/tests/文件」形态的引用；
红绿补「crate/域 写法不算路径」绿用例后重跑。初轮实验（`a901a933`）的
current 组因服务中断 infra_error、no_skill 组因该误报判 0，均作废不计入。

**spec.md 语言分支观察**：SKILL.md Phase 3 的语言模板表（c/c++/java/python/js）
无 Rust 分支。两组 runner 均未生成 spec.md——对「无匹配分支」的静默跳过。
SKILL.md 未规定该情形的处置（记录上报，不顺手改）。
