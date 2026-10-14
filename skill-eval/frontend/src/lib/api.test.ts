import { describe, it, expect } from "vitest";
import { caseVerdict, documentsPackage, gateStatus } from "./api";
const run = (score = 100) => ({
  status: "completed",
  hard_gates: { passed: 0, total: 0 },
  scores: {
    dimensions: [
      { id: "accuracy", score, pass_score: 80, invalid: false, passed: true },
    ],
  },
});
it("尚未执行的流程门禁显示待检查，缺失结果不能显示通过", () => {
  const experiment = {
    status: "queued",
    trials: 1,
    suite_snapshot: { cases: [{ workflow: { entry: "sr" }, graders: [] }] },
    runs: [],
  };
  expect(gateStatus(experiment)).toBe("待检查");
  expect(gateStatus({ ...experiment, status: "failed" })).toBe("缺少检查结果");
  expect(gateStatus(experiment, "no_skill")).toBe("不适用");
});
describe("用例判定", () => {
  it("连续评分未达维度阈值时 Failed，正常完成不会直接变成 Pass", () => {
    expect(caseVerdict([run(60)], 1)).toBe("Failed");
    expect(caseVerdict([run(100)], 1)).toBe("Pass");
  });
  it("执行错误、缺少 Trial 与无效评分分别标识", () => {
    expect(caseVerdict([{ ...run(), status: "agent_error" }], 1)).toBe("Error");
    expect(caseVerdict([run()], 3)).toBe("未完成");
    expect(
      caseVerdict(
        [
          {
            ...run(),
            scores: { dimensions: [{ id: "accuracy", invalid: true }] },
          },
        ],
        1,
      ),
    ).toBe("Error");
  });
  it("硬门禁失败覆盖质量分，缺少维度结果不能 Pass", () => {
    expect(
      caseVerdict([{ ...run(), hard_gates: { passed: 0, total: 1 } }], 1),
    ).toBe("Failed");
    expect(caseVerdict([run()], 1, "clarity")).toBe("未完成");
    // An unrelated gate failure affects the whole task, not every dimension verdict.
    expect(
      caseVerdict(
        [{ ...run(), hard_gates: { passed: 0, total: 1 } }],
        1,
        "accuracy",
      ),
    ).toBe("Pass");
  });
});
describe("可编辑用例包", () => {
  it("保留中文与验证代码，输出导入协议", () => {
    const result = documentsPackage({
      manifest: { name: "中文用例" },
      assets: { "validate.py": 'print("测试")' },
    });
    expect(result.files.map((f) => f.path)).toEqual([
      "suite.json",
      "validate.py",
    ]);
    expect(
      new TextDecoder().decode(
        Uint8Array.from(atob(result.files[1].content_base64), (c) =>
          c.charCodeAt(0),
        ),
      ),
    ).toBe('print("测试")');
  });
});
