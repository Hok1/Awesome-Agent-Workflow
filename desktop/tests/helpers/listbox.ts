/**
 * 自绘下拉（controls 的 Listbox）的测试交互助手。
 *
 * 原生 `<select>` 用 `userEvent.selectOptions` 一步搞定；自绘下拉要先点开
 * 触发按钮、再从面板里点选项——这两步在每个用到它的测试里重复，收在这里
 * 一处，语义也顺带说清了：面板是真的 DOM 节点（role=listbox），不是系统
 * 绘制的原生列表。
 */
import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

/**
 * 在指定名称的自绘下拉里选中一项。
 * @param user userEvent.setup() 的实例
 * @param label 触发按钮的可访问名称（与 `<select>` 时代的 getByLabelText 同名）
 * @param optionLabel 选项的可见文案
 */
export async function selectFromListbox(
  user: UserEvent,
  label: string,
  optionLabel: string,
): Promise<void> {
  await user.click(screen.getByRole("combobox", { name: label }));
  const panel = screen.getByRole("listbox", { name: label });
  await user.click(within(panel).getByRole("option", { name: optionLabel }));
}

/** 读出某自绘下拉当前显示的值（触发按钮的文本）。 */
export function listboxValue(label: string): string {
  return screen.getByRole("combobox", { name: label }).textContent ?? "";
}
