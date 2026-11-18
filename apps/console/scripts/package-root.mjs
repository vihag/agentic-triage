import path from "node:path";

export function packageRoot() {
  const entry = process.argv[1];
  if (entry) {
    const dir = path.dirname(path.resolve(entry));
    if (path.basename(dir) === "scripts") return path.resolve(dir, "..");
  }
  return process.cwd();
}
