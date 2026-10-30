/**
 * 连接状态徽标（左栏树 / 上下文条 / 【+】面板的共享部件）：只在项目**有
 * 连接状态**时出现——已连接（绿点）/ 连接中（蓝点 spinner）/ 连接失败
 * （红点，title 带原因）。
 *
 * 「未连接」不渲染任何东西：列表里绝大多数项目都是未连接，逐行挂一个灰点
 * 只是把「没有状态」重复 N 遍，噪声盖过了真正有信息的那一行。没有徽标
 * 就等于未连接，需要显式说明的地方（如树行）由行本身的可点性承担。
 *
 * 两种形态：
 * - badge（默认）：点 + 文字的胶囊徽标（上下文条 / 【+】面板项目行），
 *   植面取自 controls 的 `Badge`（全站唯一徽标配方，语气选 tone）；
 * - dot：仅 6px 状态点，语义进 aria-label / title（项目树行尾）——点形态
 *   塞不进胶囊，直接画点。
 */
import { useSessionStore } from "../../stores/sessionStore.ts";
import { useWorkspaceStore } from "../../stores/workspaceStore.ts";
import { Badge, BadgeDot, Spinner } from "../controls.tsx";

export function ConnectionBadge({
  path,
  variant = "badge",
}: {
  readonly path: string;
  readonly variant?: "badge" | "dot";
}) {
  const activePath = useWorkspaceStore((state) => state.activePath);
  const isConnecting = useSessionStore((state) => state.isConnecting);
  const isBound = useSessionStore((state) => state.isBound);
  const connectError = useWorkspaceStore((state) => state.lastConnectError);

  const isConnectingThis = activePath === path && isConnecting;
  // 连接失败：仅当前打开的项目且失败记录匹配时呈现（title 带具体原因）
  const failure =
    connectError !== null &&
    connectError.path === path &&
    activePath === path &&
    !isConnecting
      ? connectError
      : null;
  const isConnected = activePath === path && !isConnecting && isBound;

  if (variant === "dot") {
    // 点色对齐 ZCode remoteConnectionPresentation.ts 的 TONES：进行中
    // bg-progress-ink（=--color-progress-surface-foreground blue-300/700）、
    // 已连接 bg-ok（=--color-success #46bf72/#1e8a3e）、失败 bg-danger
    // （=--color-destructive #ff5c5c/#e03131）。
    if (isConnectingThis) {
      return (
        <span
          aria-label="连接中"
          title="连接中"
          className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-progress-ink"
        />
      );
    }
    if (failure !== null) {
      return (
        <span
          aria-label="连接失败"
          title={`连接失败：${failure.message}`}
          className="h-1.5 w-1.5 shrink-0 rounded-full bg-danger"
        />
      );
    }
    if (isConnected) {
      return (
        <span
          aria-label="已连接"
          title="已连接，可继续对话"
          className="h-1.5 w-1.5 shrink-0 rounded-full bg-ok"
        />
      );
    }
    return null;
  }

  if (isConnectingThis) {
    return (
      <Badge tone="info">
        <Spinner className="h-2.5 w-2.5" />
        连接中
      </Badge>
    );
  }
  if (failure !== null) {
    return (
      <Badge tone="danger" title={`连接失败：${failure.message}`}>
        <BadgeDot />
        失败
      </Badge>
    );
  }
  if (isConnected) {
    return (
      <Badge tone="ok">
        <BadgeDot />
        已连接
      </Badge>
    );
  }
  return null;
}

export default ConnectionBadge;
