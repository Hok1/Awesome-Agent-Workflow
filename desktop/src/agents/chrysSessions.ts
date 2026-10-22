/**
 * chrys 历史会话的只读读取（src/agents 层）。
 *
 * 为什么需要它：会话列表今天只有一条来源——ACP 握手后的 `session/list`
 * （见 realRuntime.openRealWorkspace）。也就是说**必须先 spawn chrys、
 * 连上某个项目，那个项目的会话才会出现**：冷启动时树里每个项目都是空
 * 的，点进去才「突然」冒出历史。但这份数据本来就躺在磁盘上，读取它不
 * 需要 agent 进程。
 *
 * 数据源：chrys 的会话索引缓存 `<sessions>/.cache/session_catalog.json`
 * （chrys `service/state/session_catalog.py`）。每条记录带 `session_id` /
 * `kind` / `title` 系列 / `updated_at` / `primary_cwd`，正好是树要的字段。
 * 实测（本机 29 条会话）该缓存与磁盘上各会话目录的 `session.json` 集合
 * 零漂移。
 *
 * 它是**缓存，不是权威**，因此本模块的纪律：
 * - 版本号不匹配 / 形状不合 / 读不到 → 一律返回空，绝不猜；
 * - 返回空**不等于**「该项目没有会话」，只等于「这次没读到」——调用方
 *   不得据此覆盖已连接项目的权威列表（见 sessionHistory 组装层）；
 * - 缓存文件有大小上限保护（超限不解析），避免会话上千的机器拖慢启动；
 * - 只读 `kind === "chat"`：`workflow` 是 chrys 自己的工作流运行记录，
 *   不是本应用的对话会话（与 ACP `session/list` 的 kind 过滤一致）；
 * - 路径匹配只做字符串规范化（斜杠 / 大小写 / 尾斜杠），不要求目录存在
 *   ——树里本来就可能挂着已被删除的项目目录。
 */
import { createLogger } from "../core/logger.ts";
import type { HostRuntime } from "../core/host.ts";
import { joinPath } from "../core/host.ts";

const logger = createLogger("agent");

/** 会话索引缓存的相对位置（相对 chrys 会话目录）。 */
const CATALOG_RELATIVE_PATH = ".cache/session_catalog.json";

/** 缓存文件的解析上限：超过此长度不解析（防会话极多时拖慢启动）。 */
const CATALOG_MAX_BYTES = 2 * 1024 * 1024;

/** 受支持的缓存派生版本（chrys `CATALOG_DERIVATION_VERSION`）。 */
const SUPPORTED_CATALOG_VERSION = 1;

/** 一条已知会话（历史会话列表的渲染单元；与 store 的类型解耦）。 */
export interface KnownSession {
  readonly id: string;
  readonly title: string;
  /** 最近更新时间（ISO 8601）；缺失为 null。 */
  readonly updatedAt: string | null;
  /** 该会话绑定的项目目录（chrys 记录的原始字符串）。 */
  readonly cwd: string;
}

/**
 * 路径归一化：统一分隔符为 `/`、去掉尾斜杠、折叠大小写。
 * 只用于「catalog 里的 primary_cwd」与「项目列表里的路径」比对——两者
 * 来自不同来源（chrys 写入的原始串 vs 目录对话框返回值），分隔符与大小
 * 写都可能不一致；不要求路径真实存在（项目可能已被删）。
 */
export function normalizeSessionPath(path: string): string {
  return path.trim().replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

function asRecord(raw: unknown): Readonly<Record<string, unknown>> | null {
  return typeof raw === "object" && raw !== null && !Array.isArray(raw)
    ? (raw as Readonly<Record<string, unknown>>)
    : null;
}

function asNonEmptyString(raw: unknown): string | null {
  return typeof raw === "string" && raw.trim().length > 0 ? raw : null;
}

/** 展示标题：自定标题 > 生成的短标题 > 首条消息原文（chrys display_title 顺序）。 */
function pickTitle(meta: Readonly<Record<string, unknown>>): string {
  return (
    asNonEmptyString(meta["custom_title"]) ??
    asNonEmptyString(meta["generated_title"]) ??
    asNonEmptyString(meta["title"]) ??
    "会话"
  );
}

/**
 * 解析会话索引缓存 → 已知会话列表（按 cwd 归一化后分组）。
 *
 * 形状（chrys session_catalog.py）：
 * `{ version: 1, sessions: { "<shortId>": { signature, meta } } }`
 *
 * 失败一律返回空 Map（调用方据此只做「补充」，不做「清空」）。
 */
export function parseSessionCatalog(
  raw: unknown,
): ReadonlyMap<string, readonly KnownSession[]> {
  const grouped = new Map<string, KnownSession[]>();
  const record = asRecord(raw);
  if (record === null || record["version"] !== SUPPORTED_CATALOG_VERSION) {
    return grouped;
  }
  const sessions = asRecord(record["sessions"]);
  if (sessions === null) {
    return grouped;
  }
  for (const entry of Object.values(sessions)) {
    const wrapper = asRecord(entry);
    const meta = wrapper === null ? null : asRecord(wrapper["meta"]);
    if (meta === null) {
      continue;
    }
    if (meta["kind"] !== "chat") {
      continue;
    }
    const id = asNonEmptyString(meta["session_id"]);
    const cwd = asNonEmptyString(meta["primary_cwd"]);
    if (id === null || cwd === null) {
      continue;
    }
    const key = normalizeSessionPath(cwd);
    const list = grouped.get(key);
    const known: KnownSession = {
      id,
      title: pickTitle(meta),
      updatedAt: asNonEmptyString(meta["updated_at"]),
      cwd,
    };
    if (list === undefined) {
      grouped.set(key, [known]);
    } else {
      list.push(known);
    }
  }
  // 组内按 updatedAt 降序（缺失时间的条目排末尾；相同时保持稳定）
  for (const list of grouped.values()) {
    list.sort((a, b) => rankOf(b.updatedAt) - rankOf(a.updatedAt));
  }
  return grouped;
}

/** 排序时间戳：缺失或非法时间视为最旧。 */
function rankOf(updatedAt: string | null): number {
  if (updatedAt === null) {
    return Number.NEGATIVE_INFINITY;
  }
  const time = Date.parse(updatedAt);
  return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time;
}

/** 读取并解析会话索引缓存；任何失败（无宿主 / 读不到 / 不合版本）返回空。 */
export async function readSessionCatalog(
  host: HostRuntime,
): Promise<ReadonlyMap<string, readonly KnownSession[]>> {
  try {
    const sessionsDir = await host.chrysSessionsDir();
    if (typeof sessionsDir !== "string" || sessionsDir.trim() === "") {
      return new Map();
    }
    const catalogPath = joinPath(sessionsDir, CATALOG_RELATIVE_PATH);
    if (!(await host.pathExists(catalogPath))) {
      return new Map();
    }
    const text = await host.readTextFile(catalogPath);
    if (text.length > CATALOG_MAX_BYTES) {
      logger.warn("会话索引缓存过大，本次不解析", {
        path: catalogPath,
        length: text.length,
      });
      return new Map();
    }
    return parseSessionCatalog(JSON.parse(text) as unknown);
  } catch (error) {
    // 缓存不可读不是错误状态：树退回「没有历史可显示」的既有观感
    logger.info("会话索引缓存不可读，历史会话本次不补充", {
      reason: error instanceof Error ? error.message : String(error),
    });
    return new Map();
  }
}
