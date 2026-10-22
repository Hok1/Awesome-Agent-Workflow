/**
 * aawStatusStore 回归：真实通路（loader → 解析 → 状态）、容错处理
 * 与会话事件节流自动刷新。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  useAawStatusStore,
  type AawStatusLoader,
} from "../../src/stores/aawStatusStore.ts";
import type { AcpSessionEvent } from "../../src/acp/session.ts";
import {
  sampleNextJson,
  sampleSrListJson,
  sampleStatusJson,
} from "../fixtures/aawWorkflowSamples.ts";

/** 最小会话事件样本（agent 消息块，自动刷新的典型触发源）。 */
const chunkEvent: AcpSessionEvent = {
  type: "agent_message_chunk",
  sessionId: "s-1",
  text: "正在执行 aaw next…",
};

interface LoaderCounts {
  listSrs: number;
  readStatus: number;
  readNext: number;
}

/** 可计数的假数据源：缺省返回夹具样本，可按需覆写。 */
function makeLoader(
  overrides: Partial<
    Record<"listSrs" | "readStatus" | "readNext", unknown>
  > = {},
): AawStatusLoader & { counts: LoaderCounts } {
  const counts: LoaderCounts = { listSrs: 0, readStatus: 0, readNext: 0 };
  return {
    counts,
    listSrs: () => {
      counts.listSrs += 1;
      return Promise.resolve(overrides.listSrs ?? sampleSrListJson);
    },
    readStatus: () => {
      counts.readStatus += 1;
      return Promise.resolve(overrides.readStatus ?? sampleStatusJson);
    },
    readNext: () => {
      counts.readNext += 1;
      return Promise.resolve(overrides.readNext ?? sampleNextJson);
    },
  };
}

const store = useAawStatusStore;

beforeEach(() => {
  store.getState().reset();
  store.getState().setAutoRefresh(true);
  store.getState().bindLoader(null);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("refresh 真实通路", () => {
  it("未绑定 loader 时为安全的空操作", async () => {
    await store.getState().refresh();
    expect(store.getState().isLoading).toBe(false);
    expect(store.getState().lastError).toBeNull();
  });

  it("经 loader 读取并解析 status / next，自动选中首个 SR", async () => {
    const loader = makeLoader();
    store.getState().bindLoader(loader);
    await store.getState().refresh();

    const state = store.getState();
    expect(state.srs).toEqual(["SR-001", "SR-004"]);
    expect(state.currentSr).toBe("SR-001");
    expect(state.status?.steps).toHaveLength(6);
    expect(state.next?.ready).toHaveLength(1);
    expect(state.lastError).toBeNull();
    expect(state.lastRefreshedAt).not.toBeNull();
    expect(loader.counts).toEqual({ listSrs: 1, readStatus: 1, readNext: 1 });
  });

  it("selectSr 切换当前 SR 并触发该 SR 的刷新", async () => {
    const loader = makeLoader();
    store.getState().bindLoader(loader);
    await store.getState().refresh();
    store.getState().selectSr("SR-004");
    await vi.waitFor(() => {
      // status 来自切换后的刷新（夹具恒返回 SR-004 的样本）
      expect(store.getState().status?.sr).toBe("SR-004");
    });
    expect(store.getState().currentSr).toBe("SR-004");
    expect(loader.counts.readStatus).toBe(2);
  });

  it("重入保护：并发 refresh 只执行一份", async () => {
    const loader = makeLoader();
    store.getState().bindLoader(loader);
    await Promise.all([store.getState().refresh(), store.getState().refresh()]);
    expect(loader.counts.listSrs).toBe(1);
  });

  it("loader 抛错时记录中文错误，不抛出", async () => {
    store.getState().bindLoader({
      listSrs: () => Promise.reject(new Error("ENOENT: aaw.py 不存在")),
      readStatus: () => Promise.resolve(sampleStatusJson),
      readNext: () => Promise.resolve(sampleNextJson),
    });
    await store.getState().refresh();
    expect(store.getState().lastError).toMatch(/status 读取失败.*ENOENT/);
  });

  it("输出无法解析或错误信封时记录原因", async () => {
    store.getState().bindLoader(
      makeLoader({
        listSrs: "not-json",
        readStatus: {
          ok: false,
          error: { code: "WORKFLOW_NOT_FOUND", message: "SR 不存在" },
        },
      }),
    );
    await store.getState().refresh();
    // listSrs 解析失败 → currentSr 保持 null，后续 status/next 不再读取
    expect(store.getState().lastError).toMatch(/无法解析/);

    store.getState().reset();
    store.getState().bindLoader(
      makeLoader({
        readStatus: {
          ok: false,
          error: { code: "WORKFLOW_NOT_FOUND", message: "SR 不存在" },
        },
      }),
    );
    await store.getState().refresh();
    const error = store.getState().lastError ?? "";
    expect(error).toMatch(/WORKFLOW_NOT_FOUND/);
    expect(error).toMatch(/SR 不存在/);
  });
});

describe("refresh 落地与容错", () => {
  it("selectSr + refresh 落地该 SR 的完整数据状态", async () => {
    store.getState().bindLoader(makeLoader());
    await store.getState().refresh();
    store.getState().selectSr("SR-004");
    await vi.waitFor(() => {
      expect(store.getState().status?.sr).toBe("SR-004");
    });
    const state = store.getState();
    expect(state.srs).toEqual(["SR-001", "SR-004"]);
    expect(state.currentSr).toBe("SR-004");
    expect(state.status?.steps).toHaveLength(6);
    expect(state.next?.ready).toHaveLength(1);
    expect(state.lastError).toBeNull();
    expect(state.lastRefreshedAt).not.toBeNull();
  });

  it("输出无法解析时不落地且既有状态不被清空", async () => {
    // 第一轮：正常数据落地（夹具的 status 载荷描述的是 SR-004 的工作流）
    store.getState().bindLoader(makeLoader());
    await store.getState().refresh();
    const landedStatus = store.getState().status;
    expect(store.getState().srs).toEqual(["SR-001", "SR-004"]);
    expect(landedStatus).not.toBeNull();

    // 第二轮：status / next 返回无法解析的载荷——记录错误且不清空既有状态
    store
      .getState()
      .bindLoader(makeLoader({ readStatus: 42, readNext: "not-json" }));
    await store.getState().refresh();
    expect(store.getState().lastError).toMatch(/无法解析/);
    expect(store.getState().status).toBe(landedStatus);
    expect(store.getState().next?.ready).toHaveLength(1);
  });
});

describe("会话事件自动刷新（节流）", () => {
  it("冷却期外的首个事件立即刷新，冷却期内的事件尾随补一次", async () => {
    vi.useFakeTimers();
    // 系统时间取足够大的值，覆盖任何此前测试遗留的节流时间戳
    vi.setSystemTime(new Date("2026-10-20T23:00:00Z"));
    const loader = makeLoader();
    store.getState().bindLoader(loader);
    await store.getState().refresh();
    const before = loader.counts.listSrs;

    // 距上次刷新远超冷却窗口 → leading 立即触发
    store.getState().handleSessionEvent(chunkEvent);
    expect(loader.counts.listSrs).toBe(before + 1);

    // 冷却期内的连发事件只排一次尾随
    store.getState().handleSessionEvent(chunkEvent);
    store.getState().handleSessionEvent(chunkEvent);
    expect(loader.counts.listSrs).toBe(before + 1);

    await vi.advanceTimersByTimeAsync(2_000);
    expect(loader.counts.listSrs).toBe(before + 2);
  });

  it("关闭自动刷新后事件不再触发", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-20T10:00:00Z"));
    const loader = makeLoader();
    store.getState().bindLoader(loader);
    await store.getState().refresh();
    const before = loader.counts.listSrs;

    store.getState().setAutoRefresh(false);
    store.getState().handleSessionEvent(chunkEvent);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(loader.counts.listSrs).toBe(before);
  });

  it("未绑定 loader 或无当前 SR 时不刷新", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-20T10:00:00Z"));
    // 无 loader
    store.getState().handleSessionEvent(chunkEvent);
    // 有 loader 但无 SR（空列表）
    const loader = makeLoader({ listSrs: { ok: true, srs: [] } });
    store.getState().bindLoader(loader);
    store.getState().handleSessionEvent(chunkEvent);
    expect(loader.counts.listSrs).toBe(0);
  });
});
