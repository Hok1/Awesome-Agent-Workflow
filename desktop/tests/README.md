# tests — 测试

Vitest（`npm run test` = `vitest run`，非 watch）。jsdom 环境，
`tests/setup.ts` 全局挂载 jest-dom 匹配器与 RTL cleanup。

## 组织

目录按 src 分层镜像：

- `tests/core/` — core 设施单测（logger / ring）；
- `tests/stores/` — store 行为（真实 action 通路的回归测试）；
- `tests/ui/` — 组件冒烟与交互（@testing-library/react + user-event）；
- `tests/acp/`、`tests/agents/`、`tests/aaw/` — 对应层落地时补充
  （协议层的请求超时、通知解析、进程终止是重点回归对象）；
- `tests/fixtures/` — 测试夹具：与真实输出同形状的样本 JSON 与
  经真实 action 的回放驱动。

## 约定

- 文件名 `*.test.ts(x)`，与被测模块同名；
- vitest 配置在 `vite.config.ts` 的 `test` 字段，不另建配置文件；
- 测试不 mock core 的 ring 设施——诊断链路要测「真实通路」；驱动
  store 一律走真实公开 action（夹具与局部驱动可以放 tests/ 内，
  src/ 不放）。
