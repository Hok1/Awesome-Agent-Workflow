import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { isTauriEnv } from "./host.ts";

export interface FileEntry {
  path: string;
  name: string;
  directory: boolean;
  symlink: boolean;
}
export interface DirectoryResult {
  entries: FileEntry[];
  truncated: boolean;
}
export interface FilePreview {
  kind: "image" | "text";
  content: string;
  mime: string;
  bytes: number;
}
export type GitSource =
  "staged" | "unstaged" | "untracked" | "conflict" | "branch";
export interface GitChange {
  path: string;
  oldPath: string | null;
  source: GitSource;
  status: string;
  added?: number;
  removed?: number;
}
export interface GitSnapshot {
  repoRoot: string | null;
  branch: string;
  changes: GitChange[];
  watchPaths: string[];
  upstream?: string | null;
  branchChanges?: GitChange[];
  branchError?: string | null;
}
export interface GitDiff {
  patch: string;
  notice: string | null;
  beforeContent?: string | null;
  afterContent?: string | null;
}
export interface WatchPath {
  path: string;
  recursive: boolean;
}
export function panelError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
async function call<T>(
  command: string,
  args: Record<string, unknown>,
): Promise<T> {
  if (!isTauriEnv()) throw new Error("此功能需要在 desktop 桌面客户端中使用");
  return invoke<T>(command, args);
}
export const panelService = {
  stat: (path: string) => call<FileEntry>("panel_stat", { path }),
  directory: (path: string) =>
    call<DirectoryResult>("panel_directory", { path }),
  preview: (path: string) => call<FilePreview>("panel_preview", { path }),
  gitStatus: (project: string) =>
    call<GitSnapshot>("panel_git_status", { project }),
  gitDiff: (project: string, change: GitChange) =>
    call<GitDiff>("panel_git_diff", { project, change }),
  async watch(
    paths: WatchPath[],
    changed: () => void,
    failed: (error: string) => void,
  ): Promise<() => void> {
    let id: number | null = null;
    const unlisten = await listen<{ id: number; error: string | null }>(
      "aaw://panel-files-changed",
      ({ payload }) => {
        if (payload.id !== id) return;
        if (payload.error) failed(payload.error);
        else changed();
      },
    );
    try {
      id = await call<number>("panel_watch", { paths });
    } catch (error) {
      unlisten();
      throw error;
    }
    const watchId = id;
    return () => {
      unlisten();
      void call("panel_unwatch", { id: watchId }).catch((error: unknown) =>
        failed(panelError(error)),
      );
    };
  },
};
