/**
 * 思考过程（agent_thought_chunk）：默认折叠，点击展开；流式中显示动点。
 */
import { useState } from "react";
import type { ThoughtItem } from "../../stores/sessionStore.ts";

export function ThoughtBlock({ item }: { readonly item: ThoughtItem }) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div className="w-full" data-item-kind="thought">
      <button
        type="button"
        aria-expanded={isOpen}
        onClick={() => {
          setIsOpen((current) => !current);
        }}
        className="flex items-center gap-2 text-xs text-ink-faint transition-colors hover:text-ink-soft"
      >
        <span
          className={`inline-block transition-transform ${isOpen ? "rotate-90" : ""}`}
        >
          ▸
        </span>
        <span>思考过程</span>
        {item.isStreaming ? (
          <span className="inline-block size-1.5 animate-pulse rounded-full bg-ink-faint" />
        ) : null}
      </button>
      {isOpen ? (
        <p className="mt-1.5 border-l-2 border-line pl-3 text-xs leading-6 whitespace-pre-wrap break-words text-ink-faint">
          {item.text}
        </p>
      ) : null}
    </div>
  );
}
