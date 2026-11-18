import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, test } from "vitest";
import { buildPrismSpec, loadPositiveExamples } from "../../scripts/prism-spec.mjs";

const repoRoot = path.resolve(process.cwd(), "../..");
const invalidDir = path.join(repoRoot, "contracts/examples/invalid");

describe("Prism spec", () => {
  test("embeds every positive contract example and skips invalid ones", () => {
    const spec = buildPrismSpec();
    for (const example of loadPositiveExamples()) {
      expect(containsDeep(spec, example.value), example.file).toBe(true);
    }
    for (const file of readdirSync(invalidDir)) {
      const value = JSON.parse(readFileSync(path.join(invalidDir, file), "utf8")) as unknown;
      expect(containsDeep(spec, value), file).toBe(false);
    }
  });
});

function containsDeep(haystack: unknown, needle: unknown): boolean {
  if (deepEqual(haystack, needle)) return true;
  if (Array.isArray(haystack)) return haystack.some((item) => containsDeep(item, needle));
  if (haystack !== null && typeof haystack === "object") {
    return Object.values(haystack).some((value) => containsDeep(value, needle));
  }
  return false;
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") return false;
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    return a.every((item, index) => deepEqual(item, b[index]));
  }
  const aRecord = a as Record<string, unknown>;
  const bRecord = b as Record<string, unknown>;
  const aKeys = Object.keys(aRecord);
  const bKeys = Object.keys(bRecord);
  if (aKeys.length !== bKeys.length) return false;
  return aKeys.every((key) => Object.hasOwn(bRecord, key) && deepEqual(aRecord[key], bRecord[key]));
}
