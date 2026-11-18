import { readFileSync } from "node:fs";
import path from "node:path";

export function mockBaseUrl(): string {
  return readFileSync(path.join(process.cwd(), ".prism/base-url"), "utf8").trim();
}
