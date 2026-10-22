/**
 * 设置 store（src/stores）：chrys 路径、审批默认模式、界面语言、
 * skills 安装源目录、界面主题（暗夜/暖白），以及「测试连接」状态。
 *
 * 持久化：每项设置变更即写入 localStorage（Tauri WebView 的本地存储，
 * 随应用数据目录落盘），启动时读回并经类型守卫校验——损坏/越界的旧值
 * 一律回落默认，绝不带病进入状态。
 */
import { create } from "zustand";
import {
  hostRuntime,
  joinPath,
  type CommandResult,
  type HostRuntime,
} from "../core/host";
import { createLogger } from "../core/logger";
import type { Language } from "../core/i18n";

/**
 * 界面主题：暗夜（默认，深色）或暖白（米白浅色）。
 * 取值经根元素 `theme-warm` 类驱动 src/index.css 的语义 token 切换。
 */
export type ThemePreference = "dark" | "warm";

/** 主题选单（顺序即展示顺序）。 */
export const themeOptions: readonly {
  readonly value: ThemePreference;
  readonly label: string;
}[] = [
  { value: "dark", label: "暗夜" },
  { value: "warm", label: "暖白" },
];

const logger = createLogger("settings");

/**
 * 审批默认模式：chrys 发起 `session/request_permission` 反向请求时，
 * 客户端的默认应答策略（协议形状见 src/acp/types.ts 的
 * RequestPermissionRequestParams；选项 kind 见 chrys server.py
 * _request_permission，当前只提供 allow_once / reject_once）。
 */
export type ApprovalMode = "ask" | "auto-allow" | "auto-reject";

/** 审批模式选单（顺序即展示顺序）。 */
export const approvalModeOptions: readonly {
  readonly value: ApprovalMode;
  readonly label: string;
}[] = [
  { value: "ask", label: "每次询问（弹出审批对话框）" },
  { value: "auto-allow", label: "自动放行（默认允许工具调用）" },
  { value: "auto-reject", label: "自动拒绝（默认拒绝工具调用）" },
];

/**
 * chrys 可执行路径默认值：留空（不硬编码开发者本机路径）。启动时若为空
 * 会异步探测（PATH 查找与常见安装位置，见 probeChrysPath）；探测不到
 * 保持为空，设置页提示手动指定。已有用户持久化值不受影响。
 */
export const defaultChrysPath = "";

/** 探测不到 PATH 时依次尝试的常见安装位置（存在即采纳）。 */
const CHRYS_FALLBACK_CANDIDATES: readonly string[] = [
  "C:/Program Files/chrys/chrys.exe",
  "C:/Program Files (x86)/chrys/chrys.exe",
  "D:/Program Files/chrys/chrys.exe",
];

/** AAW skills 安装源目录默认值（本仓库 skills/ 全集；可在设置页修改）。 */
export const defaultSkillsSourceDir =
  "D:/dev/workspace-ai/Awesome-Agent-Workflow/skills";

const defaultLanguage: Language = "zh-CN";
const defaultApprovalMode: ApprovalMode = "ask";
const defaultTheme: ThemePreference = "dark";

/** 需要持久化的设置子集（连接测试状态属于运行时，不落盘）。 */
interface PersistedSettings {
  readonly chrysPath: string;
  readonly approvalMode: ApprovalMode;
  readonly language: Language;
  readonly skillsSourceDir: string;
  readonly theme: ThemePreference;
}

const defaultSettings: PersistedSettings = {
  chrysPath: defaultChrysPath,
  approvalMode: defaultApprovalMode,
  language: defaultLanguage,
  skillsSourceDir: defaultSkillsSourceDir,
  theme: defaultTheme,
};

const storageKey = "aaw-desktop.settings.v1";

function isApprovalMode(value: unknown): value is ApprovalMode {
  return value === "ask" || value === "auto-allow" || value === "auto-reject";
}

function isLanguage(value: unknown): value is Language {
  return value === "zh-CN" || value === "en-US";
}

function isTheme(value: unknown): value is ThemePreference {
  return value === "dark" || value === "warm";
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

/** 读取持久化设置：解析失败或字段非法时逐项回落默认。 */
function loadPersistedSettings(): PersistedSettings {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (raw === null) {
      return defaultSettings;
    }
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== "object" || parsed === null) {
      return defaultSettings;
    }
    const record = parsed as Readonly<Record<string, unknown>>;
    let language = isLanguage(record["language"])
      ? record["language"]
      : defaultSettings.language;
    if (language === "en-US") {
      // 英文是已下线的预留选项（i18n 选单不再暴露）：旧持久化值启动即
      // 回落中文并记日志，避免用户停留在半成品英文界面
      logger.warn("持久化语言为已下线的 en-US 预留项，回落 zh-CN");
      language = defaultLanguage;
    }
    return {
      chrysPath: isNonEmptyString(record["chrysPath"])
        ? record["chrysPath"]
        : defaultSettings.chrysPath,
      approvalMode: isApprovalMode(record["approvalMode"])
        ? record["approvalMode"]
        : defaultSettings.approvalMode,
      language,
      skillsSourceDir: isNonEmptyString(record["skillsSourceDir"])
        ? record["skillsSourceDir"]
        : defaultSettings.skillsSourceDir,
      theme: isTheme(record["theme"]) ? record["theme"] : defaultSettings.theme,
    };
  } catch (error) {
    logger.warn("读取持久化设置失败，使用默认值", {
      error: error instanceof Error ? error.message : String(error),
    });
    return defaultSettings;
  }
}

function persistSettings(settings: PersistedSettings): void {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(settings));
  } catch (error) {
    // 持久化失败不阻断设置生效，仅记录（如隐私模式下的配额限制）
    logger.warn("写入持久化设置失败", {
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

// ------------------------------------------------------------- 路径自动探测

/** 取命令输出里的首个非空行（PATH 查找结果的第一条路径）。 */
function firstOutputLine(stdout: string): string | null {
  const line = stdout
    .split(/\r?\n/)
    .map((part) => part.trim())
    .find((part) => part.length > 0);
  return line ?? null;
}

/**
 * 异步探测 chrys 可执行路径：先在 PATH 里找（Windows 的 where 与
 * 类 Unix 的 which 各试一次，spawn 失败按未命中处理），再回落常见安装
 * 位置与用户级 chrys 目录。找到返回绝对路径，探测不到返回 null。
 * 宿主可注入（测试用内存宿主布置现场）。
 */
export async function probeChrysPath(
  host: HostRuntime = hostRuntime,
): Promise<string | null> {
  // PATH 查找：where / which 谁可用用谁（失败一律继续，不猜测平台）
  for (const lookup of ["where", "which"]) {
    try {
      const result = await host.runCommand(lookup, ["chrys"]);
      if (result.code === 0) {
        const found = firstOutputLine(result.stdout);
        if (found !== null) {
          return found;
        }
      }
    } catch {
      // 该查找命令不存在 / 宿主不支持：继续下一个探测手段
    }
  }
  // 常见安装位置
  for (const candidate of CHRYS_FALLBACK_CANDIDATES) {
    try {
      if (await host.pathExists(candidate)) {
        return candidate;
      }
    } catch {
      // pathExists 失败按未命中处理
    }
  }
  // 用户级 chrys 目录的同名可执行（%APPDATA%/chrys/chrys.exe 等）
  try {
    const skillsDir = await host.chrysSkillsDir();
    const candidate = joinPath(skillsDir, "..", "chrys.exe");
    if (await host.pathExists(candidate)) {
      return candidate;
    }
  } catch {
    // 宿主不支持：忽略
  }
  return null;
}

/** 「测试连接」的运行时状态。 */
export interface ConnectionStatus {
  readonly status: "idle" | "testing" | "ok" | "error";
  readonly message: string;
  /** 最近一次成功/失败检测的 ISO 时间戳；未检测过为 null。 */
  readonly checkedAt: string | null;
}

interface SettingsStoreState {
  readonly chrysPath: string;
  readonly approvalMode: ApprovalMode;
  readonly language: Language;
  readonly skillsSourceDir: string;
  readonly theme: ThemePreference;
  readonly connection: ConnectionStatus;
  /** chrys 路径自动探测进行中（启动时路径为空才触发一次）。 */
  readonly isProbingChrysPath: boolean;
  setChrysPath: (path: string) => void;
  setApprovalMode: (mode: ApprovalMode) => void;
  setLanguage: (language: Language) => void;
  setSkillsSourceDir: (dir: string) => void;
  setTheme: (theme: ThemePreference) => void;
  /** 执行 `<chrysPath> --version` 验证路径可用性。 */
  testConnection: () => Promise<void>;
  /** 路径为空时的启动探测（PATH 与常见安装位置；只探一次）。 */
  probeChrysPathIfNeeded: () => Promise<void>;
  /** 全部恢复默认值。 */
  resetToDefaults: () => void;
}

export const useSettingsStore = create<SettingsStoreState>()((set, get) => {
  /** 应用一次命令结果：testConnection 的归约器。 */
  function applyConnectionResult(result: CommandResult): void {
    const next: ConnectionStatus =
      result.code === 0
        ? {
            status: "ok",
            message:
              result.stdout.trim().length > 0
                ? `可用（版本 ${result.stdout.trim()}）`
                : "可用（无版本输出）",
            checkedAt: new Date().toISOString(),
          }
        : {
            status: "error",
            message:
              result.stderr.trim().length > 0
                ? result.stderr.trim()
                : `命令以退出码 ${result.code} 结束`,
            checkedAt: new Date().toISOString(),
          };
    logger.info("chrys 连接检测完成", {
      code: result.code,
      ok: next.status === "ok",
    });
    set({ connection: next });
  }

  /** 写入并持久化一批设置（真实 setter 与 reset 共用）。 */
  function applySettings(patch: Partial<PersistedSettings>): void {
    const next = { ...get(), ...patch };
    set(patch);
    persistSettings({
      chrysPath: next.chrysPath,
      approvalMode: next.approvalMode,
      language: next.language,
      skillsSourceDir: next.skillsSourceDir,
      theme: next.theme,
    });
  }

  return {
    ...loadPersistedSettings(),
    connection: {
      status: "idle",
      message: "尚未检测",
      checkedAt: null,
    },
    isProbingChrysPath: false,
    setChrysPath: (path) => {
      applySettings({ chrysPath: path });
      // 路径变更后，旧检测结果不再有效
      set({
        connection: {
          status: "idle",
          message: "路径已变更，请重新检测",
          checkedAt: null,
        },
      });
    },
    setApprovalMode: (mode) => {
      applySettings({ approvalMode: mode });
      logger.info("审批默认模式已更新", { mode });
    },
    setLanguage: (language) => {
      applySettings({ language });
      logger.info("界面语言已更新", { language });
    },
    setSkillsSourceDir: (dir) => {
      applySettings({ skillsSourceDir: dir });
    },
    setTheme: (theme) => {
      applySettings({ theme });
      logger.info("界面主题已更新", { theme });
    },
    testConnection: async () => {
      const program = get().chrysPath;
      if (program.trim() === "") {
        // 空路径（未配置且未探测到）：直接失败收口，不执行空命令
        set({
          connection: {
            status: "error",
            message:
              "未配置 chrys 可执行路径，请手动填写或重新打开应用自动探测",
            checkedAt: new Date().toISOString(),
          },
        });
        return;
      }
      set({
        connection: {
          status: "testing",
          message: `正在执行 ${program} --version …`,
          checkedAt: null,
        },
      });
      logger.info("测试 chrys 连接", { program });
      let result: CommandResult;
      try {
        result = await hostRuntime.runCommand(program, ["--version"]);
      } catch (error) {
        result = {
          code: -1,
          stdout: "",
          stderr: error instanceof Error ? error.message : String(error),
        };
      }
      applyConnectionResult(result);
    },
    probeChrysPathIfNeeded: async () => {
      if (get().chrysPath.trim() !== "" || get().isProbingChrysPath) {
        // 已有路径（含用户持久化值）或在探测中：不覆盖
        return;
      }
      set({ isProbingChrysPath: true });
      try {
        const found = await probeChrysPath();
        if (found !== null && get().chrysPath.trim() === "") {
          // 探测结果写入并持久化（用户在探测期间手动填写的值不覆盖）
          applySettings({ chrysPath: found });
          logger.info("已自动探测到 chrys 路径", { chrysPath: found });
        } else if (found === null) {
          logger.warn("未在 PATH 与常见位置找到 chrys，请在设置中手动指定路径");
        }
      } finally {
        set({ isProbingChrysPath: false });
      }
    },
    resetToDefaults: () => {
      applySettings({ ...defaultSettings });
      logger.info("设置已恢复默认值");
    },
  };
});

// 启动即探测：路径为空（默认空值 / 未配置）时异步找一次 chrys（PATH 与
// 常见安装位置），探测到即写入并持久化，探测不到保持为空——设置页会
// 提示手动指定。已有用户持久化值不受影响（probeChrysPathIfNeeded 直通）。
void useSettingsStore.getState().probeChrysPathIfNeeded();
