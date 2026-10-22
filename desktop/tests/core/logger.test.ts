/**
 * src/core/logger 单元测试：环形缓冲语义、级别过滤、
 * 通道上下文与 acpTraffic 分类。测试对象即「供诊断页读取」的数据源。
 */
import {
  LogSink,
  Logger,
  RingBuffer,
  createAcpTrafficChannel,
  type AcpTrafficEntry,
  type LogEntry,
} from "../../src/core/logger";

describe("RingBuffer", () => {
  it("容量必须为正整数，否则抛 RangeError", () => {
    expect(() => new RingBuffer<number>(0)).toThrow(RangeError);
    expect(() => new RingBuffer<number>(1.5)).toThrow(RangeError);
    expect(() => new RingBuffer<number>(-3)).toThrow(RangeError);
  });

  it("按写入顺序快照返回", () => {
    const buffer = new RingBuffer<string>(3);
    buffer.push("a");
    buffer.push("b");
    expect(buffer.snapshot()).toEqual(["a", "b"]);
    expect(buffer.size).toBe(2);
  });

  it("写满后覆盖最旧条目", () => {
    const buffer = new RingBuffer<number>(2);
    buffer.push(1);
    buffer.push(2);
    buffer.push(3);
    expect(buffer.snapshot()).toEqual([2, 3]);
    expect(buffer.size).toBe(2);
  });

  it("clear 清空并通知订阅者", () => {
    const buffer = new RingBuffer<number>(2);
    const snapshots: Array<readonly number[]> = [];
    buffer.subscribe((snapshot) => {
      snapshots.push([...snapshot]);
    });
    buffer.push(1);
    buffer.clear();
    expect(snapshots.at(-1)).toEqual([]);
    expect(buffer.size).toBe(0);
  });

  it("退订后不再收到通知", () => {
    const buffer = new RingBuffer<number>(2);
    let notified = 0;
    const unsubscribe = buffer.subscribe(() => {
      notified += 1;
    });
    buffer.push(1);
    unsubscribe();
    buffer.push(2);
    expect(notified).toBe(1);
  });
});

describe("LogSink", () => {
  it("低于当前级别的日志被丢弃", () => {
    const sink = new LogSink(16, "warn");
    sink.log("info", "test", "不应记录");
    expect(
      sink.snapshot().every((entry: LogEntry) => entry.level !== "info"),
    ).toBe(true);
    sink.log("error", "test", "应记录");
    expect(
      sink.snapshot().some((entry: LogEntry) => entry.message === "应记录"),
    ).toBe(true);
  });

  it("setLevel 后低级别日志恢复记录", () => {
    const sink = new LogSink(16, "error");
    sink.setLevel("debug");
    expect(sink.level).toBe("debug");
    sink.log("debug", "test", "现在能记录");
    expect(sink.snapshot().at(-1)?.message).toBe("现在能记录");
  });

  it("logger 的 child 继承通道并合并上下文", () => {
    const sink = new LogSink(16, "debug");
    const logger = new Logger(sink, "acp", { sessionId: "s-1" });
    logger.child({ requestId: 7 }).info("消息", { extra: "x" });
    const last = sink.snapshot().at(-1);
    expect(last?.channel).toBe("acp");
    expect(last?.context).toEqual({
      sessionId: "s-1",
      requestId: 7,
      extra: "x",
    });
  });

  it("条目包含级别、时间戳与结构化上下文", () => {
    const sink = new LogSink(8, "debug");
    const logger = new Logger(sink, "aaw");
    logger.info("流程已启动", { workflow: "skill-eval" });
    const entry = sink.snapshot().at(-1);
    expect(entry?.level).toBe("info");
    expect(entry?.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
    expect(entry?.context).toEqual({ workflow: "skill-eval" });
  });
});

describe("acpTraffic 通道", () => {
  it("按 JSON-RPC 形状分类 request / response / notification", () => {
    const channel = createAcpTrafficChannel(8);
    channel.recordOut({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {},
    });
    channel.recordIn({ jsonrpc: "2.0", id: 1, result: { agentInfo: {} } });
    channel.recordIn({ jsonrpc: "2.0", method: "session/update", params: {} });

    const entries: readonly AcpTrafficEntry[] = channel.snapshot();
    expect(entries).toHaveLength(3);
    expect(entries[0]?.kind).toBe("request");
    expect(entries[0]?.direction).toBe("out");
    expect(entries[0]?.method).toBe("initialize");
    expect(entries[0]?.requestId).toBe(1);
    expect(entries[1]?.kind).toBe("response");
    expect(entries[1]?.method).toBeNull();
    expect(entries[1]?.requestId).toBe(1);
    expect(entries[2]?.kind).toBe("notification");
    expect(entries[2]?.requestId).toBeNull();
  });

  it("循环引用 payload 不抛异常且可还原标记", () => {
    const channel = createAcpTrafficChannel(4);
    const circular: Record<string, unknown> = { name: "demo" };
    circular["self"] = circular;
    expect(() => channel.recordIn(circular)).not.toThrow();
    const entry = channel.snapshot().at(-1);
    expect(entry?.payload).toContain("[Circular]");
  });

  it("byteLength 反映 payload 的 UTF-8 字节数", () => {
    const channel = createAcpTrafficChannel(4);
    channel.recordOut({ jsonrpc: "2.0", method: "ping" });
    const entry = channel.snapshot().at(-1);
    expect(entry?.byteLength).toBe(
      new TextEncoder().encode(entry?.payload ?? "").length,
    );
  });
});
