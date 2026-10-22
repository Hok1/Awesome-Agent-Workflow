/**
 * 最小界面多语言设施（src/core）。
 *
 * 当前策略：中文为完整语言（默认），英文为「预留」——仅覆盖设置页高频
 * 词条，缺失词条回落中文，避免出现半成品的全量英文界面。新增文案时先在
 * `zhMessages` 补齐，英文词条随翻译进度逐步补入 `enMessages`。
 */

/** 界面语言。 */
export type Language = "zh-CN" | "en-US";

/**
 * 语言选单（顺序即展示顺序）。
 *
 * 只暴露中文：英文是半成品（仅覆盖设置页高频词条），不作为可选项露出，
 * 避免用户切到残缺界面。`Language` 类型与 en 词条机制保留，供未来翻译
 * 补齐后重新放开。
 */
export const languageOptions: readonly {
  readonly value: Language;
  readonly label: string;
}[] = [{ value: "zh-CN", label: "中文" }];

/** 词条键：先补 zh，再按进度补 en。 */
export type MessageKey =
  | "settings.title"
  | "settings.subtitle"
  | "settings.toolPathsSection"
  | "settings.toolPathsHint"
  | "settings.chrysSection"
  | "settings.chrysHint"
  | "settings.testConnection"
  | "settings.testing"
  | "settings.approvalSection"
  | "settings.approvalHint"
  | "settings.languageSection"
  | "settings.skillsSourceSection"
  | "settings.skillsSourceHint"
  | "settings.reset"
  | "approval.ask"
  | "approval.autoAllow"
  | "approval.autoReject";

const zhMessages: Readonly<Record<MessageKey, string>> = {
  "settings.title": "设置",
  "settings.subtitle":
    "工具路径、chrys 连接、审批默认模式、界面语言与 AAW skills 安装源",
  "settings.toolPathsSection": "工具路径",
  "settings.toolPathsHint":
    "健康检查与 AAW 状态查询都按这三条路径执行；项目总览只报结论，改路径在这里。",
  "settings.chrysSection": "chrys 可执行路径",
  "settings.chrysHint": "「测试连接」将执行 chrys --version 验证该路径可用",
  "settings.testConnection": "测试连接",
  "settings.testing": "测试中…",
  "settings.approvalSection": "审批默认模式",
  "settings.approvalHint":
    "chrys 请求执行工具时的默认处理方式（会话内审批弹窗显示的是 chrys 侧会话模式，两者独立）",
  "settings.languageSection": "界面语言",
  "settings.skillsSourceSection": "AAW skills 安装源目录",
  "settings.skillsSourceHint":
    "安装器会把该目录下的全部 skills 复制到用户级 chrys skills 目录",
  "settings.reset": "恢复默认设置",
  "approval.ask": "每次询问（弹出审批对话框）",
  "approval.autoAllow": "自动放行（默认允许工具调用）",
  "approval.autoReject": "自动拒绝（默认拒绝工具调用）",
};

/** 英文词条：有意保持 Partial——缺失键回落中文（预留，不算完整翻译）。 */
const enMessages: Partial<Readonly<Record<MessageKey, string>>> = {
  "settings.title": "Settings",
  "settings.chrysSection": "chrys executable path",
  "settings.testConnection": "Test connection",
  "settings.testing": "Testing…",
  "settings.languageSection": "Interface language",
  "settings.reset": "Reset to defaults",
};

/** 取翻译函数：当前语言词条 → 英文词条 → 中文词条 → 键名本身。 */
export function createTranslator(
  language: Language,
): (key: MessageKey) => string {
  return (key) => {
    if (language === "en-US") {
      return enMessages[key] ?? zhMessages[key] ?? key;
    }
    return zhMessages[key] ?? key;
  };
}
