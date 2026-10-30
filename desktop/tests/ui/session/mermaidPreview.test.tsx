import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CodeBlock } from "../../../src/ui/session/markdown/CodeBlock.tsx";
import {
  fitDiagramToViewport,
  zoomDiagramAtPoint,
  panDiagram,
} from "../../../src/ui/session/markdown/diagramViewport.ts";
vi.mock("@streamdown/mermaid", () => ({
  createMermaidPlugin: () => ({
    getMermaid: () => ({
      render: () =>
        Promise.resolve({
          svg: '<svg viewBox="0 0 3000 1200" width="100%" style="max-width:3000px"><text x="20" y="20">宽流程图</text></svg>',
        }),
    }),
  }),
}));
beforeEach(() => {
  Object.defineProperty(SVGSVGElement.prototype, "viewBox", {
    configurable: true,
    get: () => ({ baseVal: { x: 0, y: 0, width: 3000, height: 1200 } }),
  });
  Object.defineProperty(SVGSVGElement.prototype, "getBBox", {
    configurable: true,
    value: () => ({ x: 0, y: 0, width: 3000, height: 1200 }),
  });
});
describe("ZCode Mermaid 预览", () => {
  it("宽图保留自然尺寸，预览越过含 content-visibility 的祖先并支持缩放与 Esc", async () => {
    const { container } = render(
      <div style={{ contentVisibility: "auto", overflow: "hidden" }}>
        <CodeBlock
          code="flowchart LR\n A-->B"
          language="mermaid"
          appTheme="warm"
        />
      </div>,
    );
    const open = screen.getByRole("button", { name: "放大预览图表" });
    await waitFor(() => expect(open).toBeEnabled());
    expect(container.querySelector("svg[viewBox='0 0 3000 1200']")).toHaveStyle(
      { width: "3000px", height: "1200px" },
    );
    open.focus();
    fireEvent.click(open);
    const dialog = screen.getByRole("dialog", { name: "Mermaid 图表" });
    expect(container).not.toContainElement(dialog);
    expect(document.body).toContainElement(dialog);
    await act(async () => {
      await new Promise((resolve) => requestAnimationFrame(resolve));
    });
    expect(dialog.querySelector("[role=img]")).toHaveStyle({
      width: "3000px",
      height: "1200px",
    });
    fireEvent.click(screen.getByRole("button", { name: /^放大$/ }));
    expect(screen.getByRole("button", { name: "缩放比例" })).toHaveTextContent(
      "118%",
    );
    fireEvent.click(screen.getByRole("button", { name: "缩放比例" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "200%" }));
    expect(screen.getByRole("button", { name: "缩放比例" })).toHaveTextContent(
      "200%",
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
    expect(open).toHaveFocus();
  });
  it("适应窗口按长宽比居中，缩放锚点与平移保持稳定", () => {
    const fitted = fitDiagramToViewport({
      diagramWidth: 3000,
      diagramHeight: 1200,
      viewportWidth: 1600,
      viewportHeight: 800,
    });
    expect(fitted.scale).toBeCloseTo(1536 / 3000);
    expect(fitted.translateX).toBeCloseTo(32);
    expect(fitted.translateY).toBeCloseTo((800 - 1200 * fitted.scale) / 2);
    const point = { x: 800, y: 400 };
    const zoom = zoomDiagramAtPoint(fitted, point, 1);
    expect((point.x - zoom.translateX) / zoom.scale).toBeCloseTo(
      (point.x - fitted.translateX) / fitted.scale,
    );
    expect(panDiagram(zoom, { x: 50, y: -30 })).toMatchObject({
      translateX: zoom.translateX + 50,
      translateY: zoom.translateY - 30,
    });
  });
});
