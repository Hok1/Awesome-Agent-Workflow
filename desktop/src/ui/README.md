# src/ui — 界面层

React 组件与页面。只消费 `src/stores` 的状态和 action、`src/core` 的
类型与只读设施，不直接触碰协议与领域逻辑。

## 职责

- 主界面（App.tsx 组装）：上下文条（全应用唯一顶栏：视图上下文 +
  agent 标识 + 待办下拉；原 46px 顶栏的重复 crumb 已并入）+ 左缘图标
  窄栏（侧边栏开关 / 新建会话 / 设置 / 诊断，常驻 48px）+ 项目树
  （收藏 / 最近打开 → 项目 → 会话子节点，可整列收起）+ 内容区（随树
  选中项与窄栏入口切换）；权限与提问对话框（对应 ACP 的
  `request_permission` 与 `chrys/request_input`）挂在模态层；
- 项目总览（`workbench/ProjectOverview`）：项目状态行（健康摘要 chip +
  主行动按钮——未连接「新建会话」，已连接「进入会话」+「新建会话」）
  - 可折叠的健康检查明细 + 工作流状态（`AawStatusPanel`）；
- 设置页（`SettingsPage`）：工具路径（chrys / uv / aaw 脚本，全站唯一
  配置点）与「测试连接」、审批默认模式、界面语言（`core/i18n` 词条，
  英文预留）、skills 安装源，内嵌 `SkillsInstallerSection` 安装器
  （清单 / 已安装检测 / 覆盖确认 / 进度）；
- 诊断页（`DiagnosticsPage` = `LogView` + `AcpTrafficView`）：读取
  `stores/logStore`（镜像自 core 环形缓冲）展示日志与 ACP wire 流量；
- Markdown 渲染：`react-markdown` + `rehype-highlight`
  （highlight.js `github-dark` 主题，样式入口在 `src/index.css`）。

## 已实现

- `workbench/`：主界面骨架。
  - `IconRail.tsx`：图标窄栏（常驻 48px：侧边栏开关、新建会话、设置 /
    诊断入口；侧边栏收起即隐藏树列，无第二条窄条）；
  - `ProjectTree.tsx`：左栏项目树（项目 / 会话双视角、段头【+】面板、
    收藏 / 最近打开分组、健康徽标、会话子节点与「+ 新会话」，未连接项目
    点会话先自动连接再切换；连接点仅在已连接 / 连接中 / 失败时出现，
    会话视角空态给「去项目列表」出口）。**任何项目都可展开**：子区域里
    常驻「＋ 新会话」，空项目在树上不是死路。选中是「内容区正在显示谁」，
    全树只有一个：会话视图高亮会话行（项目行只是展开的父节点），总览
    高亮项目行；行选中态统一取 `controls.tsx` 的 `rowSelectedClass`
    （accent 淡底 + 左缘 2px 竖条），与中性色悬停态分属两套颜色语言；
  - `sessionStart.ts`：`startNewSession` ——在指定项目里**新建**一条会话
    （`forceNew` 跳过历史恢复，落一条空对话；选中项目 → 未连接先连接 →
    内容区切到会话视图）。与 `sessionEntry.ts` 的「打开历史会话」是两个
    动词，结果不同，不得合并；连接失败落在总览（那里有失败横幅与去设置
    工具路径的出口）；
  - `sessionHistory.ts`：装配层的历史会话补充——应用启动与添加项目后读
    agent 会话索引（`src/agents/chrysSessions.ts`），按归一化路径补进
    `sessionStore.sessionsByPath`。**只补空缺项目**，不覆盖
    session/list 的权威快照；
  - `ContextBar.tsx`：全应用唯一顶栏（44px，内容区顶部）：左侧是随视图
    切换的上下文（会话标题 / 项目名 / 连接徽标 / AAW 面板开关——有工作流
    数据时标签即「SR-xxx · 步骤 n」/ 关闭项目 / 返回按钮），右侧是共用的全局区
    （agent 标识 + 待办下拉）；空态下只渲染全局区；
  - `ContentArea.tsx`：内容区视图容器（项目总览 / 会话 / 设置 / 诊断，
    状态在 `stores/workbenchUiStore`）；
  - `SessionAawPanel.tsx`：会话内 AAW 增强面板（右栏抽屉，默认收起）：
    「进度」分段渲染 AawStatusPanel（注入 onRunCommand，放行给一个按
    人话说的动作），「启动」分段渲染 EntryWizard；由上下文条的 AAW 面板
    开关拉起；
  - `ProjectOverview.tsx`：项目总览（所示项目变化时自动触发一次异步
    健康检查；组件层从设置 store 组装工具路径成 pathsOverride，不阻塞
    UI；健康摘要 chip 可开合明细，有警告 / 失败时自动展开；主行动按钮
    不点名具体 agent——未连接时就是「新建会话」，已连接时「进入会话」+「新建会话」；项目没有 .sdd/ 时工作流面板收成一行说明）；
  - `wizardSubmit.ts`：AAW 入口向导首条 prompt 的发送（挂在会话的
    项目上下文上，未连接先连接再发送）；
  - `ColumnResizer.tsx` / `columnWidths.ts`：左栏拖宽与持久化；
  - `ModalShell.tsx`：模态外壳（问答表单等复用）。
- `EntryWizard.tsx`：AAW 入口启动向导（三入口选择 → 按入口收集变量 →
  首条中文 prompt 预览 → 交给会话发送；领域逻辑在 `src/aaw/entryWizard.ts`）。
  出现在会话内 AAW 面板的「启动」分段，是「从 AAW 入口启动」的显式动作，
  不是新建会话的必经步骤。
- `AawStatusPanel.tsx`：工作流状态面板，`aaw status / next --peek --json`
  的只读渲染（当前 SR、阶段步骤条、门禁徽标、工作单摘要、待放行提示）。
  它回答人的三个问题（在哪一步 / 要产出什么 / 卡在哪），因此 **agent 侧的
  执行细节默认不露**：done 命令行收在可展开的「执行详情」里——那是 skill
  派给 agent 的动作，不是用户的活。自身不写状态，唯一交互是刷新、自动
  刷新开关与（注入 `onRunCommand` 时）「放行进入下一步」这一个动作，发给
  会话的是自然语言请求而非 argv。项目总览与会话内 AAW 面板共用的展示件。
- `ApprovalModal.tsx`：权限审批模态弹窗（工具名 / 标题 / rawInput 摘要 /
  按 kind 排序的选项按钮，Esc 取消）。
- `QuestionForm.tsx`：结构化问答卡片表单（单选 / 多选，全答完才能提交）。
- `PendingInbox.tsx`：待办面板（顶栏「待办」按钮的下拉形态，挂起的
  审批/提问列表与焦点切换）。
- `session/`：会话视图（中央聊天流）。
  - `SessionView.tsx`：组合容器（上下文条 + 消息流 + 悬浮输入区），接近
    底部时自动跟随滚动；
  - `ChatInput.tsx`：悬浮输入卡（圆角植面 + 投影）：多行输入 Enter 发送 /
    Shift+Enter 换行，IME 组词不误发；下行模型短格式 + 审批模式徽标，
    右侧圆形发送 / 停止钮（session/cancel）；
  - `AssistantMessage.tsx` / `UserMessage.tsx` / `SystemNotice.tsx` /
    `ThoughtBlock.tsx`：四类条目的视觉区分（Markdown + 复制 / 右侧气泡 /
    居中弱化提示 / 折叠思考）；
  - `ToolCallCard.tsx`：工具调用卡片（折叠一行摘要，展开完整 JSON
    输入输出，运行中 / 完成 / 失败状态）；
- `MarkdownView.tsx` / `CopyButton.tsx`：Markdown + 代码块高亮与复制
  的共用渲染件。
- `workspaces/`：项目总览的组成件与项目侧组装工具。
  - `WorkspaceHealthPanel.tsx`：健康检查明细（chrys / uv / aaw CLI /
    `.sdd/` 四项的 通过/警告/失败 + 中文修复指引）；摘要 chip 与「重新
    检查」在项目状态行，路径修改入口在设置页；
  - `pickDirectory.ts`：系统目录选择对话框的薄封装（「添加项目…」入口）；
  - `settingsLinks.ts`：工具路径的组装桥（`settingsPathsOverride` 供执行
    入参 + `useToolPathSettings` 供设置页三路径读写）；
  - 「打开项目」把路径写入 workspace store 的 `activePath`（ACP
    session 的 cwd 绑定点）。

## 规则

- 样式用 Tailwind 工具类直写 JSX（规范见 `docs/conventions.md`）；
- 组件文件 PascalCase（`DiagnosticsPanel.tsx`），一个文件一个导出组件；
- 组件不做数据变换：领域数据进来前已在 store/领域层定型；
- 文案一律中文。
