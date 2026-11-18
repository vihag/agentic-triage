import { spawn } from "node:child_process";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { packageRoot } from "./package-root.mjs";
import { writePrismSpec } from "./prism-spec.mjs";

const consoleRoot = packageRoot();
const prismBin = path.join(consoleRoot, "node_modules/.bin/prism");

export async function startPrismMock({ port = 4010 } = {}) {
  const specPath = writePrismSpec();
  const child = spawn(
    prismBin,
    ["mock", specPath, "--port", String(port), "--host", "127.0.0.1"],
    { cwd: consoleRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  let logs = "";
  const collect = (chunk) => {
    logs += chunk.toString();
    if (logs.length > 80_000) logs = logs.slice(-80_000);
  };
  child.stdout.on("data", collect);
  child.stderr.on("data", collect);

  const baseUrl = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Prism exited ${child.exitCode}\n${logs}`);
    }
    try {
      const response = await fetch(`${baseUrl}/v1/healthz`);
      if (response.ok) {
        return { baseUrl, specPath, stop: () => stopChild(child) };
      }
    } catch {
      // Prism is still binding the port.
    }
    await delay(200);
  }
  child.kill("SIGKILL");
  throw new Error(`Prism did not become ready on ${baseUrl}\n${logs}`);
}

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function stopChild(child) {
  if (child.exitCode !== null) return Promise.resolve();
  child.kill("SIGTERM");
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      resolve();
    }, 2_000);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

const invokedDirectly =
  process.argv[1] !== undefined && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (invokedDirectly) {
  const port = Number(process.env.PRISM_PORT ?? 4010);
  const mock = await startPrismMock({ port });
  console.log(`Prism mock of contracts/openapi.yaml listening on ${mock.baseUrl}`);
  const shutdown = () => {
    mock.stop().then(() => process.exit(0));
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}
