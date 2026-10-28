import { panelError, type GitChange, type GitDiff } from "./panelService.ts";
import { changeKey, reviewModel, type ReviewModel } from "./gitReview.ts";

export interface DiffEntry {
  data?: GitDiff;
  model?: ReviewModel;
  error?: string;
  loading: boolean;
}
/** 一个 Git 快照一个缓存。关闭/换快照后，旧结果不再发布，等待队列停止。 */
export function createGitDiffCache(
  read: (change: GitChange) => Promise<GitDiff>,
) {
  let snapshot: Readonly<Record<string, DiffEntry>> = {};
  let queue: GitChange[] = [],
    running = 0,
    disposed = false,
    bytes = 0;
  let wanted = new Set<string>();
  const pending = new Set<string>();
  const listeners = new Set<() => void>();
  let owners = 0;
  const publish = (key: string, value: DiffEntry): void => {
    if (disposed) return;
    snapshot = { ...snapshot, [key]: value };
    listeners.forEach((listener) => listener());
  };
  const pump = (): void => {
    while (!disposed && running < 4 && queue.length) {
      const change = queue.shift();
      if (!change) break;
      const key = changeKey(change);
      if (!wanted.has(key) || pending.has(key) || snapshot[key]) continue;
      running++;
      pending.add(key);
      publish(key, { loading: true });
      void read(change)
        .then((data) => {
          if (disposed) return;
          // 先估算行对象成本，防止大量空行在建立模型时就耗尽内存。
          const textSize =
            2 *
            (data.patch.length +
              (data.beforeContent?.length ?? 0) +
              (data.afterContent?.length ?? 0));
          let estimatedRows = 1;
          for (const text of [
            data.patch,
            data.beforeContent ?? "",
            data.afterContent ?? "",
          ]) {
            for (let i = 0; i < text.length; i++)
              if (text.charCodeAt(i) === 10) estimatedRows++;
          }
          if (bytes + textSize * 2 + estimatedRows * 128 > 64 * 1024 * 1024) {
            publish(key, {
              loading: false,
              error: "本次查找内容超过缓存上限，请清空查找并刷新后逐文件查看",
            });
            return;
          }
          const model = reviewModel(data);
          const size =
            textSize +
            model.rows.reduce(
              (total, row) => total + 128 + row.text.length * 2,
              0,
            );
          bytes += size;
          publish(key, { data, model, loading: false });
        })
        .catch((error: unknown) =>
          publish(key, { error: panelError(error), loading: false }),
        )
        .finally(() => {
          running--;
          pending.delete(key);
          pump();
        });
    }
  };
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    retain() {
      owners++;
      // React StrictMode 会同步重放 setup/cleanup；真正卸载后才终止缓存。
      return () => {
        owners--;
        queueMicrotask(() => {
          if (owners === 0) {
            disposed = true;
            queue = [];
            listeners.clear();
          }
        });
      };
    },
    request(changes: readonly GitChange[]) {
      wanted = new Set(changes.map(changeKey));
      queue = changes.filter(
        (change) =>
          !snapshot[changeKey(change)] && !pending.has(changeKey(change)),
      );
      pump();
    },
    dispose() {
      disposed = true;
      queue = [];
      listeners.clear();
    },
  };
}
