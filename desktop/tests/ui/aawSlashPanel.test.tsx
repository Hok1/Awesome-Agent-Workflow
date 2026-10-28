import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PanelWorkspace } from "../../src/ui/right-panel/RightPanel.tsx";
import { ChatInput } from "../../src/ui/session/ChatInput.tsx";
import { useWorkbenchUiStore } from "../../src/stores/workbenchUiStore.ts";
import { useRightPanelStore } from "../../src/stores/rightPanelStore.ts";
import { useSessionStore } from "../../src/stores/sessionStore.ts";
import { useWorkspaceStore } from "../../src/stores/workspaceStore.ts";
import { sendAawToTarget } from "../../src/ui/right-panel/aawTarget.ts";

vi.mock("../../src/ui/right-panel/aawTarget.ts", () => ({
  sendAawToTarget: vi.fn(() => Promise.resolve({ ok: true })),
}));
const mockSend = vi.mocked(sendAawToTarget);
beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
  useRightPanelStore.setState({ projects: {} });
  useWorkbenchUiStore.setState({
    contextPath: null,
    treeView: "project-overview",
    overlay: null,
    aawWizardRequest: null,
  });
  useSessionStore.getState().clear();
  useSessionStore.setState({
    activeSessionId: "slash-session",
    isBound: true,
    isConnecting: false,
  });
});
function mount(project: string) {
  useWorkspaceStore.setState({ activePath: project });
  useWorkbenchUiStore.getState().openSessionView(project);
  return render(
    <PanelWorkspace project={project} enabled>
      <ChatInput
        isAgentRunning={false}
        onSend={vi.fn()}
        onEnqueue={vi.fn()}
        onCancel={vi.fn()}
      />
    </PanelWorkspace>,
  );
}
describe("斜杠命令打开项目 AAW 向导", () => {
  it.each([
    ["sr", "需求原文（保持原文，不总结不改写）"],
    ["ar", "AR 描述"],
    ["dev", "一句话需求"],
  ])("/%s 直接打开右栏启动页和对应变量表单", async (command, field) => {
    const project = `D:/slash-${command}`;
    mount(project);
    const input = screen.getByLabelText("消息输入框");
    await userEvent.type(input, `/${command}{Enter}`);
    const panel = await screen.findByLabelText("AAW 面板");
    expect(
      within(panel).getByRole("tab", { name: "启动", selected: true }),
    ).toBeInTheDocument();
    expect(within(panel).getByLabelText(field)).toBeInTheDocument();
    expect(
      useRightPanelStore.getState().projects[project.toLowerCase()],
    ).toMatchObject({ open: true, active: "aaw", aawSegment: "launch" });
    expect(screen.getByLabelText("消息输入框")).toBe(input);
    expect(input).toHaveValue("");
  });
  it("相同命令再次打开向导，切换入口后继续隔离项目草稿", async () => {
    const view = mount("D:/slash-project-a");
    const input = screen.getByLabelText("消息输入框");
    await userEvent.type(input, "/sr{Enter}");
    await userEvent.type(screen.getByLabelText("SR 编号"), "SR-101");
    await userEvent.click(
      screen.getByRole("button", { name: "收起右侧工具栏" }),
    );
    // 关闭后常见的同项目视图/侧栏状态更新不应重放旧的斜杠请求。
    act(() => {
      useWorkbenchUiStore.getState().openSessionView("D:/slash-project-a");
      useWorkbenchUiStore.setState({ sidebarCollapsed: true });
    });
    expect(
      useRightPanelStore.getState().projects["d:/slash-project-a"]?.open,
    ).toBe(false);
    await userEvent.type(input, "/sr{Enter}");
    expect(screen.getByLabelText("SR 编号")).toHaveValue("SR-101");
    await userEvent.type(input, "/ar{Enter}");
    expect(screen.getByLabelText("AR 描述")).toBeInTheDocument();
    expect(screen.getByLabelText("SR 编号")).toHaveValue("SR-101");
    act(() =>
      useWorkbenchUiStore.getState().openSessionView("D:/slash-project-b"),
    );
    view.rerender(
      <PanelWorkspace project="D:/slash-project-b" enabled>
        <ChatInput
          isAgentRunning={false}
          onSend={vi.fn()}
          onEnqueue={vi.fn()}
          onCancel={vi.fn()}
        />
      </PanelWorkspace>,
    );
    expect(
      screen.queryByRole("tab", { name: "启动", selected: true }),
    ).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("消息输入框"), "/dev{Enter}");
    expect(screen.getByLabelText("一句话需求")).toBeInTheDocument();
    expect(screen.getByLabelText("SR 编号")).toHaveValue("");
    expect(
      useRightPanelStore.getState().projects["d:/slash-project-a"]?.active,
    ).toBe("aaw");
    expect(
      useRightPanelStore.getState().projects["d:/slash-project-b"]?.active,
    ).toBe("aaw");
  });
  it("上下文已切换而右栏尚未重渲染时，请求只应用到目标项目", async () => {
    const view = mount("D:/slash-stale-a");
    act(() => {
      useWorkbenchUiStore.getState().openSessionView("D:/slash-stale-b");
      useWorkbenchUiStore.getState().openAawWizard("ar");
    });
    expect(
      useRightPanelStore.getState().projects["d:/slash-stale-a"]?.open,
    ).not.toBe(true);
    view.rerender(
      <PanelWorkspace project="D:/slash-stale-b" enabled>
        <ChatInput
          isAgentRunning={false}
          onSend={vi.fn()}
          onEnqueue={vi.fn()}
          onCancel={vi.fn()}
        />
      </PanelWorkspace>,
    );
    expect(await screen.findByLabelText("AR 描述")).toBeInTheDocument();
    expect(
      useRightPanelStore.getState().projects["d:/slash-stale-b"],
    ).toMatchObject({ open: true, active: "aaw", aawSegment: "launch" });
    expect(
      useRightPanelStore.getState().projects["d:/slash-stale-a"]?.open,
    ).not.toBe(true);
  });
  it("向导发送后可查看会话并收起右栏", async () => {
    mount("D:/slash-submit");
    const chat = screen.getByLabelText("消息输入框");
    await userEvent.type(chat, "/dev{Enter}");
    await userEvent.type(screen.getByLabelText("SR 编号"), "SR-009");
    await userEvent.type(screen.getByLabelText("一句话需求"), "增加设置开关");
    await userEvent.click(
      screen.getByRole("button", { name: "下一步：确认发送" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "交给会话发送" }));
    expect(mockSend).toHaveBeenCalledTimes(1);
    await userEvent.click(await screen.findByRole("button", { name: "查看" }));
    expect(useWorkbenchUiStore.getState().treeView).toBe("session");
    expect(
      useRightPanelStore.getState().projects["d:/slash-submit"]?.open,
    ).toBe(false);
    expect(screen.getByLabelText("消息输入框")).toBe(chat);
  });
});
