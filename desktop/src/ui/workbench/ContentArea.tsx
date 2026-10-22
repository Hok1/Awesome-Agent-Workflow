/**
 * 内容区：随左栏树的选中项与功能页入口切换的单一视图容器。
 *
 * 结构：顶部固定 44px 上下文条（ContextBar：会话标题 / 项目名 / 返回 /
 * 关闭项目等，随视图切换形态）+ 视图主体。视图优先级：功能页覆盖层
 * （设置 / 诊断，全屏语义）> 树选中驱动的基底视图（项目总览 / 会话）。
 * 覆盖层激活时树由 App 的 WorkbenchShell 整体隐藏，返回按钮在上下文条；
 * 基底视图状态在 workbenchUiStore，本组件只按状态渲染。
 *
 * AAW 不占独立视图：入口向导是会话内 AAW 面板（SessionAawPanel）的一个
 * 分段，ar 启动时的项目上下文（未连接先连接再发送）组装在 wizardSubmit，
 * 此处只接线。
 */
import { createLogger } from "../../core/logger.ts";
import { useWorkbenchUiStore } from "../../stores/workbenchUiStore.ts";
import { submitWizardPrompt } from "./wizardSubmit.ts";
import { ContextBar } from "./ContextBar.tsx";
import SettingsPage from "../SettingsPage.tsx";
import DiagnosticsPage from "../DiagnosticsPage.tsx";
import { SessionView } from "../session/SessionView.tsx";
import ProjectOverview from "./ProjectOverview.tsx";

const logger = createLogger("app");

/** 内容区视图分支（无 tab UI，纯状态驱动）。 */
function ContentArea() {
  const treeView = useWorkbenchUiStore((state) => state.treeView);
  const overlay = useWorkbenchUiStore((state) => state.overlay);
  const contextPath = useWorkbenchUiStore((state) => state.contextPath);
  const view = overlay ?? treeView;

  let body: React.ReactNode;
  switch (view) {
    case "settings":
      body = <SettingsPage />;
      break;
    case "diagnostics":
      body = <DiagnosticsPage />;
      break;
    case "session":
      body = (
        <SessionView
          onSubmitAawPrompt={(prompt) => {
            logger.info("AAW 入口向导已生成首条 prompt，交给会话发送", {
              length: prompt.length,
            });
            return submitWizardPrompt(prompt);
          }}
        />
      );
      break;
    case "project-overview":
      body = (
        <div className="h-full overflow-y-auto p-3">
          <ProjectOverview path={contextPath} />
        </div>
      );
      break;
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-base">
      <ContextBar />
      <div className="min-h-0 flex-1 overflow-hidden">{body}</div>
    </div>
  );
}

export default ContentArea;
