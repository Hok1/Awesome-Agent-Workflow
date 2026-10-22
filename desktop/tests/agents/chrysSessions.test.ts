/**
 * chrys 历史会话读取的测试（src/agents/chrysSessions）。
 *
 * 这一层是「树的会话子节点」在未连接项目下的数据来源，纪律比功能更重要：
 * 缓存不合版本 / 形状不对 / 读不到都只能返回空，且**返回空不等于没有
 * 会话**——调用方据此只做补充，不做清空。测试按这条边界组织。
 */
import { describe, expect, it } from "vitest";
import {
  normalizeSessionPath,
  parseSessionCatalog,
  readSessionCatalog,
} from "../../src/agents/chrysSessions";
import { createDemoHost } from "../../src/core/host";

/** 构造一条 catalog 记录（形状对齐 chrys session_catalog.py）。 */
function catalogRecord(overrides: {
  readonly sessionId: string;
  readonly cwd: string;
  readonly title?: string;
  readonly generatedTitle?: string;
  readonly customTitle?: string;
  readonly updatedAt?: string;
  readonly kind?: string;
}): unknown {
  return {
    signature: [1, 2, 3],
    meta: {
      kind: overrides.kind ?? "chat",
      session_id: overrides.sessionId,
      primary_cwd: overrides.cwd,
      updated_at: overrides.updatedAt ?? "2026-10-21T02:26:45.706988+00:00",
      title: overrides.title ?? "首条消息原文",
      custom_title: overrides.customTitle ?? "",
      generated_title: overrides.generatedTitle ?? "",
    },
  };
}

function catalogOf(records: readonly unknown[]): unknown {
  const sessions: Record<string, unknown> = {};
  records.forEach((record, index) => {
    sessions[`short${String(index)}`] = record;
  });
  return { version: 1, sessions };
}

describe("parseSessionCatalog", () => {
  it("按 primary_cwd 分组，标题优先取自定 > 生成 > 首条原文", () => {
    const grouped = parseSessionCatalog(
      catalogOf([
        catalogRecord({
          sessionId: "a",
          cwd: "D:\\dev\\demo",
          generatedTitle: "项目介绍",
        }),
        catalogRecord({
          sessionId: "b",
          cwd: "D:/dev/other",
          title: "统计文件数",
        }),
      ]),
    );
    const demo = grouped.get(normalizeSessionPath("D:/dev/demo"));
    expect(demo?.map((session) => session.id)).toEqual(["a"]);
    // generated_title 比首条消息原文好读，优先取它
    expect(demo?.[0]?.title).toBe("项目介绍");
    const other = grouped.get(normalizeSessionPath("D:/dev/other"));
    expect(other?.[0]?.title).toBe("统计文件数");
  });

  it("路径匹配容忍分隔符与大小写差异（项目可能已被删，不要求目录存在）", () => {
    const grouped = parseSessionCatalog(
      catalogOf([catalogRecord({ sessionId: "a", cwd: "D:\\DEV\\Demo\\" })]),
    );
    expect(grouped.get(normalizeSessionPath("d:/dev/demo"))).toHaveLength(1);
  });

  it("只收 kind=chat：workflow 是 chrys 自己的工作流运行记录，不是对话", () => {
    const grouped = parseSessionCatalog(
      catalogOf([
        catalogRecord({ sessionId: "chat-1", cwd: "D:/p" }),
        catalogRecord({ sessionId: "wf-1", cwd: "D:/p", kind: "workflow" }),
      ]),
    );
    expect(grouped.get(normalizeSessionPath("D:/p"))?.map((s) => s.id)).toEqual(
      ["chat-1"],
    );
  });

  it("组内按 updatedAt 降序（缺失时间的排末尾）", () => {
    const grouped = parseSessionCatalog(
      catalogOf([
        catalogRecord({
          sessionId: "old",
          cwd: "D:/p",
          updatedAt: "2026-01-01T00:00:00Z",
        }),
        catalogRecord({
          sessionId: "new",
          cwd: "D:/p",
          updatedAt: "2026-10-01T00:00:00Z",
        }),
        catalogRecord({ sessionId: "none", cwd: "D:/p", updatedAt: "" }),
      ]),
    );
    expect(grouped.get(normalizeSessionPath("D:/p"))?.map((s) => s.id)).toEqual(
      ["new", "old", "none"],
    );
  });

  it("版本不匹配 / 形状不合：返回空，绝不猜", () => {
    expect(parseSessionCatalog({ version: 2, sessions: {} }).size).toBe(0);
    expect(parseSessionCatalog({ sessions: {} }).size).toBe(0);
    expect(parseSessionCatalog(null).size).toBe(0);
    expect(parseSessionCatalog("不是对象").size).toBe(0);
    // 缺 session_id / primary_cwd 的记录整条丢弃
    const grouped = parseSessionCatalog(
      catalogOf([
        { signature: [], meta: { kind: "chat", primary_cwd: "D:/p" } },
        { signature: [], meta: { kind: "chat", session_id: "x" } },
      ]),
    );
    expect(grouped.size).toBe(0);
  });
});

describe("readSessionCatalog", () => {
  it("从会话目录读 .cache/session_catalog.json 并解析", async () => {
    const host = createDemoHost();
    host.setChrysSessionsDir("X:/chrys/sessions");
    await host.writeTextFile(
      "X:/chrys/sessions/.cache/session_catalog.json",
      JSON.stringify(
        catalogOf([catalogRecord({ sessionId: "a", cwd: "D:/dev/demo" })]),
      ),
    );

    const grouped = await readSessionCatalog(host);
    expect(grouped.get(normalizeSessionPath("D:/dev/demo"))).toHaveLength(1);
  });

  it("缓存不存在 / 不是合法 JSON：返回空（树退回既有观感，不报错）", async () => {
    const host = createDemoHost();
    host.setChrysSessionsDir("X:/chrys/sessions");
    expect((await readSessionCatalog(host)).size).toBe(0);

    await host.writeTextFile(
      "X:/chrys/sessions/.cache/session_catalog.json",
      "{ 这不是 JSON",
    );
    expect((await readSessionCatalog(host)).size).toBe(0);
  });

  it("缓存超过大小上限：不解析（防会话极多时拖慢启动）", async () => {
    const host = createDemoHost();
    host.setChrysSessionsDir("X:/chrys/sessions");
    await host.writeTextFile(
      "X:/chrys/sessions/.cache/session_catalog.json",
      JSON.stringify(
        catalogOf([catalogRecord({ sessionId: "a", cwd: "D:/dev/demo" })]),
      ).padEnd(3 * 1024 * 1024, " "),
    );
    expect((await readSessionCatalog(host)).size).toBe(0);
  });
});
