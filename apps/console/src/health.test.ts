import { describe, expect, it } from "vitest";

import { consoleHealth } from "./health";

describe("console placeholder", () => {
  it("reports ok", () => {
    expect(consoleHealth()).toBe("ok");
  });
});
