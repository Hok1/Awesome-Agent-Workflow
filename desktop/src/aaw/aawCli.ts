/**
 * aaw CLI 调用封装（src/aaw）：只读查询命令的统一出站封装与 stdout → JSON
 * 抽取。
 *
 * 调用形态（对照 skills/aaw-workflow/scripts/aaw.py，经 uv run）：
 * - 列表：`uv run <aaw.py> status --json` → `{"ok": true, "srs": [...]}`
 * - 详情：`uv run <aaw.py> status --sr <id> --json` →
 *   `{"ok": true, "sr", "status", "steps": [...], ...}`
 * - 工作单：`uv run <aaw.py> next --sr <id> --peek --json`
 * - 失败：`{"status": "failed", "error": "..."}`（退出码非 0）
 *
 * 本文件只负责「怎么调、怎么抽取 JSON」；命令的组合与使用方是
 * `src/aaw/statusLoader.ts` 的 `AawStatusLoader`（工作流状态面板的唯一
 * 数据源）。JSON 对象 → 领域模型的解析在 `src/aaw/workflowModel.ts`。
 */
import { describeRunFailure } from "./healthChecks.ts";
import type { ProcessRunner } from "./processRunner.ts";

/** 单次 aaw CLI 调用入参。 */
export interface AawStatusOptions {
  readonly workspacePath: string;
  readonly uvCommand: string;
  readonly aawScriptPath: string;
  readonly runner: ProcessRunner;
}

/** status 会触发 aaw 的会话入口自动更新，超时给足。 */
const AAW_STATUS_TIMEOUT_MS = 120_000;

/**
 * 执行一条 aaw CLI 只读查询并抽取 JSON（status / next 共用的出站封装）。
 * `src/aaw/statusLoader.ts` 的 loader 契约与这里共用同一命令形态，防止
 * 数据通路漂移。命令失败（非零退出 / 启动失败 / 超时）抛错，带 stderr
 * 摘要。
 */
export async function runAawJsonQuery(
  options: AawStatusOptions,
  args: readonly string[],
): Promise<unknown> {
  const result = await options.runner.run({
    command: [options.uvCommand, "run", options.aawScriptPath, ...args],
    cwd: options.workspacePath,
    timeoutMs: AAW_STATUS_TIMEOUT_MS,
  });
  if (!result.ok) {
    throw new Error(describeRunFailure(result));
  }
  return extractJsonObject(result.stdout);
}

/**
 * 从 CLI stdout 提取 JSON 对象：优先整段解析（typer 的 _echo_json 单独
 * 一行输出时两种等价），失败再从最后一行向前找首个可解析的对象。
 * 找不到返回 null。
 */
export function extractJsonObject(stdout: string): unknown {
  const whole = stdout.trim();
  if (whole === "") {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(whole);
    if (isRecord(parsed)) {
      return parsed;
    }
  } catch {
    // 整段不是 JSON：继续逐行找
  }
  const lines = whole.split("\n");
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i]?.trim() ?? "";
    if (!line.startsWith("{")) {
      continue;
    }
    try {
      const parsed: unknown = JSON.parse(line);
      if (isRecord(parsed)) {
        return parsed;
      }
    } catch {
      // 该行不是合法 JSON：继续向前
    }
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
