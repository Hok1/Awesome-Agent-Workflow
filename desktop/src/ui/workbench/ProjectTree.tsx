import { pathKey } from "../../core/panelPaths.ts";
import {
  useSessionActivityStore,
  sessionActivityKey,
} from "../../stores/sessionActivityStore.ts";
/**
 * 左栏（展开态）：列表头（标题 +【+】+ 视角菜单）+ 树体（双视角），
 * 结构对齐 ZCode project-sidebar（列表头 ProjectSidebarListHeader / 分区
 * WorkspacePurposeSection / 行 TaskListItem & ProjectNodeContent / 菜单
 * context-menu 的 desktop 等位）。
 *
 * 两个视角（切换经 workbenchUiStore 持久化，入口在列表头「切换视角」菜单，
 * radio 单选语义）：
 * - 「项目」：收藏 / 最近打开两组项目节点；项目行 = folder 图标（收起
 *   合口 / 展开开口双态）+ 目录名 + 行尾健康徽标与连接状态点（仅已连接 /
 *   连接中 / 连接失败时出现）；右键 / 键盘 ContextMenu 键弹项目菜单
 *   （新建会话 / 收藏·取消收藏 / 从列表移除——原行尾常驻星与 ✕ 收进菜单，
 *   对齐 ZCode TaskActionMenu 的「动作收进菜单」形态）；展开 chevron 不
 *   常驻——悬停行时浮现在行尾，双击整行切换收起 / 展开；单击项目名仍是
 *   进总览；
 *   会话子行整块缩进，仅标题 + 前导活动徽标 / 随行徽标，分页呈现（默认
 *   最近 SESSION_LIST_PAGE_SIZE 条，「加载更多」逐页纳新，见 ProjectChildren），
 *   末尾常驻「＋ 新会话」灰行——**空项目也有**，否则新加的项目在树上
 *   没有任何发起对话的入口；
 * - 「会话」：跨项目的「最近活跃会话」扁平列表（sessionsByPath 拍平，
 *   按 updatedAt 降序），两行卡显示会话标题 + 所属项目目录名（不显示
 *   时间，#196 定案）。
 *
 * 会话子节点的数据有两个来源，合在 sessionsByPath 一处（见 stores/
 * sessionStore 的 setSessions / mergeSessionHistory）：
 * - 已连接项目：ACP `session/list` 的权威快照；
 * - 未连接项目：agent 会话索引的补充（src/agents/chrysSessions.ts）。
 * 因此**冷启动就能看到历史**，不必先连上 agent——「连上之后突然冒出一
 * 大堆会话」不再发生。
 *
 * 选中是「内容区正在显示谁」，全树**只有一个**（双焦点修复后的硬约束）：
 * - 会话视图 → 高亮的是那个会话行；项目行只算展开的父节点，不跟着亮；
 * - 总览 → 高亮的是项目行；此前活跃的会话行一并退光（activeSessionId
 *   不清，但高亮由 treeView 门控——「我在哪」只允许一个答案）；
 * - 点会话的瞬间目标行先以「打开中」高亮（乐观，sessionStore 的
 *   openingSessionId），连接落地后转正为聚焦高亮，失败随视图回滚熄灭。
 * 行选中态统一走 `rowSelectedClass`（accent 淡底 + 左缘竖条），
 * 与中性色的悬停态分属两套颜色语言（行悬停 = bg-surface-hover，ZCode
 * TaskListItem.tsx:577 同款）。
 *
 * 数据来自 workspaceStore（收藏 / 最近 / activePath / 健康报告）与
 * sessionStore（sessionsByPath 的各项目会话列表缓存）；本组件只做渲染
 * 与交互派发，连接编排经共享入口完成：
 * - 点项目名 → 选中该项目，内容区切到项目总览（在总览里决定是否开始会话）；
 * - 点会话子节点（两个视角同路）→ openSessionFromEntry：内容区**立即**
 *   切到会话视图（连接加载态即时回响），连接与历史加载在后台串行队列
 *   完成，失败回滚视图；
 * - 点「＋ 新会话」/ 右键菜单「新建会话」/【+】面板的项目行 →
 *   startNewSession：**真开一条空对话**（forceNew 跳过历史恢复）。见
 *   sessionStart 的说明；
 * - 「收起侧边栏」只在图标窄栏（IconRail）有一处入口，树头不再重复；
 *   「设置 / 诊断」入口同样在窄栏底部。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useWorkspaceStore } from "../../stores/workspaceStore.ts";
import { useSessionStore } from "../../stores/sessionStore.ts";
import {
  SESSION_LIST_PAGE_SIZE,
  useWorkbenchUiStore,
  type ContentView,
  type TreeViewMode,
} from "../../stores/workbenchUiStore.ts";
import { Badge, focusVisibleRing, rowSelectedClass } from "../controls.tsx";
import {
  ContextMenu,
  type ContextMenuEntry,
  type MenuPlacement,
} from "../ContextMenu.tsx";
import { ChevronDownIcon, ChevronRightIcon, ClockIcon, CornerDownRightIcon, FolderGlyph, ListFilterIcon, LoaderIcon, PlusIcon, StarFilledIcon, StarOutlineIcon, XIcon, EllipsisIcon, MessageCirclePlusIcon, WorkflowIcon } from "../icons.tsx";
import { basenameOf } from "../workspaces/workspaceText.ts";
import type { SessionSummary } from "../../stores/sessionStore.ts";
import AddProjectPanel from "./AddProjectPanel.tsx";
import { flattenRecentSessions, openSessionFromEntry } from "./sessionEntry.ts";
import { startNewSession } from "./sessionStart.ts";

/**
 * folder 图标（项目行前缀，Lucide 线性图形双态）：收起合口（folder）/
 * 展开开口（folder-open），同 ZCode 面板的用法；16px + subtle 洗色对齐
 * ZCode ProjectNodeContent（size-4 text-foreground-subtle）。
 */
function FolderIcon({ isExpanded }: { readonly isExpanded: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={true}
      className="h-4 w-4 shrink-0 text-ink-subtle"
    >
      {isExpanded ? (
        <path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2" />
      ) : (
        <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />
      )}
    </svg>
  );
}

/** 健康徽标：全部通过 ✓n/n；存在警告/失败 ⚠；无检查结果不显示。 */
function HealthBadge({ path }: { readonly path: string }) {
  const health = useWorkspaceStore((state) => state.health);
  if (health === null || health.path !== path) {
    return null;
  }
  const total = health.items.length;
  const passed = health.items.filter((item) => item.status === "pass").length;
  if (passed === total) {
    return (
      <Badge
        tone="ok"
        compact={true}
        title={`健康检查 ${passed}/${total} 项通过`}
      >
        <span className="font-mono">
          ✓{passed}/{total}
        </span>
      </Badge>
    );
  }
  return (
    <Badge tone="warn" compact={true} title="健康检查存在警告或失败项">
      ⚠
    </Badge>
  );
}

/** 侧栏单例菜单的宿主接口：行组件经它开菜单，状态收在树根（ZCode 列表级
 *  单例 TaskList.tsx:121-128 的同位——同一时刻只有一个菜单）。 */
interface SidebarMenuApi {
  /** 指针右键：clientX/Y 即锚点（菜单左上角候选位，碰撞避让后定稿）。 */
  openAtPointer: (
    x: number,
    y: number,
    label: string,
    entries: readonly ContextMenuEntry[],
  ) => void;
  /** 键盘 ContextMenu/Shift+F10：行矩形右缘为锚点（ beside 行弹出）。 */
  openAtRect: (
    rect: DOMRect,
    label: string,
    entries: readonly ContextMenuEntry[],
  ) => void;
  dismiss: () => void;
}

/** 单例菜单的现场（id 区分视角菜单 / 行菜单；closing 驱动退场动画）。 */
interface SidebarMenuState {
  id: string;
  label: string;
  entries: readonly ContextMenuEntry[];
  placement: MenuPlacement;
  closing: boolean;
}

/** 退场动画时长（与 index.css 的 .context-menu-out 同拍）。 */
const MENU_CLOSE_MS = 100;

/**
 * 树根的单例菜单控制器：open 即换现场（右键另一行时旧菜单直接换内容，
 * 不闪两拍）；dismiss 置 closing 播退场，100ms 后卸载（setTimeout 主
 * 路径，jsdom 无动画也能收口）。
 */
function useSidebarMenuController(): {
  menu: SidebarMenuState | null;
  api: SidebarMenuApi;
  open: (
    id: string,
    label: string,
    entries: readonly ContextMenuEntry[],
    placement: MenuPlacement,
  ) => void;
} {
  const [menu, setMenu] = useState<SidebarMenuState | null>(null);
  const closeTimerRef = useRef<number | null>(null);

  const open = useCallback(
    (
      id: string,
      label: string,
      entries: readonly ContextMenuEntry[],
      placement: MenuPlacement,
    ) => {
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
      setMenu({ id, label, entries, placement, closing: false });
    },
    [],
  );

  const dismiss = useCallback(() => {
    setMenu((current) =>
      current === null || current.closing
        ? current
        : { ...current, closing: true },
    );
    if (closeTimerRef.current === null) {
      closeTimerRef.current = window.setTimeout(() => {
        closeTimerRef.current = null;
        setMenu(null);
      }, MENU_CLOSE_MS);
    }
  }, []);

  // 卸载时清掉挂起的退场计时器（热重载 / 视图切换不悬挂回调）
  useEffect(
    () => () => {
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
      }
    },
    [],
  );

  const api = useMemo<SidebarMenuApi>(
    () => ({
      openAtPointer: (x, y, label, entries) => {
        open(`row:${label}`, label, entries, { x, y, side: "bottom" });
      },
      openAtRect: (rect, label, entries) => {
        open(`row:${label}`, label, entries, {
          x: rect.right,
          y: rect.bottom + 4,
          side: "bottom",
        });
      },
      dismiss,
    }),
    [open, dismiss],
  );

  return { menu, api, open };
}

/** 键盘合成右键（ContextMenu 键 / Shift+F10，ZCode 行键控同款）。 */
function isContextMenuKey(event: { key: string; shiftKey: boolean }): boolean {
  return event.key === "ContextMenu" || (event.shiftKey && event.key === "F10");
}

/**
 * 项目节点的一行：folder（双态图标）+ 目录名 + 行尾徽标与 chevron；
 * 收藏 / 移除收进右键菜单（ZCode TaskActionMenu 形态）；展开 chevron
 * 悬停浮现在行尾，双击整行切换收起 / 展开。
 */
function ProjectNodeRow({
  path,
  isFavorite,
  isExpanded,
  isSelected,
  menu,
}: {
  readonly path: string;
  readonly isFavorite: boolean;
  readonly isExpanded: boolean;
  readonly isSelected: boolean;
  readonly menu: SidebarMenuApi;
}) {
  const selectWorkspace = useWorkspaceStore((state) => state.selectWorkspace);
  const toggleFavorite = useWorkspaceStore((state) => state.toggleFavorite);
  const removeFromRecent = useWorkspaceStore((state) => state.removeFromRecent);
  const toggleExpanded = useWorkbenchUiStore((state) => state.toggleExpanded);
  const openProjectOverview = useWorkbenchUiStore(
    (state) => state.openProjectOverview,
  );
  const clearContextIf = useWorkbenchUiStore((state) => state.clearContextIf);
  const name = basenameOf(path);

  // 菜单条目与原行尾按钮逐字同源（toggleFavorite/removeFromRecent/
  // clearContextIf），数据流不动
  function buildEntries(): ContextMenuEntry[] {
    return [
      {
        id: "new-session",
        label: "新建会话",
        icon: <PlusIcon className="h-4 w-4" />,
        onSelect: () => {
          void startNewSession(path);
        },
      },
      { type: "separator" },
      {
        id: "favorite",
        label: isFavorite ? "取消收藏" : "收藏",
        icon: isFavorite ? (
          <StarFilledIcon className="h-4 w-4" />
        ) : (
          <StarOutlineIcon className="h-4 w-4" />
        ),
        onSelect: () => {
          toggleFavorite(path);
        },
      },
      {
        id: "remove",
        label: "从列表移除",
        icon: <XIcon className="h-4 w-4" />,
        danger: true,
        onSelect: () => {
          removeFromRecent(path);
          // 内容区停留在被移除项目时回落空态（store 不互相 import，
          // 这条组装在组件层完成）
          clearContextIf(path);
        },
      },
    ];
  }

  return (
    <div
      onContextMenu={(event) => {
        event.preventDefault();
        menu.openAtPointer(
          event.clientX,
          event.clientY,
          "项目菜单",
          buildEntries(),
        );
      }}
      onKeyDown={(event) => {
        if (isContextMenuKey(event)) {
          event.preventDefault();
          menu.openAtRect(
            event.currentTarget.getBoundingClientRect(),
            "项目菜单",
            buildEntries(),
          );
        }
      }}
      className={`group ml-2 flex h-8 min-w-0 items-center gap-1 rounded-lg pr-1 transition-colors ${
        isSelected ? rowSelectedClass : "hover:bg-surface-hover"
      }`}
    >
      {/* 点项目名进总览（title=路径与【+】面板、测试的定位约定一致） */}
      <button
        type="button"
        onClick={() => {
          toggleExpanded(path, isExpanded);
        }}
        aria-expanded={isExpanded}
        className={`flex h-8 min-w-0 flex-1 items-center justify-start gap-2 rounded-lg pl-2.5 pr-1 text-left ${focusVisibleRing}`}
        title={path}
      >
        <FolderIcon isExpanded={isExpanded} />
        <span className="min-w-0 flex-1 truncate text-ui-base text-ink-subtle transition-colors group-hover:text-ink">
          {name}
        </span>
      </button>
      <HealthBadge path={path} />
      {/* 行尾动作栏（ZCode project-actions 布局）：hover/键盘聚焦浮现，
          菜单开着时常显；新建会话与工作流是「打开该项目」的两个入口 */}
      <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100">
        <button
          type="button"
          aria-label="更多操作"
          title="更多操作"
          onClick={(event) => {
            event.stopPropagation();
            menu.openAtRect(
              event.currentTarget.getBoundingClientRect(),
              "项目菜单",
              buildEntries(),
            );
          }}
          className="rounded p-1 text-ink-soft transition-colors hover:bg-surface-hover hover:text-ink"
        >
          <EllipsisIcon className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          aria-label="新建会话"
          title="新建会话"
          onClick={(event) => {
            event.stopPropagation();
            void startNewSession(path);
          }}
          className="rounded p-1 text-ink-soft transition-colors hover:bg-surface-hover hover:text-ink"
        >
          <MessageCirclePlusIcon className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          aria-label="工作流"
          title="打开工作流"
          onClick={(event) => {
            event.stopPropagation();
            selectWorkspace(path);
            openProjectOverview(path);
          }}
          className="rounded p-1 text-ink-soft transition-colors hover:bg-surface-hover hover:text-ink"
        >
          <WorkflowIcon className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

/**
 * 会话行的「当前」判定（项目树叶子与会话视角行共用）：
 * 高亮 = 内容区正在显示**这个项目的会话视图**，且该行是当前聚焦或
 * 正在打开的目标。用 treeView 门控是双焦点修复的关键——离开会话视图
 * （如切到项目总览）后 activeSessionId 仍在，但会话行必须退光，全树
 * 只亮「内容区正在显示谁」：总览亮项目行，会话亮会话行，互斥。
 */
function useIsSessionActive(path: string, sessionId: string): boolean {
  const activeSessionId = useSessionStore((state) => state.activeSessionId);
  const openingSessionId = useSessionStore((state) => state.openingSessionId);
  const treeView = useWorkbenchUiStore((state) => state.treeView);
  const contextPath = useWorkbenchUiStore((state) => state.contextPath);
  return (
    treeView === "session" &&
    pathKey(contextPath ?? "") === pathKey(path) &&
    (sessionId === activeSessionId || sessionId === openingSessionId)
  );
}

/**
 * 会话活动状态的前导徽标（ZCode TaskListItem 前导槽，优先级
 * error > unread > loading）：失败红点 > 已完成未读蓝点 > 运行 spinner。
 */
function SessionLeadingBadge({
  path,
  id,
}: {
  readonly path: string;
  readonly id: string;
}) {
  const activity = useSessionActivityStore(
    (state) => state.entries[sessionActivityKey(path, id)],
  );
  if (!activity || activity.status === "idle") {
    return null;
  }
  if (activity.status === "failed") {
    return (
      <span
        role="img"
        aria-label="失败"
        title="失败"
        className="h-1.5 w-1.5 shrink-0 rounded-full bg-danger"
      />
    );
  }
  if (activity.status === "completed") {
    return activity.unread ? (
      <span
        role="img"
        aria-label="已完成，未查看"
        title="已完成，未查看"
        className="size-[7px] shrink-0 rounded-full bg-icon-blue"
      />
    ) : null;
  }
  if (activity.status === "running") {
    return (
      <span
        role="img"
        aria-label="运行中"
        title="运行中"
        className="flex size-4 items-center justify-center"
      >
        <LoaderIcon className="h-4 w-4 shrink-0 animate-spin text-ink-subtle" />
      </span>
    );
  }
  return null;
}

/** 会话活动状态的随行徽标：待处理胶囊 / 已停止灰字（ZCode attention
 *  胶囊 h-5 rounded-full px-2 同款；cancelled 是 desktop 独有态，不造
 *  新视觉，保留信息）。 */
function SessionTrailingBadge({
  path,
  id,
}: {
  readonly path: string;
  readonly id: string;
}) {
  const activity = useSessionActivityStore(
    (state) => state.entries[sessionActivityKey(path, id)],
  );
  if (!activity || activity.status === "idle") {
    return null;
  }
  if (activity.status === "waiting") {
    return (
      <span className="inline-flex h-5 shrink-0 items-center rounded-full bg-interaction-confirmation-surface px-2 text-ui-sm font-medium text-ok-ink">
        待处理
      </span>
    );
  }
  if (activity.status === "cancelled") {
    return <span className="shrink-0 text-ui-sm text-ink-mute">已停止</span>;
  }
  return null;
}

/** 会话视角两行卡副行的随行徽标（前导/随行合一的紧凑版）。 */
function SessionActivityBadge({
  path,
  id,
}: {
  readonly path: string;
  readonly id: string;
}) {
  const activity = useSessionActivityStore(
    (state) => state.entries[sessionActivityKey(path, id)],
  );
  if (!activity || activity.status === "idle") {
    return null;
  }
  if (activity.status === "failed") {
    return (
      <span
        role="img"
        aria-label="失败"
        title="失败"
        className="h-1.5 w-1.5 shrink-0 rounded-full bg-danger"
      />
    );
  }
  if (activity.status === "completed") {
    return activity.unread ? (
      <span
        role="img"
        aria-label="已完成，未查看"
        title="已完成，未查看"
        className="size-[7px] shrink-0 rounded-full bg-icon-blue"
      />
    ) : null;
  }
  if (activity.status === "running") {
    return (
      <span
        role="img"
        aria-label="运行中"
        title="运行中"
        className="flex size-4 items-center justify-center"
      >
        <LoaderIcon className="h-3.5 w-3.5 shrink-0 animate-spin text-ink-subtle" />
      </span>
    );
  }
  if (activity.status === "waiting") {
    return (
      <span className="inline-flex h-5 shrink-0 items-center rounded-full bg-interaction-confirmation-surface px-2 text-ui-sm font-medium text-ok-ink">
        待处理
      </span>
    );
  }
  return <span className="shrink-0 text-ui-sm text-ink-mute">已停止</span>;
}

/** 会话行右键菜单：打开会话（ZCode 会话行菜单的 desktop 有用子集）。 */
function buildSessionMenuEntries(
  path: string,
  session: SessionSummary,
): ContextMenuEntry[] {
  return [
    {
      id: "open",
      label: "打开会话",
      icon: <CornerDownRightIcon className="h-4 w-4" />,
      onSelect: () => {
        void openSessionFromEntry(path, session.id);
      },
    },
  ];
}

/** 会话子行（项目树视角的树叶子）：前导槽 + 标题 + 随行徽标，右键弹
 *  「打开会话」菜单。 */
function SessionNode({
  path,
  session,
  menu,
}: {
  readonly path: string;
  readonly session: SessionSummary;
  readonly menu: SidebarMenuApi;
}) {
  const isActive = useIsSessionActive(path, session.id);

  return (
    <li
      onContextMenu={(event) => {
        event.preventDefault();
        menu.openAtPointer(
          event.clientX,
          event.clientY,
          "会话菜单",
          buildSessionMenuEntries(path, session),
        );
      }}
      onKeyDown={(event) => {
        if (isContextMenuKey(event)) {
          event.preventDefault();
          menu.openAtRect(
            event.currentTarget.getBoundingClientRect(),
            "会话菜单",
            buildSessionMenuEntries(path, session),
          );
        }
      }}
    >
      <button
        type="button"
        aria-current={isActive ? "true" : undefined}
        onClick={() => {
          void openSessionFromEntry(path, session.id);
        }}
        className={`flex w-full cursor-pointer items-center gap-2 rounded-lg py-1 pl-2.5 pr-1 text-left transition-[background-color,border-color,box-shadow] ${
          isActive ? rowSelectedClass : "hover:bg-surface-hover"
        } ${focusVisibleRing}`}
      >
        <span className="flex size-4 shrink-0 items-center justify-center">
          <SessionLeadingBadge path={path} id={session.id} />
        </span>
        <span className="min-w-0 flex-1 truncate text-ui-base text-ink">
          {session.title}
        </span>
        <SessionTrailingBadge path={path} id={session.id} />
      </button>
    </li>
  );
}

/** 单个项目子节点区（会话列表 + 「＋ 新会话」灰行）：缩进对照 ZCode
 *  ProjectNodeContent.tsx:394-395 的 CollapsibleContent——仅 pl-2 pt-1，
 *  行背景起于 8px，与项目名称保持对齐（旧任务 34px 缩进外只需 8px 留白）。 */
function ProjectChildren({
  path,
  sessions,
  menu,
}: {
  readonly path: string;
  readonly sessions: readonly SessionSummary[];
  readonly menu: SidebarMenuApi;
}) {
  // 分页呈现：默认最近 SESSION_LIST_PAGE_SIZE 条，「加载更多」逐页纳新；
  // 只裁显示不裁数据——store 仍持有全量列表，连接回填不受影响
  const limit = useWorkbenchUiStore(
    (state) => state.sessionListLimits[path] ?? SESSION_LIST_PAGE_SIZE,
  );
  const expandSessionList = useWorkbenchUiStore(
    (state) => state.expandSessionList,
  );
  const visible = sessions.slice(0, limit);
  const hiddenCount = sessions.length - visible.length;

  return (
    <ul className="flex flex-col gap-0.5 pl-2 pt-1">
      {visible.map((session) => (
        <SessionNode
          key={session.id}
          path={path}
          session={session}
          menu={menu}
        />
      ))}
      {hiddenCount > 0 ? (
        <li>
          <button
            type="button"
            aria-label={`加载更多会话（还有 ${hiddenCount} 条）`}
            onClick={() => {
              expandSessionList(path);
            }}
            // ZCode ProjectTaskRows.tsx:174-175：show-more 是无底色文本钮，
            // 仅交互时提亮（focus-visible），不做全宽圆角行悬停；
            // ml-8.5 让文字与会话标题文字位对齐（pl-2 + 槽 16 + gap 8 + pl-2.5 = 42px）
            className={`ml-8.5 flex h-auto items-center p-0 text-left text-ui-base text-ink-subtlest focus-visible:text-ink ${focusVisibleRing}`}
          >
            加载更多 · 还有 {hiddenCount} 条
          </button>
        </li>
      ) : null}
      <li>
      </li>
    </ul>
  );
}

/** 分组标题行尾的【+】（ZCode PurposeSections.tsx:122-137：新建入口住在
 *  各分区标题行尾，不在列表头）。两个分组共用同一面板与 store 开关，
 *  点击时把触发器登记进共享 ref（面板的外部点击判定要排除它）。 */
function SectionAddButton({
  triggerRef,
}: {
  readonly triggerRef: React.RefObject<HTMLButtonElement | null>;
}) {
  const isAddPanelOpen = useWorkbenchUiStore((state) => state.isAddPanelOpen);
  const toggleAddPanel = useWorkbenchUiStore((state) => state.toggleAddPanel);
  return (
    <button
      type="button"
      aria-label="新建会话或添加项目"
      aria-haspopup="true"
      aria-expanded={isAddPanelOpen}
      title="新建会话或添加项目"
      onClick={(event) => {
        triggerRef.current = event.currentTarget;
        toggleAddPanel();
      }}
      className={TREE_HEADER_BUTTON_CLASS}
    >
      <PlusIcon className="h-3.5 w-3.5" />
    </button>
  );
}

/** 树的一个分组（收藏 / 最近打开）：分组头对照 ZCode
 *  WorkspacePurposeSection.tsx:97-114——标题钮带 hover 显现的折叠
 *  chevron（点击收起/展开本组），行尾动作位 hover 显现、面板展开时
 *  常显（has-[[aria-expanded=true]]）。分组头恒在（空组只空行，
 *  ZCode 分区结构同样不随内容消失）。 */
function TreeSection({
  title,
  action,
  children,
}: {
  readonly title: string;
  readonly action?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  return (
    <section aria-label={title} className="group/section min-w-0">
      <div className="ml-2 mr-1 flex h-7 min-w-0 items-center">
        <button
          type="button"
          aria-expanded={!isCollapsed}
          onClick={() => {
            setIsCollapsed((value) => !value);
          }}
          className={`flex h-7 min-w-0 flex-1 items-center gap-1 px-2.5 text-left text-ui-base font-medium text-ink-subtlest outline-none transition-colors hover:text-ink focus-visible:text-ink ${focusVisibleRing}`}
        >
          <span className="min-w-0 truncate">{title}</span>
          {isCollapsed ? (
            <ChevronRightIcon className="h-3.5 w-3.5 shrink-0 opacity-0 transition-opacity group-hover/section:opacity-100 group-focus-within/section:opacity-100 [@media(hover:none)]:opacity-100" />
          ) : (
            <ChevronDownIcon className="h-3.5 w-3.5 shrink-0 opacity-0 transition-opacity group-hover/section:opacity-100 group-focus-within/section:opacity-100 [@media(hover:none)]:opacity-100" />
          )}
        </button>
        <div className="flex shrink-0 items-center opacity-0 transition-opacity group-hover/section:opacity-100 group-focus-within/section:opacity-100 has-[[aria-expanded=true]]:opacity-100 [@media(hover:none)]:opacity-100">
          {action}
        </div>
      </div>
      {!isCollapsed ? (
        <ul className="flex flex-col gap-0.5">{children}</ul>
      ) : null}
    </section>
  );
}

/** 项目视角：收藏 / 最近打开两组项目节点。分组头（含【+】动作位）恒在，
 *  新建面板挂树体顶部（ZCode 列表区形态：列表头只有标题与视角菜单，
 *  新建入口在各分组标题行尾）。 */
function ProjectsView({
  treeView,
  menu,
}: {
  readonly treeView: ContentView;
  readonly menu: SidebarMenuApi;
}) {
  const recentWorkspaces = useWorkspaceStore((state) => state.recentWorkspaces);
  const favoritePaths = useWorkspaceStore((state) => state.favoritePaths);
  const sessionsByPath = useSessionStore((state) => state.sessionsByPath);
  const contextPath = useWorkbenchUiStore((state) => state.contextPath);
  const expandedOverrides = useWorkbenchUiStore(
    (state) => state.expandedOverrides,
  );
  const isAddPanelOpen = useWorkbenchUiStore((state) => state.isAddPanelOpen);
  const closeAddPanel = useWorkbenchUiStore((state) => state.closeAddPanel);
  const addTriggerRef = useRef<HTMLButtonElement | null>(null);

  const lastOpenedByPath = new Map(
    recentWorkspaces.map((entry) => [entry.path, entry.lastOpenedAt] as const),
  );
  const favorites = favoritePaths.map((path) => ({
    path,
    lastOpenedAt: lastOpenedByPath.get(path) ?? null,
  }));
  const recentOnly = recentWorkspaces.filter(
    (entry) => !favoritePaths.includes(entry.path),
  );
  const knownProjects = [...favorites, ...recentOnly];

  function renderProject(path: string, isFavorite: boolean): React.ReactNode {
    const sessions =
      sessionsByPath[path] ??
      Object.entries(sessionsByPath).find(
        ([key]) => pathKey(key) === pathKey(path),
      )?.[1] ??
      [];
    // 默认展开有会话的项目；用户显式切换过则以切换值为准。
    // 无会话不再等于不可展开：子区域里有「＋ 新会话」，那是新项目的唯一
    // 起步入口，藏起来等于这个项目在树上无处可动。
    const isExpanded = expandedOverrides[path] ?? sessions.length > 0;
    // 选中是「内容区正在显示谁」，全树只有一个：
    // - 会话视图 → 高亮的是那个会话行（项目行只算展开的父节点）；
    // - 总览 → 高亮的是项目行。
    // 两者同时亮会让「当前在这」变成两个答案，且相邻两块底色叠在一起。
    const isSelected =
      pathKey(contextPath ?? "") === pathKey(path) && treeView !== "session";
    return (
      <li key={`${isFavorite ? "fav" : "recent"}-${path}`}>
        <ProjectNodeRow
          path={path}
          isFavorite={isFavorite}
          isExpanded={isExpanded}
          isSelected={isSelected}
          menu={menu}
        />
        {isExpanded ? (
          <ProjectChildren path={path} sessions={sessions} menu={menu} />
        ) : null}
      </li>
    );
  }

  return (
    <div className="relative flex flex-col gap-3">
      {/* 新建面板：零高绝对定位壳挂树体顶部，面板从列表顶端下探
          （触发器在各分组标题行尾，壳与分组头同宽） */}
      {isAddPanelOpen && (
        <div className="absolute inset-x-0 top-0 z-40">
          <AddProjectPanel onClose={closeAddPanel} triggerRef={addTriggerRef} />
        </div>
      )}
      <TreeSection
        title="收藏"
        action={<SectionAddButton triggerRef={addTriggerRef} />}
      >
        {favorites.length === 0
          ? null
          : favorites.map((entry) => renderProject(entry.path, true))}
      </TreeSection>

      <TreeSection
        title="最近打开"
        action={<SectionAddButton triggerRef={addTriggerRef} />}
      >
        {recentOnly.length === 0
          ? null
          : recentOnly.map((entry) => renderProject(entry.path, false))}
      </TreeSection>

      {/* 冷启动空态：分组头自带的【+】是唯一添加入口，树体补一行指引 */}
      {knownProjects.length === 0 ? (
        <p className="px-2.5 py-2 text-ui-base leading-relaxed text-ink-subtlest">
          还没有项目，点分组标题行的 ＋ 添加
        </p>
      ) : null}
    </div>
  );
}

/** 会话视角的一行（两行卡）：会话标题 + 副行（所属项目目录名 + 活动徽标）；
 *  不显示时间（#196 定案）。 */
function RecentSessionRow({
  path,
  session,
  menu,
}: {
  readonly path: string;
  readonly session: SessionSummary;
  readonly menu: SidebarMenuApi;
}) {
  const isActive = useIsSessionActive(path, session.id);

  return (
    <li
      onContextMenu={(event) => {
        event.preventDefault();
        menu.openAtPointer(
          event.clientX,
          event.clientY,
          "会话菜单",
          buildSessionMenuEntries(path, session),
        );
      }}
      onKeyDown={(event) => {
        if (isContextMenuKey(event)) {
          event.preventDefault();
          menu.openAtRect(
            event.currentTarget.getBoundingClientRect(),
            "会话菜单",
            buildSessionMenuEntries(path, session),
          );
        }
      }}
    >
      <button
        type="button"
        aria-current={isActive ? "true" : undefined}
        title={path}
        onClick={() => {
          void openSessionFromEntry(path, session.id);
        }}
        // 行体对照 ZCode TaskListItem.tsx:570-574：pl-2.5 pr-1，timeline
        // 两行变体 py-1.5（左 10px / 右 4px / 上下 6px）
        className={`flex w-full flex-col gap-0.5 rounded-lg py-1.5 pl-2.5 pr-1 text-left transition-colors ${
          isActive ? rowSelectedClass : "hover:bg-surface-hover"
        } ${focusVisibleRing}`}
      >
        <span className="min-w-0 truncate text-ui-base text-ink">
          {session.title}
        </span>
        {/* 副行对照 ZCode TaskListItem.tsx:668：text-ui-base 定高 h-6 */}
        <div className="flex h-6 items-center gap-1.5 text-ui-base text-ink-subtle">
          <CornerDownRightIcon className="h-3.5 w-3.5 shrink-0" />
          <span className="min-w-0 flex-1 truncate">{basenameOf(path)}</span>
          <SessionActivityBadge path={path} id={session.id} />
        </div>
      </button>
    </li>
  );
}

/** 会话视角：跨项目的「最近活跃会话」扁平列表（updatedAt 降序）。 */
function SessionsView({ menu }: { readonly menu: SidebarMenuApi }) {
  const sessionsByPath = useSessionStore((state) => state.sessionsByPath);
  const entries = flattenRecentSessions(sessionsByPath);

  if (entries.length === 0) {
    // 空态给行动出口：会话记录只会因「进过项目」而产生，这里指向项目视角
    return (
      <div className="flex flex-col items-center gap-2 px-2 py-6 text-center">
        <p className="text-ui-base leading-relaxed text-ink-subtlest">
          暂无会话记录。
          <br />
          进入任意项目发起一次对话，这里会按最近活跃排序。
        </p>
        <button
          type="button"
          onClick={() => {
            useWorkbenchUiStore.getState().setTreeViewMode("projects");
          }}
          className="rounded-md border border-line-strong px-2 py-1 text-xs text-ink-mute transition-colors hover:bg-raised hover:text-ink"
        >
          去项目列表
        </button>
      </div>
    );
  }
  return (
    <nav aria-label="最近活跃会话">
      <ul className="flex flex-col gap-0.5">
        {entries.map((entry) => (
          <RecentSessionRow
            key={`${entry.path}-${entry.session.id}`}
            path={entry.path}
            session={entry.session}
            menu={menu}
          />
        ))}
      </ul>
    </nav>
  );
}

/**
 * 树头部/分组头的小方钮（视角菜单、【+】动作位共用）。
 */
const TREE_HEADER_BUTTON_CLASS = `flex size-6 shrink-0 items-center justify-center rounded-md text-ink-subtle transition-colors hover:bg-hover hover:text-ink ${focusVisibleRing}`;

/**
 * 列表头（ZCode ProjectSidebarListHeader 形态）：标题 + 视角菜单。ZCode
 * 列表头只有搜索与视角菜单，搜索钮因 desktop 无 ⌘K 中枢省略；新建【+】
 * 不住列表头——住各分组标题行尾（SectionAddButton / TreeSection 动作位）。
 */
function ListHeader({
  treeViewMode,
  viewMenuOpen,
  onToggleViewMenu,
}: {
  readonly treeViewMode: TreeViewMode;
  readonly viewMenuOpen: boolean;
  readonly onToggleViewMenu: (anchor: DOMRect) => void;
}) {
  return (
    <div
      data-testid="sidebar-list-header"
      className="flex min-w-0 shrink-0 items-center gap-1 px-2 pb-2"
    >
      <span className="min-w-0 flex-1 truncate px-2.5 text-ui-base font-medium text-ink-subtle">
        {treeViewMode === "projects" ? "项目" : "最近会话"}
      </span>
      <button
        type="button"
        aria-label="切换视角"
        aria-haspopup="menu"
        aria-expanded={viewMenuOpen}
        title="切换视角"
        onClick={(event) => {
          onToggleViewMenu(event.currentTarget.getBoundingClientRect());
        }}
        className={TREE_HEADER_BUTTON_CLASS}
      >
        <ListFilterIcon className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

/** 左栏（树列）：列表头（标题 +【+】+ 视角菜单）+ 树体（双视角）+
 *  单例右键/下拉菜单。 */
export function ProjectTree() {
  const treeViewMode = useWorkbenchUiStore((state) => state.treeViewMode);
  const setTreeViewMode = useWorkbenchUiStore((state) => state.setTreeViewMode);
  // 内容区当前视图：决定树的选中落点是项目行还是会话行（见文件头说明）
  const treeView = useWorkbenchUiStore((state) => state.treeView);
  const { menu, api, open } = useSidebarMenuController();

  const viewMenuOpen = menu !== null && menu.id === "view-menu";

  const openViewMenu = useCallback(
    (anchor: DOMRect) => {
      // 视角切换菜单（ZCode radio 组形态：当前视角打勾）
      const entries: ContextMenuEntry[] = [
        {
          id: "projects",
          label: "项目",
          radio: true,
          selected: treeViewMode === "projects",
          icon: (
            <FolderGlyph
              isExpanded={false}
              className="h-4 w-4 text-ink-subtle"
            />
          ),
          onSelect: () => {
            setTreeViewMode("projects");
          },
        },
        {
          id: "sessions",
          label: "最近会话",
          radio: true,
          selected: treeViewMode === "sessions",
          icon: <ClockIcon className="h-4 w-4 text-ink-subtle" />,
          onSelect: () => {
            setTreeViewMode("sessions");
          },
        },
      ];
      open("view-menu", "切换视角", entries, {
        x: anchor.right,
        y: anchor.bottom + 4,
        side: "bottom",
        // ZCode ProjectSidebarListHeader 的 DropdownMenuContent align="end"：
        // 菜单右缘对齐触发器右缘
        align: "end",
      });
    },
    [open, setTreeViewMode, treeViewMode],
  );

  const toggleViewMenu = useCallback(
    (anchor: DOMRect) => {
      // 触发器再点一次收起（pointerdown 已把菜单置 closing，这里只补一拍）
      if (viewMenuOpen) {
        api.dismiss();
        return;
      }
      openViewMenu(anchor);
    },
    [api, openViewMenu, viewMenuOpen],
  );

  return (
    <aside
      aria-label="项目树"
      className="flex h-full min-h-0 flex-col overflow-hidden bg-sidebar"
    >
      {/* 顶部 48px 空区：ZCode 列表区的 h-12 拖拽带等位（纯构图对位，
          窗口拖拽仍由 ContextBar 的 data-tauri-drag-region 承担） */}
      <div aria-hidden={true} className="h-12 shrink-0" />
      <div className="flex min-h-0 flex-1 flex-col border-t border-line/50 pt-3">
        <ListHeader
          treeViewMode={treeViewMode}
          viewMenuOpen={viewMenuOpen}
          onToggleViewMenu={toggleViewMenu}
        />
        {/* 树体：视角决定内容（项目树 / 跨项目最近会话）；
            仅纵向滚动 + overflow-clip 防焦点滚动（ZCode project-sidebar
            :224-225,:242-246 同因），横向溢出靠文本截断处理 */}
        <div className="relative min-h-0 flex-1 overflow-clip">
          <div className="h-full overflow-x-hidden overflow-y-auto">
            <div className="flex flex-col gap-3 pb-3">
              {treeViewMode === "projects" ? (
                <ProjectsView treeView={treeView} menu={api} />
              ) : (
                <SessionsView menu={api} />
              )}
            </div>
          </div>
        </div>
      </div>
      {/* 单例菜单（右键/下拉共用，portal 挂 body 不受 aside 裁剪） */}
      {menu !== null && (
        <ContextMenu
          entries={menu.entries}
          placement={menu.placement}
          label={menu.label}
          closing={menu.closing}
          onDismiss={api.dismiss}
        />
      )}
    </aside>
  );
}

export default ProjectTree;
