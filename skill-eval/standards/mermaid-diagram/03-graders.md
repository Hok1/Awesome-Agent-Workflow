# mermaid-diagram 评测标准（判据正文）

来源套件：`mermaid-diagram-SR1-key-lifecycle-eval`
套件 id：15a54472-8c59-457f-a757-4e8ae970da1e
skill：mermaid-diagram  project：C:\code\workspace\globaltrustauthority-rbs

| id | 类型 | 权重 | 硬门槛 | rubric 字数 |
|---|---|---|---|---|
| `mermaid-assert` | command | 100.0 | False | 0 |

---

## mermaid-assert

- 名称：图表产物黑盒断言（存在性/可编译/图型匹配/路径覆盖/无自造标识符）
- 类型：`command`
- 权重：100.0
- 硬门槛：False
- 命令：`python .sdd/SR-1/assert_mermaid.py`（cwd = run 工作区；退出码 0 得满分 100，非 0 得 0 分）
- 脚本本体：`fixture/assert_mermaid.py`（sha1 `9d4ff3521ca9ebe7b1bfdfa37f460ee8a5d87bbd`）

### rubric

```text

```

> 注：本 grader 类型为 `command`，无 `rubric` 字段——导出脚本只渲染 `rubric`，故上方为空块。
> 该 grader 的全部判据在 `fixture/assert_mermaid.py` 中，其断言条款与出处如下（黑盒：脚本只读
> 产物 `docs/SM2-密钥生命周期-图.md` 并调用 skill 自带校验器，不 import 任何被测源码）：

| # | 断言 | 出处 |
|---|---|---|
| 1 | 产物存在，含 ≥1 个 mermaid 代码块，且 `check_mermaid.py` 退出码为 0（完全离线） | `SKILL.md`「## 编译验证」：交付前运行该脚本，任一图无法编译时返回非零退出码 |
| 2 | 存在 `stateDiagram-v2`，且 ≥4 条 `-->` 转换、≥5 个状态声明 | `SKILL.md`「## 选择图型」：对象生命周期、合法状态和转换条件用 stateDiagram-v2 |
| 3 | 图中出现 生成/轮换/吊销/销毁，且出现「泄露」 | `SKILL.md` 编写规则 3（关键失败、回退或终止路径不能悬空）+ `crypto-gate-checklist.md` §3（状态集合） |
| 4 | 不得出现 `Foo()` 形态的函数调用标识符 | `SKILL.md` 编写规则 2：节点使用稳定的业务、模块或职责名称，避免发明私有类、函数和文件 |
| 5 | 存在 1–2 张 `sequenceDiagram` | `SKILL.md`「## 选择图型」：多参与者时序调用用 sequenceDiagram；「同一张图只回答一个主要问题」 |
| 6 | 不得出现 flowchart/sequence/state/class/er 之外的图型 | `SKILL.md`「## 选择图型」：只有不同图型回答不同评审问题时才同时保留 |

全部通过则输出 `MERMAID-ASSERT-PASS` 并 `exit 0`。

### 断言红绿验证（使用前完成）

断言脚本在用于实测之前，已用 13 个合成用例验证它能红也能绿，**0 个不符预期**：

| 用例 | 期望 | 实测 |
|---|---|---|
| 合规文档（stateDiagram-v2 6 状态 8 转换 + 1 张时序图） | 绿 | `MERMAID-ASSERT-PASS` |
| 产物文件缺失 | 红 | 产物文件不存在 |
| 无任何 mermaid 代码块 | 红 | 没有任何 ```mermaid 代码块 |
| 图有语法错误 | 红 | 离线校验器未通过 |
| 只有 flowchart 无状态图 | 红 | 缺少 stateDiagram-v2 |
| 状态图仅 3 条转换 | 红 | 少于生命周期所需的 4 条 |
| 状态图仅 3 个状态 | 红 | 只声明了 3 个状态 |
| 缺「吊销」节点 | 红 | 缺少关键节点 |
| 缺「泄露」路径 | 红 | 缺少「泄露」这条安全路径 |
| 出现 `exportPrivateKey()` | 红 | 私有标识符 |
| 缺时序图 | 红 | 缺少 sequenceDiagram |
| 3 张雷同时序图 | 红 | 重复表达同一关系 |
| 混入 pie 图 | 红 | 无关或自造的图型 |

红绿夹具与驱动：`fixture/redgreen/`（harness.py + 13 个用例目录）。

### 实测中暴露的结构性事实（2026-09-14）

断言 1 把「产物能编译」与「skill 包在场」耦合：`no_skill` 组不安装 skill 包，
`check_mermaid.py` 不存在于 workspace，断言 1 必然失败——这是 fail-closed 的正确行为
（SKILL.md 把离线编译验证定为交付硬步骤，无校验器即无法按契约交付），但意味着
**no_skill 组的图质量本身未被本判据独立测量**。事后用本地校验器复核其实际产物：
3 张图全部编译通过、图型选择与路径覆盖亦满足断言 2–6——模型不靠 skill 也能画对图，
skill 的增量价值体现在「可验证的交付纪律」上。而 no_skill 组产物文末谎称
「3 个图块全部 [OK]，退出码 0」（该组 workspace 中校验器根本不存在）——
恰好被断言 1 抓住。详见 `00-source-standard.md` §5 与 `evidence/`。
