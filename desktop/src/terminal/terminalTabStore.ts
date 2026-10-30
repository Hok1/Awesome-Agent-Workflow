/**
 * 终端页签 store（zustand）：页签数组 + 激活 id + 每页签的 spawn 错误。
 * v1 是**单一全局页签组**（跨项目共享，对齐 ZCode 的应用级终端面板）；
 * 数据底座（纯函数）见 terminalTabState.ts，本模块只做薄封装。
 *
 * attachHandle 是 handle 的唯一写入口：TerminalSessionView spawn 成功后
 * 写入，页签壳层关闭页签时从被关页签读 handle 调 ptyHost.closeConnection。
 * closeShellTab 返回被关页签（而非在 store 内触 Tauri）——保持 store 纯 UI，
 * 收尾动作留在调用侧。
 */
import { create } from "zustand";

import {
  attachShellName as attachShellNamePure,
  closeShellTab as closeShellTabPure,
  createTerminalTabs,
  markExited as markExitedPure,
  openShellTab as openShellTabPure,
  type TerminalTab,
} from "./terminalTabState.ts";

interface TerminalTabState {
  /** 页签组（初始为空；打开面板 / Plus 创建 shell 页签）。 */
  readonly tabs: TerminalTab[];
  /** 激活页签 id；空组（未开过 shell）为 null。 */
  readonly activeTabId: string | null;
  /** tabId → spawn / 连接错误（存 store 而非组件态：错误边界重挂后不丢）。 */
  readonly connectionErrors: Readonly<Record<string, string>>;

  /** 打开新 shell 页签（展示名由项目定格）并激活它。 */
  readonly openShellTab: (project: string | null) => void;
  /**
   * 关闭 shell 页签；返回被关页签（调用方据 handle 收尾 PTY），无则 null。
   * 被关页签正激活时激活相邻页签（先左后右）。
   */
  readonly closeShellTab: (tabId: string) => TerminalTab | null;
  /** 激活页签。 */
  readonly setActiveTab: (tabId: string) => void;
  /** spawn 成功写入 handle（null 用于防御路径清空悬空句柄）。 */
  readonly attachHandle: (tabId: string, handle: number | null) => void;
  /** spawn 成功写回 shell 显示名（工具栏展示；页签标题不变）。 */
  readonly attachShellName: (tabId: string, shellName: string) => void;
  /** 进程退出：置 exited 态 + 退出码（handle 保留至页签关闭收尾）。 */
  readonly markExited: (tabId: string, exitCode: number | null) => void;
  /** 记录 / 清除（message 为 null）页签的连接错误。 */
  readonly setConnectionError: (tabId: string, message: string | null) => void;
}

const initial = createTerminalTabs();

export const useTerminalTabStore = create<TerminalTabState>((set, get) => ({
  tabs: initial.tabs,
  activeTabId: initial.activeTabId,
  connectionErrors: {},

  openShellTab: (project) => {
    const result = openShellTabPure(get().tabs, project);
    set({ tabs: result.tabs, activeTabId: result.tab.id });
  },

  closeShellTab: (tabId) => {
    const result = closeShellTabPure(get().tabs, get().activeTabId, tabId);
    if (result.closed === null) {
      return null;
    }
    set((state) => {
      const connectionErrors = { ...state.connectionErrors };
      delete connectionErrors[tabId];
      return {
        tabs: result.tabs,
        activeTabId: result.activeTabId,
        connectionErrors,
      };
    });
    return result.closed;
  },

  setActiveTab: (tabId) => {
    if (get().activeTabId !== tabId) {
      set({ activeTabId: tabId });
    }
  },

  attachHandle: (tabId, handle) => {
    set((state) => ({
      tabs: state.tabs.map((tab) =>
        tab.id === tabId && tab.handle !== handle ? { ...tab, handle } : tab,
      ),
    }));
  },

  attachShellName: (tabId, shellName) => {
    set((state) => ({
      tabs: attachShellNamePure(state.tabs, tabId, shellName),
    }));
  },

  markExited: (tabId, exitCode) => {
    set((state) => ({ tabs: markExitedPure(state.tabs, tabId, exitCode) }));
  },

  setConnectionError: (tabId, message) => {
    set((state) => {
      if (state.connectionErrors[tabId] === message) {
        return state;
      }
      const connectionErrors = { ...state.connectionErrors };
      if (message === null) {
        delete connectionErrors[tabId];
      } else {
        connectionErrors[tabId] = message;
      }
      return { connectionErrors };
    });
  },
}));
