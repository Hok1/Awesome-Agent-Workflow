# 工程约定（desktop/）

本文件是 AAW 桌面客户端的编码与协作规范。review 时以此为依据；
与代码冲突时，要么改代码，要么先改这里。

## 1. 命名规范

| 对象                | 约定                             | 示例                       |
| ------------------- | -------------------------------- | -------------------------- |
| 目录                | 全小写单词                       | `src/acp`、`src/stores`    |
| 组件文件            | PascalCase，一个文件一个导出组件 | `DiagnosticsPanel.tsx`     |
| 非组件 TS 文件      | camelCase                        | `logger.ts`、`logStore.ts` |
| 测试文件            | 与被测模块同名 + `.test`         | `logger.test.ts`           |
| 类型 / 接口         | PascalCase；数据形状用名词       | `LogEntry`、`AgentAdapter` |
| 函数 / 变量         | camelCase，动词开头              | `createLogger`、`recordIn` |
| 常量                | camelCase（非 SCREAMING_CASE）   | `acpTraffic`、`appLogSink` |
| zustand hook        | `use` + 域名 + `Store`           | `useLogStore`              |
| 事件通道 / 日志通道 | 小写域名                         | `acp`、`aaw`、`store`      |

- 界面文案与代码注释一律**中文**；标识符（类型、函数名）用英文。
- 布尔命名：`is/has/can` 前缀（`isLoading`、`hasSession`）。

## 2. zustand store 模式

```ts
// 一域一 store；State 与 action 内聚在同一 create 调用里
interface SessionStoreState {
  sessionId: string | null;
  openSession: (id: string) => void;
}

export const useSessionStore = create<SessionStoreState>((set) => ({
  sessionId: null,
  openSession: (id) => set({ sessionId: id }),
}));
```

硬性规则：

1. **选择器订阅**：组件里 `useStore((s) => s.x)`，禁止无选择器的
   `useStore()` 整对象订阅（多字段用 `useShallow`）。
2. **不可变更新**：`set` 永远给新对象/新数组，不做原地 mutate。
3. **action 内聚**：action 定义在 store 工厂内；不拆独立的
   action-creator 文件，不把 setState 暴露给组件。
4. **store 之间不互相 import**：共享数据下沉到 `src/core` 的纯数据设施
   （如环形缓冲），或由调用方组装后分别派发。
5. store 可以 import `core` / `aaw` / `agents` / `acp` 的纯逻辑，
   但不 import React 组件。
6. 状态变换在 action 或领域层完成，组件只做渲染。

参考实现：`src/stores/logStore.ts`。

## 3. 样式规范

- **Tailwind CSS v4**（CSS-first）：无 `tailwind.config.js`；全局入口
  `src/index.css` 的 `@import "tailwindcss"`；主题定制用 CSS 里的
  `@theme` 块（需要设计 token 时再加，目前用默认调色板）。
- 工具类**直写 JSX**，不抽 `style` 属性；动态值（如运行时计算的颜色）
  才允许内联 style。
- 色调以暗色为基调（当前页面 `bg-neutral-950` + `neutral` 系），
  与桌面开发工具的气质一致。
- 组件内重复三次以上的工具类组合才抽局部组件，不做 class 字符串拼接
  库。
- 代码高亮：highlight.js `github-dark` 主题（`src/index.css` 引入），
  配 `rehype-highlight`；`.hljs` 背景置透明，容器底色由外层控制。

## 4. 质量门槛

提交前（CI 落地前靠自觉 + `npm run` 本地）：

```bash
npm run typecheck   # tsc --noEmit（主项目 + node 配置）
npm run lint        # eslint .
npm run test        # vitest run
npm run build       # typecheck + vite build
```

- TypeScript strict 全开（含 `noUncheckedIndexedAccess`、
  `verbatimModuleSyntax`），**禁止 `any` 兜底**：外部数据 `unknown`
  进入 + 类型守卫收窄；ESLint 的 `no-explicit-any` /
  `no-unsafe-*` / `no-floating-promises` 均为 error。
- ESLint 管质量、Prettier 管格式（`npm run format`），互不越界。
