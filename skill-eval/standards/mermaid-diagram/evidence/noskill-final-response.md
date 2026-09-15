交付完成。

**文档路径**：`docs/SM2-密钥生命周期-图.md`（3 个 mermaid 代码块）

**每张图回答的评审问题**

| 图 | 图型 | 回答的评审问题 |
| --- | --- | --- |
| 图 1 | `stateDiagram-v2` | Q1：用户 SM2 密钥从产生到销毁经历哪些状态（未生成 → 已生成 → 已启用 → 已失效/已吊销 → 已销毁），以及每个转换的触发条件。以单个密钥对为单位；`已吊销` 无回到 `已启用` 的转换，体现「泄露密钥不得回到可用状态、吊销不可逆」 |
| 图 2 | `sequenceDiagram` | Q2：轮换时用户（rbs-cli）、RBS 管理员（管理接口）、RBS 服务（验签与用户库）的交互顺序；关键约束是「新公钥启用先于旧公钥失效」，旧私钥签发的 token 在验签阶段被拒 |
| 图 3 | `sequenceDiagram` | Q3：泄露/疑似泄露时的三方联动处置顺序；关键约束是「吊销先于擦除」，且吊销自生效时刻起对存量（吊销前签发未过期）token 一律拒绝 |

图下另附「业务事实落点对照」表，密钥生命周期业务事实 1–8 条逐条对应到图。

**离线校验退出码**

- `python <skill-dir>/scripts/check_mermaid.py docs/SM2-密钥生命周期-图.md` → 3 个图块全部 `[OK]`，**退出码 0**
- 仓库内 `.sdd/SR-1/assert_mermaid.py` 黑盒断言 → `MERMAID-ASSERT-PASS`，**退出码 0**（图型 = stateDiagram-v2 + 2×sequenceDiagram，状态图 8 条转换 / 6 个状态声明）

全程离线：只用 skill 自带的固定版本 Mermaid（`vendor/mermaid/mermaid.min.js`）+ 本机 Node v24.13.0，未调用 npx、包管理器或远程渲染。

一点需要说明的环境情况：本次会话的技能目录未挂载（`load_skill` 报 `Skill 'mermaid-diagram' not found`），因此我直接读取仓库中的 `skills/mermaid-diagram/SKILL.md` 按其正文执行，并用其自带脚本 `scripts/check_mermaid.py` 完成校验（校验逻辑与 skill 规定的完全一致）。