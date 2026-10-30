/**
 * src/stores/protocolProbeStore 测试：探查状态机流转（idle → probing →
 * done）与结果持有。探查执行本身在 tests/ui/agentProbe.test.ts。
 */
import { beforeEach, describe, expect, it } from "vitest";
import {
  useProtocolProbeStore,
  type AgentProbeResult,
} from "../../src/stores/protocolProbeStore";

const fakeResult = (): AgentProbeResult => ({
  agentId: "chrys",
  agentLabel: "iCode",
  depth: "safe",
  startedAt: "2026-01-01T00:00:00.000Z",
  elapsedMs: 12,
  ok: true,
  failedStep: null,
  failureReason: null,
  protocolVersion: 1,
  agentName: "chrys",
  agentVersion: "0.30.0",
  capabilities: {},
  models: null,
  modes: null,
  list: { status: "ok", count: 0 },
  closeAck: true,
  events: { eventTypeCounts: {}, toolKindCounts: {}, rawMethodCounts: {} },
  permissionRequests: 0,
  questionRequests: 0,
  prompts: [],
});

describe("protocolProbeStore", () => {
  beforeEach(() => {
    useProtocolProbeStore.getState().reset();
  });

  it("初始为 idle 且无结果；begin 进入 probing 并带起步步骤", () => {
    expect(useProtocolProbeStore.getState().phase).toBe("idle");
    useProtocolProbeStore.getState().begin("chrys");
    const state = useProtocolProbeStore.getState();
    expect(state.phase).toBe("probing");
    expect(state.step).toBe("启动进程");
    expect(state.probingAgentId).toBe("chrys");
    expect(state.result).toBeNull();
    expect(state.resultsByAgent).toEqual({});
  });

  it("setStep 更新进度；finish 落结果并按 agent 记忆结论；reset 全清", () => {
    const store = useProtocolProbeStore.getState();
    store.begin("chrys");
    useProtocolProbeStore.getState().setStep("握手 initialize");
    expect(useProtocolProbeStore.getState().step).toBe("握手 initialize");

    const result = fakeResult();
    useProtocolProbeStore.getState().finish(result);
    const done = useProtocolProbeStore.getState();
    expect(done.phase).toBe("done");
    expect(done.step).toBeNull();
    expect(done.probingAgentId).toBeNull();
    expect(done.result).toBe(result);
    // 按 agentId 记忆：列表行摘要的数据源
    expect(done.resultsByAgent["chrys"]).toBe(result);

    done.reset();
    const cleared = useProtocolProbeStore.getState();
    expect(cleared.phase).toBe("idle");
    expect(cleared.result).toBeNull();
    expect(cleared.resultsByAgent).toEqual({});
  });
});
