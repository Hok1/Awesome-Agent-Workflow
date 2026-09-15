# dev-design-gate 质量测评标准 —— SR-2 rbs-cli --expires-in（轻量链路，正/反双例）

> 版本：v1.0（2026-09-15）
> 用途：作为 skill-eval 测评平台对 `dev-design-gate` skill 打分的输入标准。
> 立场：task-split 的准入闸口视角。不问"报告写没写"，只问"三项准入是不是真查了"。

---

## 0. 被测评需求是什么

- **SR 编号**：SR-2（dev 轻量链路的测评载体，与 SR-1 的 sr 重链路区分）
- **需求**：rbs-cli `token gen` 新增 `--expires-in <秒>` 相对过期参数（与 `--exp`
  互斥；非法输入明确报错）——真实代码现状： `tools/src/token/cmd.rs:177` 已有
  `exp: Option<u64>`，:329 为计算点，:506 为时间校验。夹具的 file:line 引用全部真实。
- **交付物**：`.sdd/SR-2/.context/dev-design-gate.md`（yaml required output）

**这项任务的业务实质**：dev-design-gate 是轻量链路进任务拆分前的唯一闸口，
只查三件事：决策已收敛（无「待定/可选/看情况」）、代码论断可回溯（file:line
经取证）、契约与验收可执行（覆盖矩阵覆盖全部验收标准与契约变更项）。
它「不复查设计过程、不挑常规建议」——判定面窄而硬，适合确定性断言。

**双例设计**（setup 互斥，两个 suite）：
- **正向 clean**：手写合规 dev-design.md + test-design.md（七节/四 TC/覆盖矩阵齐）。
- **反向 defect**：方案插入「待定，看情况再定」（检查项 1）；覆盖矩阵删 A3 行
  （检查项 3）。期望：不通过 + 需整改项命中检查项 1 与 3。

**判据保密纪律**：断言脚本不进 workspace、task 不复述 skill 规则。

---

## 1. 打分总则

1. **判据全部确定性。** 单条 `command` grader（weight=100）。
2. **0-100 分锚点**：全过 100，任一失败 0。
3. **no_skill 组仅作参考**（语料先验已知）。
4. **诚实记录局限**：「代码论断可回溯」的真伪核验（file:line 是否指向真实内容）
   未作断言——它需要对 RBS 代码逐行比对，本次只判形态（论断带 file:line）。

---

## 2. 硬性门槛（对应断言条款）

### 正向/反向共用（assert_devgate_common.py，7 条）

| # | 断言 | 出处 |
|---|---|---|
| 1 | 报告存在于契约路径 | yaml output required |
| 2 | 两输入 sha1 不变 | 「门禁阶段只读……不修改设计正文」 |
| 3 | 结论 ∈ {通过/不通过/阻塞} | 结论判定表 |
| 4 | 建议 ∈ 三值枚举 | gate-report.md 骨架「建议」行 |
| 5 | 三检查项名逐项出现 | 「每项给出 达标/未达标 判定」「逐项判定，没有跳过」 |
| 6 | 结论-统计一致（通过⇒三计数全 0；不通过⇒unqualified>0 且指明整改对象） | 具体流程 5 + 报告边界 |
| 7 | —（并入 6） | — |

### 反向追加（assert_devgate_defect.py，2 条）

| # | 断言 | 出处 |
|---|---|---|
| 7 | 结论不得为「通过」 | 「任一检查项未达标……不得通过」 |
| 8 | 「需整改项」章节命中检查项 1 与检查项 3（判定落点在整改区，防判定表骗检） | 3 项准入检查表 + 「未达标项必须指明问题出处与整改方向」 |

---

## 3. 判据落点

- 正向 grader：`python C:\tmp\ctx5dg2\assert_devgate_common.py`
- 反向 grader：`python C:\tmp\ctx5dg2\assert_devgate_defect.py`（内部先跑 common）

## 4. 判定纪律

1. **先红后绿。** 13 个合成用例（正向 1 绿 + 7 红；反向 1 绿 + 4 红），
   0 个不符预期；见 `fixture/redgreen/`。
2. **断言必须有出处。** §2 逐条标注。

---

## 5. 实测记录（2026-09-15）

| 项 | 值 |
|---|---|
| 套件（正向） | `dev-design-gate-SR2-clean-eval` / `85017e9d-31cc-4fbb-9d99-b35d478f6d8a` |
| 实验（正向） | `21205abb-4e5e-4300-ad1f-191527bda6bc`，`quick` |
| 套件（反向） | `dev-design-gate-SR2-defect-eval` / `ac681f71-0b60-4995-a004-2c6b891b6de2` |
| 实验（反向） | `6170b0df-b763-40f7-806c-4f41fcc5f0ea`，`quick` |
| profile | chrys / `e5d1a7b2c901`（DeepSeek 官方 `deepseek-v4-pro`）/ high，无网络 |
| 项目基线 | `globaltrustauthority-rbs` @ `7ef62cd3` |

**结果**：

| 用例 | 组 | 结论 | 判分 |
|---|---|---|---|
| clean | current | 不通过 | 100（形式合规） |
| clean | no_skill | 通过 | 100（形式合规） |
| defect | current | 不通过 | 100（命中检查项 1+3） |
| defect | no_skill | 不通过 | 100（命中检查项 1+3） |

**正向 current 组判「不通过」且完全正当**——它抓到了夹具自身的两处真实瑕疵
（测评设计方的失误，被 gate 正确识别，这是本 skill 价值的最佳证据）：

1. **代码论断可回溯（未达标）**：夹具把 clap 参数结构误称 `TokenGenerate`；
   gate 读真实代码确认实际是 `GenerateArgs`（cmd.rs:132），`TokenGenerate`
   是无字段单元结构（cmd.rs:227）——file:line 级核验真做了。
2. **契约与验收可执行（未达标）**：需求要求「0、负数、溢出」三类非法输入，
   夹具只覆盖 0；且夹具论断「负数自然命中既有 exp 校验」与代码事实矛盾
   （`Option<u64>` 在 clap 解析层即拒绝负值）——论断-代码矛盾被抓。

no_skill 组对同一夹具判「通过」——**它没做 file:line 核验就放了行**。
正向用例因此出现了实质分差（current 抓真问题 / no_skill 漏判），
尽管判分同为 100（形式断言的粒度），语义差异记录在案。

**资源备注**：DeepSeek 官方端点 `deepseek-flash` 池在 2026-09-15 凌晨持续过载
（四个 run 全部 900s 服务超时、agent_error），本测评切换 `deepseek-v4-pro`
完成。初轮失败实验（`b61cf321`/`d7b01d08`）结果作废，不计入。
