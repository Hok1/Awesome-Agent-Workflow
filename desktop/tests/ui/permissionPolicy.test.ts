/**
 * 审批默认模式的应答策略（src/ui/permissionPolicy）测试：
 * 三种设置模式的分派（ask 弹窗 / auto-allow 放行 / auto-reject 拒绝）、
 * kind 白名单优先级与安全默认（白名单落空回退弹窗，绝不静默取消）。
 */
import { describe, expect, it } from "vitest";

import { resolveAutoPermission } from "../../src/ui/permissionPolicy.ts";
import type { PermissionOption } from "../../src/acp/types.ts";

/** chrys 实际下发的两项选项（server.py _request_permission）。 */
const CHRYS_OPTIONS: readonly PermissionOption[] = [
  { optionId: "allow", name: "Allow once", kind: "allow_once" },
  { optionId: "reject", name: "Reject once", kind: "reject_once" },
];

describe("resolveAutoPermission", () => {
  it("ask：返回 null，交人工弹窗", () => {
    expect(resolveAutoPermission("ask", CHRYS_OPTIONS)).toBeNull();
  });

  it("auto-allow：按 allow_once 优先自动放行", () => {
    expect(resolveAutoPermission("auto-allow", CHRYS_OPTIONS)).toEqual({
      outcome: "selected",
      optionId: "allow",
    });
  });

  it("auto-allow：无 allow_once 时回落 allow_always（白名单第二优先）", () => {
    const options: readonly PermissionOption[] = [
      { optionId: "always", name: "Always allow", kind: "allow_always" },
      { optionId: "reject", name: "Reject once", kind: "reject_once" },
    ];
    expect(resolveAutoPermission("auto-allow", options)).toEqual({
      outcome: "selected",
      optionId: "always",
    });
  });

  it("auto-reject：按 reject_once 优先自动拒绝", () => {
    expect(resolveAutoPermission("auto-reject", CHRYS_OPTIONS)).toEqual({
      outcome: "selected",
      optionId: "reject",
    });
  });

  it("auto-reject：无 reject 选项时回落 reject_always", () => {
    const options: readonly PermissionOption[] = [
      { optionId: "always", name: "Always reject", kind: "reject_always" },
    ];
    expect(resolveAutoPermission("auto-reject", options)).toEqual({
      outcome: "selected",
      optionId: "always",
    });
  });

  it("白名单落空：返回 null 回退弹窗，绝不静默取消，也不拿相反语义选项充数", () => {
    const unknownOnly: readonly PermissionOption[] = [
      { optionId: "mystery", name: "Unknown", kind: "unknown" },
    ];
    expect(resolveAutoPermission("auto-allow", unknownOnly)).toBeNull();
    // auto-allow 不拿 reject 选项充数；auto-reject 不拿 allow 选项充数
    const rejectOnly: readonly PermissionOption[] = [
      { optionId: "reject", name: "Reject once", kind: "reject_once" },
    ];
    expect(resolveAutoPermission("auto-allow", rejectOnly)).toBeNull();
    const allowOnly: readonly PermissionOption[] = [
      { optionId: "allow", name: "Allow once", kind: "allow_once" },
    ];
    expect(resolveAutoPermission("auto-reject", allowOnly)).toBeNull();
    expect(resolveAutoPermission("auto-allow", [])).toBeNull();
  });
});
