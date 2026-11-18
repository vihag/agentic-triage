import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { startPrismMock } from "../../scripts/prism-mock.mjs";

const baseUrlFile = path.join(process.cwd(), ".prism/base-url");

let stop: (() => Promise<void>) | undefined;

export async function setup(): Promise<void> {
  const port = Number(process.env.PRISM_TEST_PORT ?? 4011);
  const mock = await startPrismMock({ port });
  mkdirSync(path.dirname(baseUrlFile), { recursive: true });
  writeFileSync(baseUrlFile, `${mock.baseUrl}\n`);
  stop = mock.stop;
}

export async function teardown(): Promise<void> {
  await stop?.();
}
