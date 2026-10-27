/**
 * edit 类工具的「改动」视图（工具卡展开区输入段的替身）：
 * - edit_file：±1 行上下文的行级 diff（增行绿/删行红，双列行号，连续
 *   未变区间折叠为 ⋯），头部给 `路径 +N -M` 统计；
 * - write_file：新内容预览（超过 WRITE_PREVIEW_LINE_LIMIT 行截断提示）。
 * 数据全部来自 editDiff 纯函数，本组件只做渲染。
 */
import { useMemo } from "react";
import type { DiffResult, EditPayload } from "./editDiff.ts";
import { buildDiffRows, previewLines } from "./editDiff.ts";

/** diff 行的底色：增=ok 系，删=danger 系（与全局语义色一致）。 */
const rowClasses: Readonly<Record<string, string>> = {
  context: "",
  add: "bg-ok-bg/40",
  del: "bg-danger-bg/40",
  gap: "",
};

function DiffRowsView({ diff }: { readonly diff: DiffResult }) {
  if (diff.rows.length === 0) {
    return (
      <p className="px-2.5 py-1.5 text-xs text-ink-faint">（无差异行）</p>
    );
  }
  return (
    <div
      className="max-h-64 overflow-auto rounded bg-base/70 font-mono text-xs leading-relaxed"
      aria-label="行级差异"
    >
      {diff.rows.map((row, index) => (
        <div
          key={index}
          className={`flex gap-2 px-2.5 whitespace-pre-wrap break-words ${
            rowClasses[row.type] ?? ""
          }`}
        >
          <span className="w-7 shrink-0 select-none text-right text-ink-ghost">
            {row.type === "gap" ? "" : (row.oldNo ?? "")}
          </span>
          <span className="w-7 shrink-0 select-none text-right text-ink-ghost">
            {row.type === "gap" ? "" : (row.newNo ?? "")}
          </span>
          <span
            aria-hidden={true}
            className="w-3 shrink-0 select-none text-center"
          >
            {row.type === "add" ? (
              <span className="text-ok-ink">+</span>
            ) : row.type === "del" ? (
              <span className="text-danger-ink">−</span>
            ) : row.type === "gap" ? (
              <span className="text-ink-ghost">⋯</span>
            ) : null}
          </span>
          <span
            className={`min-w-0 flex-1 ${
              row.type === "gap"
                ? "select-none text-ink-ghost"
                : "text-ink-soft"
            }`}
          >
            {row.text}
          </span>
        </div>
      ))}
    </div>
  );
}

/** write_file：新内容预览（截断提示兜底，完整内容仍可看输入 JSON）。 */
function WritePreview({ content }: { readonly content: string }) {
  const preview = useMemo(() => previewLines(content), [content]);
  return (
    <div
      className="max-h-64 overflow-auto rounded bg-base/70 p-2.5 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words text-ink-soft"
      aria-label="新文件内容预览"
    >
      {preview.lines.length === 0
        ? "（空文件）"
        : preview.lines.map((line, index) => (
            <div key={index}>{line.length === 0 ? " " : line}</div>
          ))}
      {preview.truncated ? (
        <div className="select-none pt-1 text-ink-ghost">
          ⋯ 已截断预览，完整内容见「输入」JSON
        </div>
      ) : null}
    </div>
  );
}

function EditCard({
  path,
  oldString,
  newString,
}: {
  readonly path: string;
  readonly oldString: string;
  readonly newString: string;
}) {
  const diff = useMemo(
    () => buildDiffRows(oldString, newString, 1),
    [oldString, newString],
  );
  return (
    <div className="space-y-1">
      <div className="flex min-w-0 items-center gap-2 font-mono text-2xs">
        <span className="truncate text-ink-soft" title={path}>
          {path}
        </span>
        <span className="shrink-0">
          <span className="text-ok-ink">+{diff.added}</span>{" "}
          <span className="text-danger-ink">−{diff.removed}</span>
        </span>
      </div>
      <DiffRowsView diff={diff} />
    </div>
  );
}

function WriteCard({
  path,
  content,
}: {
  readonly path: string;
  readonly content: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex min-w-0 items-center gap-2 font-mono text-2xs">
        <span className="truncate text-ink-soft" title={path}>
          {path}
        </span>
        <span className="shrink-0 text-ink-faint">新文件</span>
      </div>
      <WritePreview content={content} />
    </div>
  );
}

export function EditDiffView({ payload }: { readonly payload: EditPayload }) {
  if (payload.kind === "write") {
    return <WriteCard path={payload.path} content={payload.content} />;
  }
  return (
    <EditCard
      path={payload.path}
      oldString={payload.oldString}
      newString={payload.newString}
    />
  );
}
