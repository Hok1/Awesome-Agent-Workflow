/**
 * src/ui/SettingsPage 测试：字段渲染与默认值、变更写 store、
 * 「测试连接」成功/失败反馈、语言切换词条、skills 安装器区块挂载。
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import SettingsPage from "../../src/ui/SettingsPage";
import { demoHost } from "../../src/core/host";
import { useSettingsStore } from "../../src/stores/settingsStore";
import { useSkillsStore } from "../../src/stores/skillsStore";
import { selectFromListbox } from "../helpers/listbox";

/**
 * 渲染设置页并等待 SkillsInstallerSection 的挂载扫描落定：
 * 挂载即异步扫描（demoHost 默认无 skills 目录，按失败收尾），
 * 提前结束测试会让 store→组件的更新逃逸 act（RTL 警告 + stderr 噪声）。
 */
async function renderSettingsPage(): Promise<void> {
  render(<SettingsPage />);
  await waitFor(() => {
    expect(useSkillsStore.getState().isScanning).toBe(false);
  });
}

const CHRYS_TEST_PATH = "X:/tools/chrys.exe";

describe("SettingsPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
    demoHost.reset();
    useSettingsStore.getState().resetToDefaults();
    useSettingsStore.setState({
      connection: { status: "idle", message: "尚未检测", checkedAt: null },
      isProbingChrysPath: false,
    });
  });

  it("渲染各设置区块与默认 chrys 路径", async () => {
    await renderSettingsPage();
    expect(screen.getByText("iCode 可执行路径")).toBeInTheDocument();
    expect(screen.getByText("审批默认模式")).toBeInTheDocument();
    expect(screen.getByText("界面语言")).toBeInTheDocument();
    expect(screen.getByText("AAW skills 安装源目录")).toBeInTheDocument();
    // 默认路径为空（不硬编码开发者本机路径），并提示手动指定
    expect(screen.getByLabelText("iCode 可执行路径")).toHaveValue("");
    expect(
      screen.getByText("未找到 iCode，请手动指定路径"),
    ).toBeInTheDocument();
    // 内置 skills 安装器作为设置页区块存在
    expect(screen.getByText("AAW skills 安装器")).toBeInTheDocument();
  });

  it("修改 chrys 路径写入 store 并持久化", async () => {
    await renderSettingsPage();
    const input = screen.getByLabelText("iCode 可执行路径");
    await userEvent.clear(input);
    await userEvent.type(input, "X:/chrys.exe");
    expect(useSettingsStore.getState().chrysPath).toBe("X:/chrys.exe");
    expect(window.localStorage.getItem("aaw-desktop.settings.v1")).toContain(
      "X:/chrys.exe",
    );
  });

  it("「测试连接」成功时展示版本", async () => {
    useSettingsStore.getState().setChrysPath(CHRYS_TEST_PATH);
    demoHost.scriptCommand(CHRYS_TEST_PATH, ["--version"], {
      code: 0,
      stdout: "0.25.1\n",
      stderr: "",
    });
    await renderSettingsPage();
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
    await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
    expect(await screen.findByText(/系统找不到指定的文件/)).toBeInTheDocument();
  });

  it("路径为空时「测试连接」失败收口并提示配置路径", async () => {
    await renderSettingsPage();
    await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
    expect(
      await screen.findByText(/未配置 iCode 可执行路径/),
    ).toBeInTheDocument();
  });

  it("配置路径后「未找到 chrys」提示消失", async () => {
    await renderSettingsPage();
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

  it("语言选单只暴露中文，English 预留不再下发", async () => {
    await renderSettingsPage();
    // 自绘下拉：选项在 role=listbox 的 DOM 面板里（原生 select 的 option
    // 由系统绘制，主题管不到——这是我们换掉它的原因）
    await userEvent.click(screen.getByRole("combobox", { name: "界面语言" }));
    const panel = screen.getByRole("listbox", { name: "界面语言" });
    const options = within(panel).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["中文"]);
    expect(useSettingsStore.getState().language).toBe("zh-CN");
  });

  it("切换审批默认模式写入 store", async () => {
    await renderSettingsPage();
    await selectFromListbox(
      userEvent.setup(),
      "审批默认模式",
      "自动放行（默认允许工具调用）",
    );
    expect(useSettingsStore.getState().approvalMode).toBe("auto-allow");
  });

  it("外观区块：切换主题写入 store 并持久化，分段按钮呈按下态", async () => {
    await renderSettingsPage();
    const group = screen.getByRole("group", { name: "外观主题" });
    const warm = within(group).getByRole("button", { name: "暖白" });
    const dark = within(group).getByRole("button", { name: "暗夜" });
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
});
