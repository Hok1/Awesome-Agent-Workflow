/**
 * Markdown 渲染：react-markdown + rehype-highlight（github-dark 主题，
 * 样式入口见 src/index.css）。
 *
 * 代码块（pre）重写为带「语言标签 + 复制按钮」头栏的容器；行内代码
 * 与代码块内的高亮 span 分别处理样式。
 */
import React, { memo, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import { CopyButton } from "./CopyButton.tsx";

/** 从 pre 的 children（code 元素树）里提取语言与纯文本。 */
function inspectCodeChildren(children: ReactNode): {
  language: string | null;
  text: string;
} {
  let language: string | null = null;
  let text = "";
  const visit = (node: ReactNode): void => {
    if (typeof node === "string" || typeof node === "number") {
      text += String(node);
      return;
    }
    if (Array.isArray(node)) {
      // Array.isArray 对宽松联合会收窄成 any[]，这里显式回到 ReactNode
      for (const child of node as readonly ReactNode[]) {
        visit(child);
      }
      return;
    }
    if (
      React.isValidElement<{ className?: unknown; children?: ReactNode }>(node)
    ) {
      const className = node.props.className;
      if (language === null && typeof className === "string") {
        const match = /language-([\w+-]+)/.exec(className);
        if (match !== null && match[1] !== undefined) {
          language = match[1];
        }
      }
      visit(node.props.children);
    }
  };
  visit(children);
  return { language, text };
}

/** 代码块外壳：头栏（语言 + 复制）+ 横向滚动的 pre。 */
function CodeBlockShell({ children }: { children?: ReactNode }) {
  const { language, text } = inspectCodeChildren(children);
  return (
    <div className="my-3 overflow-hidden rounded-lg border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3 py-1">
        <span className="font-mono text-xs text-ink-faint">
          {language ?? "text"}
        </span>
        <CopyButton getText={() => text} label="复制代码" />
      </div>
      <pre className="overflow-x-auto p-3 text-md leading-relaxed">
        {children}
      </pre>
    </div>
  );
}

const markdownComponents: Components = {
  pre: ({ children }) => <CodeBlockShell>{children}</CodeBlockShell>,
  code: ({ className, children }) => {
    const isBlock =
      typeof className === "string" && /(^|\s)(hljs|language-)/.test(className);
    if (isBlock) {
      return (
        <code className={`font-mono text-ink-soft ${className ?? ""}`}>
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-md text-ink-soft">
        {children}
      </code>
    );
  },
  p: ({ children }) => (
    <p className="my-2 leading-6 first:mt-0 last:mb-0">{children}</p>
  ),
  h1: ({ children }) => (
    <h1 className="mb-2 mt-4 text-lg font-semibold text-ink">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-4 text-base font-semibold text-ink">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-1.5 mt-3 text-sm font-semibold text-ink">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="mb-1.5 mt-3 text-sm font-medium text-ink">{children}</h4>
  ),
  ul: ({ children }) => (
    <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-6">{children}</li>,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-accent-ink hover:text-accent-ink-strong hover:underline"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-line-strong pl-3 text-ink-mute">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-line" />,
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-line bg-surface px-2.5 py-1.5 text-left font-medium">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-line px-2.5 py-1.5">{children}</td>
  ),
};

function MarkdownViewBase({ text }: { readonly text: string }) {
  return (
    // break-words：Windows 绝对路径 / URL 这类超长不可断 token 按字符折行，
    // 不把消息流撑出横向滚动（代码块自身的横向滚动不受影响：pre 的
    // whitespace: pre 优先，且它显式写了 overflow-x-auto）
    <div className="text-sm break-words text-ink">
      <ReactMarkdown
        rehypePlugins={[rehypeHighlight]}
        components={markdownComponents}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

/**
 * memo（按 text 浅比较）：文本不变则跳过整棵 Markdown 重解析——
 * react-markdown + rehype-highlight 是消息流里最贵的渲染路径，
 * 配合条目级引用稳定，历史消息在流式期间零重渲。
 */
export const MarkdownView = memo(MarkdownViewBase);
