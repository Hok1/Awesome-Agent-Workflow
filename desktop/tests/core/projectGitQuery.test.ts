import { afterEach, describe, expect, it, vi } from "vitest";
import { createProjectGitQuery } from "../../src/core/projectGitQuery.ts";
import type { GitSnapshot } from "../../src/core/panelService.ts";

const data: GitSnapshot = {
  repoRoot: "D:/repo",
  branch: "main",
  changes: [],
  watchPaths: ["D:/repo", "D:/repo/.git"],
};
const flush = async (): Promise<void> => {
  for (let i = 0; i < 8; i++) await Promise.resolve();
};
afterEach(() => vi.useRealTimers());

describe("项目 Git 共享查询", () => {
  it("两个消费者共享读取和监听，最后一位退出才释放，突发事件只刷新一次", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const stop = vi.fn();
    const status = vi.fn().mockResolvedValue(data);
    let changed: (() => void) | undefined;
    const watch = vi.fn((_paths, callback: () => void) => {
      changed = callback;
      return Promise.resolve(stop);
    });
    const query = createProjectGitQuery("D:/repo", { status, watch });
    const first = query.subscribe(vi.fn()),
      second = query.subscribe(vi.fn());
    await flush();
    expect(status).toHaveBeenCalledTimes(1);
    expect(watch).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 30; i++) changed?.();
    await vi.advanceTimersByTimeAsync(400);
    expect(status).toHaveBeenCalledTimes(2);
    first();
    await flush();
    expect(stop).not.toHaveBeenCalled();
    second();
    await flush();
    expect(stop).toHaveBeenCalledOnce();
    changed?.();
    await vi.advanceTimersByTimeAsync(1000);
    expect(status).toHaveBeenCalledTimes(2);
  });
  it("卸载后的迟到注册被释放，旧查询不能覆盖重新进入的项目快照", async () => {
    const finishes: ((snapshot: GitSnapshot) => void)[] = [];
    const status = vi.fn(
      () => new Promise<GitSnapshot>((resolve) => finishes.push(resolve)),
    );
    let finishWatch: ((stop: () => void) => void) | undefined;
    const watch = vi.fn(
      () =>
        new Promise<() => void>((resolve) => {
          finishWatch = resolve;
        }),
    );
    const query = createProjectGitQuery("D:/repo", { status, watch });
    const release = query.subscribe(vi.fn());
    await flush();
    release();
    await flush();
    const releaseAgain = query.subscribe(vi.fn());
    await flush();
    finishes[1]?.({ ...data, branch: "fresh" });
    await flush();
    finishes[0]?.({ ...data, branch: "old" });
    await flush();
    expect(query.getSnapshot().data?.branch).toBe("fresh");
    releaseAgain();
    await flush();
    const stop = vi.fn();
    finishWatch?.(stop);
    await flush();
    expect(stop).toHaveBeenCalledOnce();
  });
  it("刷新失败保留旧数据并标错；StrictMode重放不重复创建查询", async () => {
    const status = vi.fn().mockResolvedValue({ ...data, watchPaths: [] });
    const query = createProjectGitQuery("D:/repo", { status, watch: vi.fn() });
    query.subscribe(vi.fn())();
    const release = query.subscribe(vi.fn());
    await flush();
    expect(status).toHaveBeenCalledTimes(1);
    status.mockRejectedValueOnce(new Error("Git unavailable"));
    query.refresh();
    await flush();
    expect(query.getSnapshot()).toMatchObject({
      data: { branch: "main" },
      error: "Git unavailable",
      loading: false,
    });
    release();
    await flush();
  });
  it("监听注册失败后刷新会重试，即使监听路径没有变化", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const stop = vi.fn();
    const status = vi.fn().mockResolvedValue(data);
    const watch = vi
      .fn()
      .mockRejectedValueOnce(new Error("暂时不可用"))
      .mockResolvedValue(stop);
    const query = createProjectGitQuery("D:/repo", { status, watch });
    const release = query.subscribe(vi.fn());
    await flush();
    expect(query.getSnapshot().watchError).toContain("暂时不可用");
    query.refresh();
    await flush();
    expect(watch).toHaveBeenCalledTimes(2);
    expect(query.getSnapshot().watchError).toBeUndefined();
    release();
    await flush();
    expect(stop).toHaveBeenCalledOnce();
  });

  it("注册前的错误使该代失效，迟到成功与旧错误不能破坏新监听", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const pending: {
      fail: (message: string) => void;
      finish: (stop: () => void) => void;
    }[] = [];
    const status = vi.fn().mockResolvedValue(data);
    const watch = vi.fn(
      (_paths, _changed, fail: (message: string) => void) =>
        new Promise<() => void>((finish) => pending.push({ fail, finish })),
    );
    const query = createProjectGitQuery("D:/repo", { status, watch });
    const release = query.subscribe(vi.fn());
    await flush();
    pending[0]?.fail("提前出错");
    expect(query.getSnapshot().watchError).toContain("提前出错");
    query.refresh();
    await flush();
    expect(watch).toHaveBeenCalledTimes(2);
    const oldStop = vi.fn(),
      newStop = vi.fn();
    pending[1]?.finish(newStop);
    await flush();
    expect(query.getSnapshot().watchError).toBeUndefined();
    pending[0]?.finish(oldStop);
    await flush();
    pending[0]?.fail("迟到错误");
    expect(oldStop).toHaveBeenCalledOnce();
    expect(query.getSnapshot().watchError).toBeUndefined();
    expect(newStop).not.toHaveBeenCalled();
    pending[1]?.fail("运行时失败");
    expect(newStop).toHaveBeenCalledOnce();
    expect(query.getSnapshot().watchError).toContain("运行时失败");
    status.mockResolvedValueOnce({ ...data, watchPaths: [] });
    query.refresh();
    await flush();
    expect(query.getSnapshot().watchError).toBeUndefined();
    release();
    await flush();
  });
});
