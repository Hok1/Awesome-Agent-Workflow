import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { panelService, type GitSnapshot } from "../../core/panelService.ts";
import {
  changeKey,
  findReviewMatches,
  reviewChanges,
  reviewSources,
  type ReviewMatch,
  type ReviewSource,
} from "../../core/gitReview.ts";
import { createGitDiffCache } from "../../core/gitDiffCache.ts";
import { useProjectGit } from "./useProjectGit.ts";
import { GitReviewDiff } from "./GitReviewDiff.tsx";
import { useRightPanelStore } from "../../stores/rightPanelStore.ts";
import { pathKey } from "../../core/panelPaths.ts";
export { GitDiffView } from "./GitDiffView.tsx";

export function GitPanel({ project }: { project: string }) {
  const result = useProjectGit(project);
  return (
    <div className="flex h-full min-h-0 flex-col text-xs">
      {result.error && (
        <p role="alert" className="p-3 text-danger-ink">
          {result.error}
        </p>
      )}
      {result.watchError && (
        <p className="p-2 text-warn-ink">{result.watchError}</p>
      )}
      {result.data ? (
        <GitReview
          project={project}
          data={result.data}
          loading={result.loading}
          onRefresh={result.refresh}
        />
      ) : (
        <div className="p-3">
          <button
            className="rounded border border-line px-2 py-1"
            onClick={result.refresh}
          >
            刷新
          </button>
          {result.loading && <p className="py-2">正在读取 Git 状态…</p>}
        </div>
      )}
    </div>
  );
}

function GitReview({
  project,
  data,
  loading,
  onRefresh,
}: {
  project: string;
  data: GitSnapshot;
  loading: boolean;
  onRefresh: () => void;
}) {
  const source = useRightPanelStore(
    (state) => state.projects[pathKey(project)]?.gitSource ?? "unstaged",
  );
  const [expanded, setExpanded] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<ReviewMatch | null>(null);
  const [navigation, setNavigation] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const changes = useMemo(() => reviewChanges(data, source), [data, source]);
  // 新快照必须建立新缓存，即使项目和路径未变，正文也可能已变化。
  const cache = useMemo(
    () => createGitDiffCache((change) => panelService.gitDiff(project, change)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, project],
  );
  const entries = useSyncExternalStore(cache.subscribe, cache.getSnapshot);
  useEffect(() => cache.retain(), [cache]);
  const hasQuery = query.trim().length > 0;
  useEffect(() => {
    cache.request(
      hasQuery
        ? changes
        : changes.filter((change) => changeKey(change) === expanded),
    );
  }, [cache, changes, hasQuery, expanded]);
  const matches = useMemo(
    () =>
      hasQuery
        ? changes.flatMap((change) => {
            const key = changeKey(change),
              model = entries[key]?.model;
            return model ? findReviewMatches(key, model, query) : [];
          })
        : [],
    [changes, entries, query, hasQuery],
  );
  const selectedIndex = selected
    ? matches.findIndex(
        (match) =>
          match.key === selected.key &&
          match.row === selected.row &&
          match.start === selected.start &&
          match.side === selected.side,
      )
    : -1;
  const activeIndex = matches.length ? Math.max(0, selectedIndex) : -1;
  const active = matches[activeIndex];
  const expandedKey = active?.key ?? expanded;
  // TanStack Virtual 自行维护测量状态，此组件不依赖 React Compiler 自动记忆化。
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: changes.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 36,
    overscan: 14,
    getItemKey: (index) => (changes[index] ? changeKey(changes[index]) : index),
  });
  const virtual = changes.length > 100;
  const locateMatch = useCallback(
    (element: HTMLElement): void => {
      element.scrollIntoView?.({ block: "center", inline: "nearest" });
      if (virtual && scrollRef.current) {
        // 用命中行的实际位置替换虚拟列表的文件定位目标，避免后续尺寸校准拉回文件中部。
        virtualizer.scrollToOffset(scrollRef.current.scrollTop, {
          align: "start",
        });
      }
    },
    [virtual, virtualizer],
  );
  useLayoutEffect(() => {
    virtualizer.measure();
  }, [virtualizer, expandedKey]);
  useLayoutEffect(() => {
    if (!active) return;
    const index = changes.findIndex(
      (change) => changeKey(change) === active.key,
    );
    if (virtual) virtualizer.scrollToIndex(index, { align: "center" });
    else
      scrollRef.current
        ?.querySelector(`[data-review-index="${index}"]`)
        ?.scrollIntoView?.({ block: "nearest" });
  }, [active, changes, navigation, virtual, virtualizer]);
  const move = (delta: number): void => {
    if (!matches.length) return;
    setSelected(
      matches[(activeIndex + delta + matches.length) % matches.length] ?? null,
    );
    setNavigation((old) => old + 1);
  };
  const pending = hasQuery
    ? changes.filter(
        (change) =>
          !entries[changeKey(change)] || entries[changeKey(change)]?.loading,
      ).length
    : 0;
  const failures = hasQuery
    ? changes.filter((change) => entries[changeKey(change)]?.error).length
    : 0;
  const skipped = hasQuery
    ? changes.filter((change) => entries[changeKey(change)]?.data?.notice)
        .length
    : 0;
  const renderChange = (index: number) => {
    const change = changes[index];
    if (!change) return null;
    const key = changeKey(change),
      entry = entries[key],
      isOpen = expandedKey === key;
    const name = change.path.split("/").at(-1) ?? change.path;
    const directory = change.path.includes("/")
      ? change.path.slice(0, change.path.lastIndexOf("/"))
      : "";
    return (
      <div data-review-index={index}>
        <button
          aria-expanded={isOpen}
          aria-label={`${isOpen ? "收起" : "展开"} ${change.path}`}
          title={`${change.oldPath ? `${change.oldPath} → ` : ""}${change.path} · ${change.status}`}
          className={`sticky top-0 z-10 flex h-9 w-full items-center gap-2 border-b border-line bg-surface px-3 text-left hover:bg-raised ${isOpen ? "font-medium" : ""}`}
          onClick={() => setExpanded(isOpen ? null : key)}
        >
          <span className="min-w-0 flex-1 truncate">
            <span>{name}</span>
            <span className="ml-2 text-ink-faint">{directory}</span>
          </span>
          <span className="shrink-0 whitespace-nowrap">
            <span className="text-ok-ink">+{change.added ?? 0}</span>
            <span className="ml-2 text-danger-ink">−{change.removed ?? 0}</span>
          </span>
          <span aria-hidden="true">{isOpen ? "▾" : "▸"}</span>
        </button>
        {isOpen && (
          <div className="border-b border-line">
            {(!entry || entry.loading) && (
              <p className="p-3 text-ink-faint">正在读取差异…</p>
            )}
            {entry?.error && (
              <p role="alert" className="p-3 text-danger-ink">
                {entry.error}
              </p>
            )}
            {entry?.data?.notice && (
              <p className="p-3 text-warn-ink">{entry.data.notice}</p>
            )}
            {entry?.model && (
              <GitReviewDiff
                key={key}
                model={entry.model}
                query={query}
                match={active?.key === key ? active : undefined}
                navigation={navigation}
                onLocate={locateMatch}
              />
            )}
          </div>
        )}
      </div>
    );
  };
  return (
    <div
      className="flex min-h-0 flex-1 flex-col"
      onKeyDown={(event) => {
        if (
          (event.ctrlKey || event.metaKey) &&
          event.key.toLowerCase() === "f"
        ) {
          event.preventDefault();
          event.stopPropagation();
          searchRef.current?.focus();
          searchRef.current?.select();
        }
      }}
    >
      <div className="flex items-center gap-2 border-b border-line p-3">
        <select
          aria-label="变更来源"
          className="min-w-0 flex-1 rounded border border-line bg-surface px-2 py-1.5"
          value={source}
          onChange={(event) => {
            useRightPanelStore
              .getState()
              .gitSource(project, event.target.value as ReviewSource);
            setExpanded(null);
            setSelected(null);
          }}
        >
          {reviewSources.map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
        <button
          disabled={loading}
          className="rounded border border-line px-2 py-1.5 disabled:opacity-50"
          onClick={onRefresh}
        >
          {loading ? "刷新中…" : "刷新"}
        </button>
      </div>
      <div className="flex items-center gap-1 border-b border-line p-2">
        <input
          ref={searchRef}
          aria-label="查找变更内容"
          placeholder="查找变更内容"
          value={query}
          className="min-w-0 flex-1 rounded border border-line bg-base px-2 py-1.5"
          onChange={(event) => {
            setQuery(event.target.value);
            setSelected(null);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              move(event.shiftKey ? -1 : 1);
            }
            if (event.key === "Escape") {
              event.stopPropagation();
              setQuery("");
              setSelected(null);
            }
          }}
        />
        <output aria-label="查找命中数" className="shrink-0 text-ink-faint">
          {activeIndex + 1}/{matches.length}
        </output>
        <button
          disabled={!matches.length}
          aria-label="上一处匹配"
          className="px-1 disabled:opacity-40"
          onClick={() => move(-1)}
        >
          ↑
        </button>
        <button
          disabled={!matches.length}
          aria-label="下一处匹配"
          className="px-1 disabled:opacity-40"
          onClick={() => move(1)}
        >
          ↓
        </button>
        {query && (
          <button
            aria-label="清空查找"
            className="px-1"
            onClick={() => {
              setQuery("");
              setSelected(null);
            }}
          >
            ×
          </button>
        )}
      </div>
      {hasQuery && (pending > 0 || failures > 0 || skipped > 0) && (
        <p role="status" className="px-3 py-1 text-ink-faint">
          {pending > 0 ? `正在查找，剩余 ${pending} 个文件。` : ""}
          {failures > 0 ? `${failures} 个文件读取失败，结果不完整。` : ""}
          {skipped > 0 ? `${skipped} 个文件无法完整查找。` : ""}
        </p>
      )}
      {source === "branch" && data.upstream && (
        <p className="px-3 py-1 text-ink-faint">{data.upstream}…HEAD</p>
      )}
      {source === "branch" && data.branchError && (
        <p role="alert" className="p-3 text-danger-ink">
          {data.branchError}
        </p>
      )}
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-auto"
        aria-label="Git 变更文件列表"
      >
        {!data.repoRoot ? (
          <p className="p-4 text-ink-faint">此项目不是 Git 仓库</p>
        ) : source === "last-turn" ? (
          <p className="p-4 text-ink-faint">
            暂无上一轮更改。当前尚未接入轮次文件快照。
          </p>
        ) : source === "branch" && !data.upstream ? (
          <p className="p-4 text-ink-faint">
            当前分支没有跟踪上游，暂无分支对比。
          </p>
        ) : changes.length === 0 ? (
          <p className="p-4 text-ink-faint">当前来源没有变更</p>
        ) : virtual ? (
          <div
            className="relative"
            style={{ height: virtualizer.getTotalSize() }}
          >
            {virtualizer.getVirtualItems().map((row) => (
              <div
                key={row.key}
                data-index={row.index}
                ref={virtualizer.measureElement}
                className="absolute left-0 w-full"
                style={{ top: row.start }}
              >
                {renderChange(row.index)}
              </div>
            ))}
          </div>
        ) : (
          changes.map((change, index) => (
            <div key={changeKey(change)}>{renderChange(index)}</div>
          ))
        )}
      </div>
    </div>
  );
}
