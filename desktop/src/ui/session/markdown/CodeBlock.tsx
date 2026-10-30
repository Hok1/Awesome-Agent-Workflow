/**
 * 代码块 chrome(移植自 ZCode components/ai-elements/code-block.tsx 的
 * 头栏与动作按钮;高亮本体来自 streamdown 的 @streamdown/code 插件,
 * 这里只包壳:语言标签 + 换行切换 + 复制 + mermaid 分支与放大预览)。
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { CopyButton } from "../CopyButton.tsx";
import { useHintTooltip } from "../../controls/HintTooltip.tsx";
import { DiagramPreviewDialog } from "./DiagramPreviewDialog.tsx";
import { MermaidBlock } from "./MermaidBlock.tsx";
import {
  codeHashOf,
  isCodeVisible,
  markCodeVisibleAndFlush,
} from "./deferredCodePlugin.ts";
import {
  isMermaidLanguage,
  shouldRenderMermaidCodeBlock,
} from "./mermaidLanguage.ts";

/** 语言 → 示例文件名(ZCode 同款映射,让语言标签更像文件)。 */
const LANGUAGE_DISPLAY_FILE_BY_LANGUAGE: Record<string, string> = {
  bash: "script.sh",
  cjs: "index.cjs",
  css: "style.css",
  go: "main.go",
  html: "index.html",
  javascript: "index.js",
  js: "index.js",
  jsx: "component.jsx",
  json: "data.json",
  markdown: "README.md",
  md: "README.md",
  mermaid: "diagram.mmd",
  mmd: "diagram.mmd",
  mjs: "index.mjs",
  python: "main.py",
  py: "main.py",
  rs: "main.rs",
  rust: "main.rs",
  sh: "script.sh",
  shell: "script.sh",
  toml: "config.toml",
  ts: "index.ts",
  tsx: "component.tsx",
  typescript: "index.ts",
  yaml: "config.yaml",
  yml: "config.yml",
  zsh: "script.zsh",
};

export function resolveCodeBlockDisplayFile(language: string): string {
  const normalized = language.trim().toLowerCase();
  return (
    LANGUAGE_DISPLAY_FILE_BY_LANGUAGE[normalized] ??
    `code.${normalized === "" ? "txt" : normalized}`
  );
}

interface CodeBlockContextType {
  code: string;
  toggleWrapLongLines: () => void;
  wrapLongLines: boolean;
}

const CodeBlockContext = createContext<CodeBlockContextType>({
  code: "",
  toggleWrapLongLines: () => {},
  wrapLongLines: false,
});

function CodeBlockIcon({ children }: { readonly children: ReactNode }) {
  return (
    <span
      aria-hidden={true}
      className="inline-flex size-3.5 items-center justify-center [&_svg]:h-3.5 [&_svg]:w-3.5"
    >
      {children}
    </span>
  );
}

/** 换行切换钮(无 lucide 依赖:内联 WrapText 语义图形)。 */
function CodeBlockWrapButton() {
  const { toggleWrapLongLines, wrapLongLines } = useContext(CodeBlockContext);
  const hint = useHintTooltip("切换自动换行");
  return (
    <button
      type="button"
      aria-label="切换换行"
      aria-pressed={wrapLongLines}
      onClick={toggleWrapLongLines}
      {...hint}
      className={`shrink-0 rounded p-1 text-ink-faint transition-colors hover:bg-raised hover:text-ink ${
        wrapLongLines ? "bg-raised text-ink" : ""
      }`}
    >
      <CodeBlockIcon>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 6h18" />
          <path d="M3 12h13a3 3 0 1 1 0 6h-4" />
          <path d="m14 16-2 2 2 2" />
          <path d="M3 18h4" />
        </svg>
      </CodeBlockIcon>
    </button>
  );
}

/** mermaid 放大预览钮(渲染完成后可用)。 */
function CodeBlockPreviewButton({
  disabled,
  onClick,
}: {
  readonly disabled: boolean;
  readonly onClick: () => void;
}) {
  const hint = useHintTooltip("放大预览(双击图表亦可)");
  return (
    <button
      type="button"
      aria-label="放大预览图表"
      disabled={disabled}
      {...hint}
      onClick={onClick}
      className="shrink-0 rounded p-1 text-ink-faint transition-colors hover:bg-raised hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
    >
      <CodeBlockIcon>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M15 3h6v6" />
          <path d="M9 21H3v-6" />
          <path d="M21 3l-7 7" />
          <path d="M3 21l7-7" />
        </svg>
      </CodeBlockIcon>
    </button>
  );
}

export type CodeBlockProps = HTMLAttributes<HTMLDivElement> & {
  /** 原始代码文本(复制 / mermaid 判定用)。 */
  readonly code: string;
  readonly language: string;
  /** 高亮后的 pre > code 子树(由 streamdown 的 code 插件产出)。 */
  readonly children?: ReactNode;
  readonly appTheme: "dark" | "warm";
};

export function CodeBlock({
  code,
  language,
  children,
  appTheme,
  ...props
}: CodeBlockProps) {
  const [isWrapped, setIsWrapped] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewSvg, setPreviewSvg] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  // 最新代码哈希（流式期逐 chunk 变化）；IO 回调经此取当前块
  const hashRef = useRef<string>("");
  useLayoutEffect(() => {
    hashRef.current = codeHashOf(code);
  }, [code]);
  const closePreview = useCallback(() => setPreviewOpen(false), []);
  const toggleWrapLongLines = useCallback(() => {
    setIsWrapped((current) => !current);
  }, []);
  const contextValue = useMemo(
    () => ({ code, toggleWrapLongLines, wrapLongLines: isWrapped }),
    [code, isWrapped, toggleWrapLongLines],
  );
  const canRenderMermaid = shouldRenderMermaidCodeBlock(language, code);

  const [previousCanRenderMermaid, setPreviousCanRenderMermaid] =
    useState(canRenderMermaid);
  if (previousCanRenderMermaid !== canRenderMermaid) {
    setPreviousCanRenderMermaid(canRenderMermaid);
    if (!canRenderMermaid) {
      setPreviewSvg(null);
      setPreviewOpen(false);
    }
  }

  // 首帧同步量位（useLayoutEffect 在绘制前跑）：本块在首屏视口内（±200px
  // 预高亮带）就立即标记可见并冲刷排队高亮——微任务在绘制前完成，首屏块
  // 不会出现素色闪烁。视口外块走下方 IO。
  useLayoutEffect(() => {
    if (canRenderMermaid) return;
    const hash = hashRef.current;
    if (isCodeVisible(hash)) return;
    const node = containerRef.current;
    if (node === null) return;
    const rect = node.getBoundingClientRect();
    if (rect.top < window.innerHeight + 200 && rect.bottom > -200) {
      markCodeVisibleAndFlush(hash);
    }
  });

  // 视口外块：进入视口（±200px 预高亮带）后冲刷高亮。观察的是节点而非
  // 代码内容，流式换哈希不重建观察器。
  useEffect(() => {
    if (canRenderMermaid) return;
    const node = containerRef.current;
    if (node === null || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        const hash = hashRef.current;
        if (!isCodeVisible(hash)) {
          markCodeVisibleAndFlush(hash);
        }
      },
      { rootMargin: "200px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [canRenderMermaid]);

  return (
    <CodeBlockContext.Provider value={contextValue}>
      <div
        ref={containerRef}
        className="group relative my-3 w-full overflow-hidden rounded-xl border border-line bg-surface"
        data-language={language}
        style={{
          containIntrinsicSize: "auto 200px",
          contentVisibility: "auto",
        }}
        {...props}
      >
        <div className="flex items-center justify-between gap-3 px-3 py-2 text-ui-base text-ink">
          <span className="min-w-0 truncate font-mono lowercase">
            {canRenderMermaid ? (
              <span className="flex items-center gap-2">
                <svg
                  aria-hidden="true"
                  className="size-4 text-info"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                >
                  <path d="M6 3h8l4 4v14H6z M14 3v5h4 M9 12h6 M9 16h6" />
                </svg>
                mermaid
              </span>
            ) : (
              resolveCodeBlockDisplayFile(language)
            )}
          </span>
          <div className="-my-1 -mr-1 flex items-center gap-1">
            {isMermaidLanguage(language) || canRenderMermaid ? (
              <CodeBlockPreviewButton
                disabled={!canRenderMermaid || previewSvg === null}
                onClick={() => setPreviewOpen(true)}
              />
            ) : (
              <CodeBlockWrapButton />
            )}
            <CopyButton getText={() => code} label="复制代码" iconOnly />
          </div>
        </div>
        <div className="p-2 pb-3 pt-0">
          {canRenderMermaid ? (
            <MermaidBlock
              key={`${appTheme}:${code}`}
              code={code}
              theme={appTheme}
              onOpenPreview={() => setPreviewOpen(true)}
              onPreviewSvgChange={setPreviewSvg}
            />
          ) : (
            <pre
              className={`p-2 text-sm leading-relaxed ${
                isWrapped
                  ? "whitespace-pre-wrap break-words"
                  : "overflow-x-auto whitespace-pre"
              }`}
            >
              {children}
            </pre>
          )}
        </div>
        {previewSvg !== null && (
          <DiagramPreviewDialog
            key={String(previewOpen)}
            open={previewOpen}
            onClose={closePreview}
            svg={previewSvg}
          />
        )}
      </div>
    </CodeBlockContext.Provider>
  );
}
