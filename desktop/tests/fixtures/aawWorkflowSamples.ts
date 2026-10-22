/**
 * aaw CLI 样本输出（测试夹具）：与 `aaw status` / `next` `--json` 实际输出
 * 同形状的 JSON（对照 main.py status 命令与 workflow.py build_next_payload）。
 *
 * 供解析器与 store / 面板测试复用：因为形状与真实 CLI 输出一致，解析走
 * 生产代码里的同一套宽收窄解析器。
 */

/** `aaw status --json`（无 --sr）：SR 列表。 */
export const sampleSrListJson: unknown = {
  ok: true,
  srs: ["SR-001", "SR-004"],
};

/** `aaw status --sr SR-004 --json`：dev 入口进行中的工作流。 */
export const sampleStatusJson: unknown = {
  ok: true,
  sr: "SR-004",
  workflow_id: "dev-20261020-001",
  entry: "dev",
  status: "in_progress",
  vars: { SR: "SR-004" },
  pending_user_confirm: null,
  steps: [
    {
      id: 1,
      type: "dev-init",
      name: "确认需求",
      execution: "skill",
      finished: true,
      execution_status: "completed",
      attempt: 1,
      started_at: "2026-10-20T08:11:04Z",
      ended_at: "2026-10-20T08:16:32Z",
      next: [2],
      depends_on: [],
    },
    {
      id: 2,
      type: "dev-design",
      name: "功能设计",
      execution: "skill",
      finished: true,
      execution_status: "completed",
      attempt: 1,
      started_at: "2026-10-20T08:16:40Z",
      ended_at: "2026-10-20T08:41:07Z",
      next: [3],
      depends_on: [1],
    },
    {
      id: 3,
      type: "dev-test-design",
      name: "测试设计",
      execution: "skill",
      finished: false,
      execution_status: "running",
      attempt: 1,
      started_at: "2026-10-20T08:42:15Z",
      ended_at: null,
      next: [4],
      depends_on: [2],
    },
    {
      id: 4,
      type: "dev-design-gate",
      name: "设计门禁",
      execution: "skill",
      finished: false,
      execution_status: "ready",
      attempt: 1,
      started_at: null,
      ended_at: null,
      next: [5],
      depends_on: [3],
    },
    {
      id: 5,
      type: "dev-task-split",
      name: "任务拆分",
      execution: "skill",
      finished: false,
      execution_status: "ready",
      attempt: 1,
      started_at: null,
      ended_at: null,
      next: [6],
      depends_on: [4],
    },
    {
      id: 6,
      type: "dev-task-dev",
      name: "开发",
      execution: "skill",
      finished: false,
      execution_status: "ready",
      attempt: 1,
      started_at: null,
      ended_at: null,
      next: [],
      depends_on: [5],
    },
  ],
};

/** `aaw next --sr SR-004 --peek --json`：当前就绪工作单（测试设计）。 */
export const sampleNextJson: unknown = {
  ok: true,
  sr: "SR-004",
  entry: "dev",
  status: "in_progress",
  ready: [
    {
      id: 3,
      type: "dev-test-design",
      name: "测试设计",
      execution: "skill",
      skill: ["dev-test-design"],
      prompt:
        "基于 .sdd/SR-004/dev-design.md 生成最小充分用例集、覆盖矩阵与缺口清单，写入 .sdd/SR-004/test-design.md。",
      data_prompt: "提交覆盖矩阵摘要",
      data_file: {
        path: "D:/dev/workspace-ai/demo/.sdd/SR-004/.aaw/data/step-0003-dev-test-design.json",
        encoding: "utf-8",
        overwrite: true,
      },
      input: [
        {
          path: "D:/dev/workspace-ai/demo/.sdd/SR-004/dev-design.md",
          required: true,
          exists: true,
        },
      ],
      output: [
        {
          path: "D:/dev/workspace-ai/demo/.sdd/SR-004/test-design.md",
          required: true,
          exists: false,
        },
      ],
      inputs: {
        required: ["D:/dev/workspace-ai/demo/.sdd/SR-004/dev-design.md"],
        optional: [],
        missing_required: [],
        all_required_exist: true,
        blocked: false,
      },
      data: {
        description: "覆盖矩阵摘要",
        fields: {
          covered: { description: "已覆盖用例 ID", example: ["T-001"] },
        },
      },
      deliverables: {
        required: ["D:/dev/workspace-ai/demo/.sdd/SR-004/test-design.md"],
        optional: [],
        missing_required: [
          "D:/dev/workspace-ai/demo/.sdd/SR-004/test-design.md",
        ],
        all_required_exist: false,
        can_skip: false,
      },
      existing_output_reusable: false,
      commands: {
        done_argv: [
          "python",
          "D:/dev/workspace-ai/demo/skills/aaw-workflow/scripts/aaw.py",
          "done",
          "--sr",
          "SR-004",
          "3",
          "--data-file",
          "D:/dev/workspace-ai/demo/.sdd/SR-004/.aaw/data/step-0003-dev-test-design.json",
          "--json",
        ],
      },
    },
  ],
  done: false,
  telemetry: [],
};

/** `aaw next --sr SR-004 --peek --json`：awaiting_user_confirm 场景。 */
export const sampleNextAwaitingJson: unknown = {
  ok: true,
  sr: "SR-004",
  entry: "dev",
  status: "awaiting_user_confirm",
  ready: [],
  done: false,
  message: "当前步骤已完成，等待用户确认是否放行进入下一步。",
  pending_user_confirm: {
    from_step: 3,
    from_name: "测试设计",
    from_type: "dev-test-design",
    planned_next: [{ id: 4, name: "设计门禁", type: "dev-design-gate" }],
    prompt: "当前步骤已完成，等待用户确认是否放行进入下一步。",
  },
  commands: {
    user_confirm:
      "python D:/dev/workspace-ai/demo/skills/aaw-workflow/scripts/aaw.py user-confirm --sr SR-004 --json",
    user_confirm_argv: [
      "python",
      "D:/dev/workspace-ai/demo/skills/aaw-workflow/scripts/aaw.py",
      "user-confirm",
      "--sr",
      "SR-004",
      "--json",
    ],
  },
};

/** `aaw status --sr SR-404 --json` 的失败信封样本。 */
export const sampleCliErrorJson: unknown = {
  schema_version: 1,
  ok: false,
  error: { code: "WORKFLOW_NOT_FOUND", message: "SR SR-404 不存在" },
};
