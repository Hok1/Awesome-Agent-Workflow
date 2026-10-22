/**
 * 设置页：工具路径（iCode / uv / aaw 脚本，全站唯一配置点）、审批默认
 * 模式、界面语言、界面主题（外观区块）、AAW skills 安装源目录，以及内置
 * skills 安装器区块。
 *
 * 每项变更经 settings / workspace store 的真实 setter 即时写入本地持久化；
 * 文案经 core/i18n 取词（英文为预留词条，缺失回落中文）。
 *
 * 「恢复默认设置」会清掉上述全部本地配置，因此走行内二次确认（与关闭
 * 项目的确认同一形态），确认前不写任何状态。
 */
import { useMemo, useState } from "react";
import {
  approvalModeOptions,
  themeOptions,
  useSettingsStore,
} from "../stores/settingsStore";
import { createTranslator } from "../core/i18n";
import { languageOptions } from "../core/i18n";
import {
  btnDanger,
  btnGhost,
  btnPrimary,
  btnSecondary,
  Listbox,
  tabActiveClass,
} from "./controls";
import { useToolPathSettings } from "./workspaces/settingsLinks";
import SkillsInstallerSection from "./SkillsInstallerSection";

/** 输入框的公共样式（设置页内多处复用）。 */
const textInputClass =
  "rounded-md border border-line-strong bg-raised px-3 py-1.5 font-mono text-sm text-ink placeholder:text-ink-ghost focus:border-ink-faint focus:outline-none";

/** 「恢复默认设置」的行内确认：取消不动作，确认才写默认值。 */
function ResetConfirm({
  onConfirm,
  onCancel,
}: {
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}) {
  return (
    <span
      role="alertdialog"
      aria-label="恢复默认设置确认"
      className="flex items-center gap-2 rounded-md border border-line-strong bg-raised px-2 py-1 shadow-lg"
    >
      <span className="text-xs text-ink">
        将清除 iCode 路径、uv / aaw 路径、审批模式、语言、主题与 skills
        源目录，确认？
      </span>
      <button
        type="button"
        onClick={onCancel}
        className={`${btnSecondary} px-2 py-0.5 text-xs`}
      >
        取消
      </button>
      <button
        type="button"
        onClick={onConfirm}
        className={`${btnDanger} px-2 py-0.5 text-xs`}
      >
        恢复默认
      </button>
    </span>
  );
}

function SettingsPage() {
  const [isResetConfirmOpen, setResetConfirmOpen] = useState(false);
  const approvalMode = useSettingsStore((state) => state.approvalMode);
  const language = useSettingsStore((state) => state.language);
  const skillsSourceDir = useSettingsStore((state) => state.skillsSourceDir);
  const theme = useSettingsStore((state) => state.theme);
  const connection = useSettingsStore((state) => state.connection);
  const setApprovalMode = useSettingsStore((state) => state.setApprovalMode);
  const setLanguage = useSettingsStore((state) => state.setLanguage);
  const setSkillsSourceDir = useSettingsStore(
    (state) => state.setSkillsSourceDir,
  );
  const setTheme = useSettingsStore((state) => state.setTheme);
  const testConnection = useSettingsStore((state) => state.testConnection);
  const resetToDefaults = useSettingsStore((state) => state.resetToDefaults);
  const toolPaths = useToolPathSettings();

  const t = useMemo(() => createTranslator(language), [language]);

  return (
    <section aria-label="设置" className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-ink">
            {t("settings.title")}
          </h2>
          <p className="mt-1 text-sm text-ink-faint">
            {t("settings.subtitle")}
          </p>
        </div>
        {isResetConfirmOpen ? (
          <ResetConfirm
            onConfirm={() => {
              resetToDefaults();
              setResetConfirmOpen(false);
            }}
            onCancel={() => {
              setResetConfirmOpen(false);
            }}
          />
        ) : (
          <button
            type="button"
            onClick={() => {
              setResetConfirmOpen(true);
            }}
            className={`${btnGhost} px-2.5 py-1 text-xs`}
          >
            {t("settings.reset")}
          </button>
        )}
      </header>

      {/* 工具路径：iCode / uv / aaw 脚本一处配置。项目总览的健康检查与
          AAW 状态查询都用这里的三条路径执行。 */}
      <div className="space-y-4 rounded-lg border border-line bg-surface p-4">
        <div>
          <h3 className="text-sm font-medium text-ink">
            {t("settings.toolPathsSection")}
          </h3>
          <p className="mt-1 text-xs text-ink-faint">
            {t("settings.toolPathsHint")}
          </p>
        </div>

        <div>
          <label
            htmlFor="chrys-path"
            className="block text-sm font-medium text-ink"
          >
            {t("settings.chrysSection")}
          </label>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              id="chrys-path"
              type="text"
              value={toolPaths.chrysPath}
              onChange={(event) => {
                toolPaths.setChrysPath(event.target.value);
              }}
              className={`min-w-72 flex-1 ${textInputClass}`}
            />
            <button
              type="button"
              onClick={() => {
                void testConnection();
              }}
              disabled={connection.status === "testing"}
              className={`${btnPrimary} px-3 py-1.5 text-sm`}
            >
              {connection.status === "testing"
                ? t("settings.testing")
                : t("settings.testConnection")}
            </button>
          </div>
          {/* 路径为空（未配置且自动探测未命中）：提示手动指定 */}
          {toolPaths.chrysPath.trim() === "" && (
            <p role="alert" className="mt-1.5 text-xs text-warn-ink">
              未找到 iCode，请手动指定路径
            </p>
          )}
          {connection.status !== "idle" && connection.status !== "testing" && (
            <p
              role="status"
              className={`mt-1.5 text-sm ${
                connection.status === "ok" ? "text-ok-ink" : "text-danger-ink"
              }`}
            >
              {`${connection.message}${
                connection.checkedAt === null
                  ? ""
                  : ` · ${connection.checkedAt.slice(11, 19)}`
              }`}
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <label
              htmlFor="uv-command"
              className="block text-sm font-medium text-ink"
            >
              uv 命令
            </label>
            <input
              id="uv-command"
              type="text"
              value={toolPaths.uvCommand}
              onChange={(event) => {
                toolPaths.setUvCommand(event.target.value);
              }}
              placeholder="uv"
              className={`mt-2 w-full ${textInputClass}`}
            />
            <p className="mt-1.5 text-xs text-ink-faint">
              执行 aaw CLI 与工作流脚本的解释器命令（可写绝对路径）。
            </p>
          </div>
          <div>
            <label
              htmlFor="aaw-script"
              className="block text-sm font-medium text-ink"
            >
              aaw 脚本路径
            </label>
            <input
              id="aaw-script"
              type="text"
              value={toolPaths.aawScriptPath}
              onChange={(event) => {
                toolPaths.setAawScriptPath(event.target.value);
              }}
              placeholder="skills/aaw-workflow/scripts/aaw.py"
              className={`mt-2 w-full ${textInputClass}`}
            />
            <p className="mt-1.5 text-xs text-ink-faint">
              留空则按下方 skills 源目录推导
              （&lt;源目录&gt;/aaw-workflow/scripts/aaw.py）。
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-5 rounded-lg border border-line bg-surface p-4">
        <div>
          <span className="block text-sm font-medium text-ink">
            {t("settings.approvalSection")}
          </span>
          <div className="mt-2 w-80">
            <Listbox
              label={t("settings.approvalSection")}
              value={approvalMode}
              options={approvalModeOptions.map((option) => ({
                value: option.value,
                label: option.label,
              }))}
              onChange={(next) => {
                setApprovalMode(
                  next as (typeof approvalModeOptions)[number]["value"],
                );
              }}
              fullWidth={true}
              className="py-1.5 text-sm"
            />
          </div>
          <p className="mt-1.5 text-xs text-ink-faint">
            {t("settings.approvalHint")}
          </p>
        </div>

        <div>
          <span className="block text-sm font-medium text-ink">
            {t("settings.languageSection")}
          </span>
          <div className="mt-2 w-80">
            <Listbox
              label={t("settings.languageSection")}
              value={language}
              options={languageOptions.map((option) => ({
                value: option.value,
                label: option.label,
              }))}
              onChange={(next) => {
                setLanguage(next as (typeof languageOptions)[number]["value"]);
              }}
              fullWidth={true}
              className="py-1.5 text-sm"
            />
          </div>
        </div>

        {/* 外观：主题分段按钮（暗夜 / 暖白），写入 store 即持久化，
            根元素类由 App 的 ThemeRootBinding 按设置同步。 */}
        <div>
          <span className="block text-sm font-medium text-ink">外观</span>
          <div
            role="group"
            aria-label="外观主题"
            className="mt-2 flex w-fit gap-1 rounded-md border border-line bg-base p-0.5"
          >
            {themeOptions.map((option) => {
              const isSelected = theme === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => {
                    setTheme(option.value);
                  }}
                  className={`rounded px-3 py-1 text-xs transition-colors ${
                    isSelected ? tabActiveClass : "text-ink-mute hover:text-ink"
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
          <p className="mt-1.5 text-xs text-ink-faint">
            暗夜为默认深色界面；暖白为米白浅色界面。
          </p>
        </div>

        <div>
          <label
            htmlFor="skills-source"
            className="block text-sm font-medium text-ink"
          >
            {t("settings.skillsSourceSection")}
          </label>
          <input
            id="skills-source"
            type="text"
            value={skillsSourceDir}
            onChange={(event) => {
              setSkillsSourceDir(event.target.value);
            }}
            className={`mt-2 w-full ${textInputClass}`}
          />
          <p className="mt-1.5 text-xs text-ink-faint">
            {t("settings.skillsSourceHint")}
          </p>
        </div>
      </div>

      <SkillsInstallerSection />
    </section>
  );
}

export default SettingsPage;
