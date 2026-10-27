/**
 * 输入行状态芯片菜单（ZCode 输入栏控件式）：小芯片触发 + 弹在输入卡上方
 * 的轻量菜单（Esc / 点外部关闭；面板内点击选中后自动收起）。
 *
 * Esc 在此被消费（preventDefault）——SessionView 的全局 Esc 停止按
 * defaultPrevented 让位（与 mention 面板同一约定）。
 */
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

export function StatusChipMenu({
  label,
  title,
  menuLabel,
  tone = "neutral",
  disabled = false,
  children,
}: {
  /** 芯片文案（如「+」「模型名」「手动询问」）。 */
  readonly label: ReactNode;
  /** 芯片悬停提示。 */
  readonly title: string;
  /** 菜单面板的可访问名称。 */
  readonly menuLabel: string;
  /** neutral=中性描边；warn=琥珀警示（自动拒绝等危险态）。 */
  readonly tone?: "neutral" | "warn";
  /** 无内容可选时呈纯展示芯片（如无模型清单）。 */
  readonly disabled?: boolean;
  readonly children: ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    function handlePointerDown(event: PointerEvent): void {
      const root = rootRef.current;
      if (root !== null && !root.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    window.addEventListener("pointerdown", handlePointerDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [isOpen]);

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>): void => {
    if (event.nativeEvent.isComposing) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setIsOpen(false);
    }
  };

  const toneClass =
    tone === "warn"
      ? "border-warn-line bg-warn-bg/50 text-warn-ink"
      : "border-line-strong bg-surface text-ink-faint hover:border-ink-faint hover:text-ink-soft";

  if (disabled) {
    return (
      <span
        title={title}
        className="shrink-0 rounded border border-line-strong bg-surface px-1.5 py-0.5 text-2xs text-ink-faint"
      >
        {label}
      </span>
    );
  }
  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label={menuLabel}
        title={title}
        onClick={() => {
          setIsOpen((current) => !current);
        }}
        onKeyDown={handleKeyDown}
        className={`press flex items-center gap-1 rounded border px-1.5 py-0.5 text-2xs transition-colors ${toneClass} ${
          isOpen ? "border-ink-faint text-ink-soft" : ""
        }`}
      >
        {label}
      </button>
      {isOpen ? (
        <div
          role="menu"
          aria-label={menuLabel}
          // 面板内任何点击（选中某项）都收起菜单
          onClickCapture={() => {
            setIsOpen(false);
          }}
          className="absolute bottom-full left-0 z-30 mb-1.5 w-64 overflow-hidden rounded-xl border border-line-strong bg-surface shadow-elev-2"
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

/** 菜单分区标题。 */
export function MenuSectionLabel({ text }: { readonly text: string }) {
  return (
    <p className="border-b border-line px-3 py-1.5 text-2xs tracking-wide text-ink-ghost">
      {text}
    </p>
  );
}

/** 菜单条目（role=menuitem；选中态打勾）。 */
export function MenuItemButton({
  selected,
  onClick,
  children,
  danger = false,
}: {
  readonly selected: boolean;
  readonly onClick: () => void;
  readonly children: ReactNode;
  readonly danger?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={`flex w-full items-start gap-2 px-3 py-1.5 text-left text-xs transition-colors ${
        danger ? "text-danger-ink hover:bg-danger-bg/40" : "text-ink-soft hover:bg-raised/70"
      }`}
    >
      <span aria-hidden={true} className="w-3 shrink-0 text-ok-ink">
        {selected ? "✓" : ""}
      </span>
      <span className="min-w-0 flex-1 break-words">{children}</span>
    </button>
  );
}

/** 只读信息行（skills/mcp 清单等，不可选）。 */
export function MenuInfoRow({
  text,
  danger = false,
}: {
  readonly text: string;
  readonly danger?: boolean;
}) {
  return (
    <p
      className={`flex w-full items-start gap-2 px-3 py-1 text-left text-xs ${
        danger ? "text-danger-ink" : "text-ink-soft"
      }`}
    >
      <span aria-hidden={true} className="w-3 shrink-0" />
      <span className="min-w-0 flex-1 break-words">{text}</span>
    </p>
  );
}
