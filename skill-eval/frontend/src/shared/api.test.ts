import { expect, it, vi } from "vitest";
import { documentsPackage, score } from "./api";
import { poll } from "./polling";

it("encodes non-ASCII case material without corruption", () => {
  const pack = documentsPackage({
    manifest: { name: "中文用例" },
    assets: { "说明.md": "预期结果" },
  });
  const bytes = Uint8Array.from(atob(pack.files[1].content_base64), (c) =>
    c.charCodeAt(0),
  );
  expect(new TextDecoder().decode(bytes)).toBe("预期结果");
  expect(score(null)).toBe("—");
});

it("does not publish a response after navigating away", async () => {
  let resolve!: (value: number) => void;
  const receive = vi.fn();
  const dispose = poll(
    () =>
      new Promise<number>((done) => {
        resolve = done;
      }),
    receive,
    vi.fn(),
    100,
  );
  dispose();
  resolve(1);
  await Promise.resolve();
  expect(receive).not.toHaveBeenCalled();
});
