# skill-eval 证据链缺陷：评分依据缺失与评测环境污染

**关联 Issue**：待提交
**状态**：待整改（仅根因分析，整改计划另行提出）
**发现日期**：2026-09-11
**发现场景**：L2 端到端手工测试（toy-structured-report，no_skill vs current 盲评对比）

## 背景

L2 测试中 no_skill 组得 30 分、current 组得 85 分，分差方向符合预期。但逐条核对产物时发现：**两组 run 的 `changes.patch` 均为 0 字节，而 judge 却给出了 85 分的详细评分理由**。顺此线索追查，暴露 4 个相互关联的缺陷。

## 问题清单

### 问题 1｜未跟踪文件的内容未进入 judge 证据（严重）

**现象**

judge 在其 reasoning 中明确记录了自身的证据缺失：

> 但 `git_patch` 为空，无法直接核对 REPORT.md 全文细节与章节内措辞……故未给满分，定 85。

**实证**

| 证据 | 内容 |
|---|---|
| `artifacts/.../6b6c765d.../changes.patch` | 0 字节 |
| `artifacts/.../e458f337.../changes.patch` | 0 字节 |
| `artifacts/.../6b6c765d.../untracked.zip` | 含真实 `REPORT.md`（2282 字节） |
| `artifacts/.../e458f337.../untracked.zip` | 含真实 `REPORT.md`（2066 字节） |

**根因（机制层）**

`services/repository.py:152`：

```python
patch = _git(workspace, "diff", "--binary", "HEAD", timeout=120)
```

`git diff HEAD` **按 Git 的设计**只输出已跟踪文件的变更，新建文件（untracked）天然不在其中。而本次评测任务的产物形态恰恰是「新建 `REPORT.md`」——即**只要被测任务是产出新文件，该字段必然恒为空**。

传导链路：

```
repository.py:152   git diff HEAD        → 未跟踪文件不参与
orchestrator.py:257 capture_changes()
orchestrator.py:263 evidence["git_patch"] = changes["patch"]
orchestrator.py:768 judge payload.evidence
                    → judge 最终只拿到 agent 的 final_response 自述
```

**影响**

judge 的 `llm_rubric` 评分实际依据是 **agent 的自我陈述，而非产物本身**。这构成方法论级缺陷：agent 只要在 `final_response` 中声称「我写了三章节报告」，judge 无从核对。评分有效性依赖被测方的诚实度，盲评的客观性被削弱。

---

### 问题 2｜未跟踪文件已归档，但未回喂 judge（中等）

**现象**

平台**已经**正确识别并归档了未跟踪文件，却未将其用于评审。

**实证**

`orchestrator.py:290-292` 调用 `archive_untracked()` 将未跟踪文件写入 `untracked.zip`，`run.json` 中 `untracked_archive: ["REPORT.md"]` 记录完整。

但 `orchestrator.py:261-269` 构造的 `evidence` 字典中**不含**该归档内容。

**根因**

归档动作（`orchestrator.py:290`）与证据构造（`orchestrator.py:261`）是两段独立代码，归档产物从未回流至 `evidence`。判明为**遗漏而非设计取舍**：作者已专门编写未跟踪文件的归档逻辑，说明意识到了这类文件的存在，只是评审链路上漏接一步。

**影响**

修复成本极低（数据已在手），但当前 judge 完全无法利用。

---

### 问题 3｜评测元数据目录 `.aaw-eval/` 暴露给被测 agent（严重）

**现象**

no_skill 组的产出报告在「Repository Layout」表格中列出了评测基础设施目录：

| Path | Purpose |
| --- | --- |
| `.aaw-eval/` | Evaluation harness metadata (not part of the product). |

**即：被测 agent 明确感知到了自己正身处评测环境。**

**实证**

- agent 产出：`artifacts/.../6b6c765d.../untracked.zip → REPORT.md` 第 4 节表格
- 平台快照：同 run 的 `file-tree.json` 内容为 **仅** `README.md`、`REPORT.md`、`src/main.py` —— **不含 `.aaw-eval/`**

两者矛盾，指向问题根因。

**根因（机制层）**

`services/skills.py:163-182` `prepare_eval_workspace()` 在**工作区根目录**创建 `.aaw-eval/skills`：

```python
runtime_root = workspace / ".aaw-eval"
skill_root = runtime_root / "skills"
skill_root.mkdir(parents=True)
```

该函数在 `orchestrator.py:235` 被**无条件调用**（位于 `if selected is not None` 判断之前），因此 **no_skill 组同样会创建工作区根下的 `.aaw-eval/`**（内容为空目录）。

该目录仅被写入 `.git/info/exclude` 以对 Git 隐藏：

```python
rules = ("/.aaw-eval/", "/.agents/skills/aaw-eval-*/")
```

**但它只影响 Git 的视图，文件系统上物理存在**，agent 通过 `ls` / `find` 可直接观测。

**影响（双重）**

1. **实验效度被威胁（污染 baseline）**：no_skill 组的语义是「无 skill 的基线行为」。该组 agent 看到 `.aaw-eval/` 后，会推断自己处于评测环境并主动在报告中标注「not part of the product」。**基线组不该知道自己正在被评测**——这引入了与 skill 无关的行为差异，削弱 A/B 对比的可比性。
2. **证据链自相矛盾**：`file-tree.json` 过滤掉了 `.aaw-eval/`，agent 却真实看到并提及了它。judge 因此面对一份「响应提到、证据中不存在」的目录，无从判断其真伪，可能误判为幻觉。

---

### 问题 4｜过滤规则分散两处、各自硬编码（轻微，可维护性）

**现象**

对 `.aaw-eval/` 的过滤逻辑在两个文件中各写了一份，判定方式互不相同：

| 位置 | 判定方式 | 作用域 |
|---|---|---|
| `repository.py:171` | `path.startswith((".aaw-eval/", ".agents/skills/aaw-eval-"))` | `capture_changes` |
| `repository.py:191` | `not (current == workspace and directory == ".aaw-eval")` | `file_tree_manifest` |
| `storage.py:47` | `(".git/", ".aaw-eval/", ".agents/skills/aaw-eval-")` | 归档 |

**根因**

三处硬编码字符串，无单一真相源。第二处的判定条件（`current == workspace`）与前两处的前缀匹配**语义并不等价**——嵌套目录中的 `.aaw-eval/` 不被过滤。规则漂移风险高。

**影响**

当前不致错，但新增证据类型时易漏改，是问题 3 得以存在的土壤。

## 问题关系图

```
问题 1（patch 恒空）────┐
                        ├──→ 评分依据 = agent 自述，而非产物
问题 2（归档未回喂）────┘        【方法论级：盲评客观性受损】

问题 4（过滤规则分散）──→ 问题 3（.aaw-eval 泄漏）
                              【效度级：baseline 被污染 + 证据自相矛盾】
```

## 证据附录

**A. 两组 run 产物对比**

| 项目 | no_skill（6b6c765d） | current（e458f337） |
|---|---|---|
| `report-exists`（硬门） | 100 ✅ | 100 ✅ |
| `report-sections`（硬门） | 0 ❌ exit_code=1 | 100 ✅ exit_code=0 |
| `report-quality`（rubric, w=100） | 30 | 85 |
| **quality_score** | **30** | **85** |
| `changes.patch` 大小 | 0 字节 | 0 字节 |
| `untracked.zip` 内容 | `REPORT.md` 2282B | `REPORT.md` 2066B |
| `file-tree.json` | 3 项（无 `.aaw-eval/`） | 3 项（无 `.aaw-eval/`） |

**B. 根因定位**

| 文件:行号 | 代码 |
|---|---|
| `repository.py:152` | `patch = _git(workspace, "diff", "--binary", "HEAD", timeout=120)` |
| `repository.py:171` | `if path.startswith((".aaw-eval/", ".agents/skills/aaw-eval-")):` |
| `repository.py:191` | `and not (current == workspace and directory == ".aaw-eval")` |
| `orchestrator.py:235` | `prepare_eval_workspace(workspace)`（无条件调用） |
| `orchestrator.py:257` | `changes = capture_changes(workspace)` |
| `orchestrator.py:263` | `"git_patch": changes["patch"][-120_000:]` |
| `orchestrator.py:290-292` | `archive_untracked(...)` → `untracked.zip` |
| `orchestrator.py:768` | judge payload `"evidence": evidence` |
| `skills.py:163-182` | `prepare_eval_workspace()` 创建 `.aaw-eval/skills` |
| `storage.py:47` | 归档过滤规则 |

## 复查补充（2026-09-11 晚，L2 数据二次核对）

问题 1–4 提出后对同一批 run 做了逐字段复查，又暴露 3 个独立缺陷。

### 问题 5｜judge 证据携带去匿名化字段，与 judge prompt 的匿名声明冲突（中等）

**现象**

judge prompt 明确声明所评对象匿名（不告知技能名、不告知分组），但送进 judge 的
证据结构中含有 `skill_invoked` 字段，其取值直接暴露被评 agent 是否调用过技能。

**实证**

| 证据 | 内容 |
|---|---|
| judge payload | `evidence` 内含 `skill_invoked`，与 `git_patch` / `untracked` 同级 |
| 7 条 run 的 `skill_invoked` 取值 | `no_skill` 组恒为 `"no"`；`baseline` / `current` 组恒为 `"unknown"` |

**影响**

盲评的有效性依赖于 judge 无法从证据中推断分组。该字段虽在本次取值下未直接
给出 `"yes"`，但 `"no"` 与 `"unknown"` 的系统性差异本身就是分组指纹：judge 只要
观察到该字段，即可将「`no`」与「非 `no`」分成两类，与实验分组一一对应。

**根因**

证据组装时未做字段级脱敏，直接将内部诊断字段并入 judge 可见的 evidence 结构；
判据配置（哪些字段可外露）未在任何单一定义处集中声明。

### 问题 6｜`_skill_invocation()` 在 Chrys 下恒不可能返回 `"yes"`，该列是死指标（中等）

**现象**

`skill_invoked` 列在 UI 上展示，但在 Chrys 上评的 7 条 run 中无一为 `"yes"`。

**实证**

| 证据 | 内容 |
|---|---|
| 7 条 run 取值 | `no_skill` → `"no"`；`baseline` / `current` → `"unknown"`，无一条为 `"yes"` |
| `_skill_invocation()` 判定依据 | 依赖 Codex 专属的技能调用痕迹；Chrys 会话结构中不存在对应字段 |

**影响**

该列在启用 Chrys 后失去区分能力，`"unknown"` 既可能表示「没调用」也可能表示
「无法判定」，UI 上无法区分。更严重的是：它同时是问题 5 的分组指纹来源。

**根因**

判定逻辑按 Codex 实现编写，未对 Chrys 会话结构做适配，也未在无法判定时把
「不适用」与「未知」分开表达；`"unknown"` 被当作兜底值而非显式的「本运行时不支持」。

### 问题 7｜`_token_usage()` 字段名不匹配，token 统计恒为空（轻微）

**现象**

全部 7 条 run 的 token 统计字段为 `NULL`，UI 上 token 列全空。

**实证**

| 证据 | 内容 |
|---|---|
| 会话写入侧字段名 | `last_usage.{input_token_count, output_token_count}` |
| `_token_usage()` 读取侧字段名 | `{input_tokens, output_tokens}` |
| 7 条 run 结果 | token 计数均为 `NULL` |

**影响**

成本归因与「省钱」类指标不可用；不污染评分正确性。

**根因**

读取侧按预期字段名硬编码，未与会话写入侧的实际 schema 对齐；两处各自独立
定义同一概念，缺一组契约测试锁住。

## 备注

- 本次 L2 测试**总体结论不受影响**：`report-sections` 硬门对两组给出 0 / 100 的明确区分，分差方向正确，平台端到端可用性已获证明。
- 上述缺陷影响的是**评分的证据充分性**与**实验环境的干净度**，在更严格的 L3/L4 对比中会放大。
- 问题 1、3 会直接污染 L3（真实技能区分度验证）的结论，建议在 L3 开跑前处理；
  问题 5 影响盲评有效性，与问题 6 同源，可一并整改。
- 整改计划另行提出，本文档只做根因记录。
