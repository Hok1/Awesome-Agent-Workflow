/**
 * src/ui/SettingsPage 测试（侧边 Tab 版）：Tab 分片渲染与切换、字段
 * 渲染与默认值、变更写 store、「测试连接」成功/失败反馈、语言单选项
 * 呈静态值、skills 安装器区块挂载。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import SettingsPage from "../../src/ui/SettingsPage";
import { demoHost } from "../../src/core/host";
import { useSettingsStore } from "../../src/stores/settingsStore";
import { useSkillsStore } from "../../src/stores/skillsStore";

/**
 * 渲染设置页并等待挂载期的异步扫描落定（skills 安装器 + Agent 本机扫描）：
 * 提前结束测试会让 store→组件的更新逃逸 act（RTL 警告 + stderr 噪声）。
 */
async function renderSettingsPage(): Promise<void> {
  render(<SettingsPage />);
  await waitFor(() => {
    expect(useSkillsStore.getState().isScanning).toBe(false);
    expect(useSettingsStore.getState().isScanningAgents).toBe(false);
  });
}

/** 切到指定 Tab（侧边导航）。 */
async function openTab(name: string): Promise<void> {
  await userEvent.click(screen.getByRole("tab", { name }));
}

const CHRYS_TEST_PATH = "X:/tools/chrys.exe";

describe("SettingsPage（侧边 Tab 版）", () => {
  beforeEach(() => {
    window.localStorage.clear();
    demoHost.reset();
    useSettingsStore.getState().resetToDefaults();
    useSettingsStore.setState({
      connection: { status: "idle", message: "尚未检测", checkedAt: null },
      isProbingChrysPath: false,
      discoveredAgents: [],
      isScanningAgents: false,
    });
  });

  it("Agent 分片：内置项在列且默认选中 iCode，报告卡呈空态", async () => {
    await renderSettingsPage();
    await openTab("Agent");
    expect(screen.getByText("会话 Agent")).toBeInTheDocument();
    const row = screen.getByLabelText("agent-iCode");
    expect(row).toBeInTheDocument();
    // 内置行带「当前使用」徽标
    expect(within(row).getByText("当前使用")).toBeInTheDocument();
    // demo 宿主未脚本化 where：扫描结论为「未发现」
    expect(screen.getByText(/未发现其他原生 ACP CLI/)).toBeInTheDocument();
    // 报告卡空态
    expect(screen.getByLabelText("协议自检报告")).toBeInTheDocument();
    expect(screen.getByText(/尚未自检/)).toBeInTheDocument();
  });

  it("本机扫描：where 命中 OpenCode 时列出发现行，点行即切换会话 Agent", async () => {
    demoHost.scriptCommand("where", ["opencode"], {
      code: 0,
      stdout: "C:/Users/demo/npm/opencode.exe\r\n",
      stderr: "",
    });
    await renderSettingsPage();
    await openTab("Agent");
    const row = await screen.findByLabelText("agent-OpenCode");
    expect(within(row).getByText("本机发现")).toBeInTheDocument();
    // 行内选择按钮含 agent 名与命令（radio 语义，aria-pressed 表选中）
    const select = within(row).getByRole("button", {
      name: /OpenCode/,
    });

    await userEvent.click(select);
    expect(useSettingsStore.getState().activeAgentId).toBe("native-opencode");
    expect(window.localStorage.getItem("aaw-desktop.settings.v1")).toContain(
      "native-opencode",
    );
    expect(within(row).getByText("当前使用")).toBeInTheDocument();
  });

  it("添加自定义 agent：入列、持久化、可删除（删除当前项回落内置）", async () => {
    await renderSettingsPage();
    await openTab("Agent");
    await userEvent.type(
      screen.getByLabelText("自定义 Agent 名称"),
      "内网 Agent",
    );
    await userEvent.type(
      screen.getByLabelText("自定义 Agent 启动命令"),
      '"C:/Program Files/intranet/agent.exe" acp',
    );
    await userEvent.click(screen.getByRole("button", { name: "添加" }));

    const row = await screen.findByLabelText("agent-内网 Agent");
    // 双引号路径成组：首段不带引号
    expect(
      within(row).getByText("C:/Program Files/intranet/agent.exe acp"),
    ).toBeInTheDocument();
    expect(useSettingsStore.getState().agents).toHaveLength(1);

    // 点行切到自定义项再删除：回落内置 iCode
    await userEvent.click(
      within(row).getByRole("button", { name: /内网 Agent/ }),
    );
    expect(useSettingsStore.getState().activeAgentId).toBe("custom-agent");
    await userEvent.click(within(row).getByRole("button", { name: "删除" }));
    expect(useSettingsStore.getState().agents).toHaveLength(0);
    expect(useSettingsStore.getState().activeAgentId).toBe("chrys");
  });

  it("空名称 / 空命令的添加被拒并给出错误文案", async () => {
    await renderSettingsPage();
    await openTab("Agent");
    // 名称留空：先报名称
    await userEvent.click(screen.getByRole("button", { name: "添加" }));
    expect(await screen.findByText("名称不能为空")).toBeInTheDocument();
    // 名称合法、命令留空：报命令
    await userEvent.type(
      screen.getByLabelText("自定义 Agent 名称"),
      "内网 Agent",
    );
    await userEvent.click(screen.getByRole("button", { name: "添加" }));
    expect(await screen.findByText("启动命令不能为空")).toBeInTheDocument();
    expect(useSettingsStore.getState().agents).toHaveLength(0);
  });

  it("四枚 Tab 切换分片；默认落在「通用」", async () => {
    await renderSettingsPage();
    // 默认 Tab：通用（语言 / 主题 / 关于在位，工具路径行不可见）
    expect(screen.getByRole("tab", { name: "通用" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("界面语言")).toBeInTheDocument();
    expect(screen.getByText("版本")).toBeInTheDocument();
    // 工具路径面板 hidden（仍在 DOM，但不可见）
    expect(screen.getByLabelText("iCode 可执行路径")).not.toBeVisible();

    await openTab("Agent");
    expect(screen.getByRole("tab", { name: "Agent" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("会话 Agent")).toBeInTheDocument();

    await openTab("工具路径");
    expect(screen.getByRole("tab", { name: "工具路径" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByLabelText("iCode 可执行路径")).toBeInTheDocument();

    await openTab("会话与审批");
    expect(screen.getByText("审批默认模式")).toBeInTheDocument();
    expect(screen.getByLabelText("iCode 可执行路径")).not.toBeVisible();
  });

  it("工具路径分片：渲染各字段与默认 chrys 路径（空 + 手动指定提示）", async () => {
    await renderSettingsPage();
    await openTab("工具路径");
    expect(screen.getByLabelText("iCode 可执行路径")).toHaveValue("");
    expect(screen.getByLabelText("uv 命令")).toBeInTheDocument();
    expect(screen.getByLabelText("aaw 脚本路径")).toBeInTheDocument();
    expect(screen.getByLabelText("AAW skills 安装源目录")).toBeInTheDocument();
    expect(
      screen.getByText("未找到 iCode，请手动指定路径"),
    ).toBeInTheDocument();
    // 内置 skills 安装器作为工具路径分片的区块存在
    expect(screen.getByText("AAW skills 安装器")).toBeInTheDocument();
  });

  it("修改 chrys 路径写入 store 并持久化", async () => {
    await renderSettingsPage();
    await openTab("工具路径");
    const input = screen.getByLabelText("iCode 可执行路径");
    await userEvent.clear(input);
    await userEvent.type(input, "X:/chrys.exe");
    expect(useSettingsStore.getState().chrysPath).toBe("X:/chrys.exe");
    expect(window.localStorage.getItem("aaw-desktop.settings.v1")).toContain(
      "X:/chrys.exe",
    );
  });

  it("「测试连接」成功时展示版本（行尾 chip + 状态行）", async () => {
    useSettingsStore.getState().setChrysPath(CHRYS_TEST_PATH);
    demoHost.scriptCommand(CHRYS_TEST_PATH, ["--version"], {
      code: 0,
      stdout: "0.25.1\n",
      stderr: "",
    });
    await renderSettingsPage();
    await openTab("工具路径");
    await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
    expect(
      await screen.findByText(/可用（版本 0\.25\.1）/),
    ).toBeInTheDocument();
  });

  it("「测试连接」失败时展示错误", async () => {
    useSettingsStore.getState().setChrysPath(CHRYS_TEST_PATH);
    demoHost.scriptCommand(CHRYS_TEST_PATH, ["--version"], {
      code: 9009,
      stdout: "",
      stderr: "系统找不到指定的文件",
    });
    await renderSettingsPage();
    await openTab("工具路径");
    await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
    expect(await screen.findByText(/系统找不到指定的文件/)).toBeInTheDocument();
  });

  it("路径为空时「测试连接」失败收口并提示配置路径", async () => {
    await renderSettingsPage();
    await openTab("工具路径");
    await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
    expect(
      await screen.findByText(/未配置 iCode 可执行路径/),
    ).toBeInTheDocument();
  });

  it("配置路径后「未找到 iCode」提示消失", async () => {
    await renderSettingsPage();
    await openTab("工具路径");
    expect(
      screen.getByText("未找到 iCode，请手动指定路径"),
    ).toBeInTheDocument();
    await userEvent.type(
      screen.getByLabelText("iCode 可执行路径"),
      CHRYS_TEST_PATH,
    );
    expect(
      screen.queryByText("未找到 iCode，请手动指定路径"),
    ).not.toBeInTheDocument();
  });

  it("语言仅一项可选时呈静态值，不渲染单选项选单（English 预留未下发）", async () => {
    await renderSettingsPage();
    expect(screen.getByText("界面语言")).toBeInTheDocument();
    expect(screen.getByText("中文")).toBeInTheDocument();
    expect(useSettingsStore.getState().language).toBe("zh-CN");
    // 伪控件检查：不出现只有一个方向可选的分组按钮
    expect(
      screen.queryByRole("group", { name: "界面语言" }),
    ).not.toBeInTheDocument();
  });

  it("会话与审批分片：分段控件切换审批默认模式写入 store", async () => {
    await renderSettingsPage();
    await openTab("会话与审批");
    const autoAllow = screen.getByRole("button", { name: "自动放行" });
    expect(autoAllow).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/手动确认 —/)).toBeInTheDocument();

    await userEvent.click(autoAllow);
    expect(useSettingsStore.getState().approvalMode).toBe("auto-allow");
    expect(autoAllow).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/自动放行 —/)).toBeInTheDocument();
  });

  it("任务步骤默认关闭，切换后持久化并可恢复默认", async () => {
    await renderSettingsPage();
    await openTab("会话与审批");
    const group = screen.getByRole("group", { name: "在消息流中显示任务步骤" });
    expect(useSettingsStore.getState().messageStreamShowTodos).toBe(false);
    await userEvent.click(within(group).getByRole("button", { name: "开启" }));
    expect(useSettingsStore.getState().messageStreamShowTodos).toBe(true);
    const persisted: unknown = JSON.parse(
      window.localStorage.getItem("aaw-desktop.settings.v1") ?? "{}",
    );
    expect(persisted).toMatchObject({ messageStreamShowTodos: true });
    useSettingsStore.getState().resetToDefaults();
    expect(useSettingsStore.getState().messageStreamShowTodos).toBe(false);
  });

  it("通用分片：切换主题写入 store 并持久化，分段按钮呈按下态", async () => {
    await renderSettingsPage();
    const warm = screen.getByRole("button", { name: "暖白" });
    const dark = screen.getByRole("button", { name: "暗夜" });
    // 默认暗夜：暗夜呈按下态
    expect(dark).toHaveAttribute("aria-pressed", "true");
    expect(warm).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(warm);
    expect(useSettingsStore.getState().theme).toBe("warm");
    expect(window.localStorage.getItem("aaw-desktop.settings.v1")).toContain(
      '"warm"',
    );
    expect(warm).toHaveAttribute("aria-pressed", "true");
    expect(dark).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(dark);
    expect(useSettingsStore.getState().theme).toBe("dark");
    expect(dark).toHaveAttribute("aria-pressed", "true");
  });

  it("页头呈「修改即时生效」说明与「恢复默认设置」入口", async () => {
    await renderSettingsPage();
    expect(screen.getByText("修改即时生效，自动保存")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "恢复默认设置" }),
    ).toBeInTheDocument();
  });
});
