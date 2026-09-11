import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

export const SRC_DIR = fileURLToPath(new URL("../../src", import.meta.url));

/** Machine-generated artifacts are not hand-authored UI and are excluded from style scans. */
function isGenerated(path: string): boolean {
  return path.endsWith(".generated.ts") || path.endsWith("/api/schema.ts");
}

export async function sourceFiles(dir: string = SRC_DIR): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const full = `${dir}/${entry.name}`;
    if (entry.isDirectory()) {
      files.push(...(await sourceFiles(full)));
    } else if (/\.(ts|tsx|css)$/.test(entry.name) && !isGenerated(full)) {
      files.push(full);
    }
  }
  return files.sort();
}

export async function readSources(): Promise<{ path: string; text: string }[]> {
  const files = await sourceFiles();
  return Promise.all(files.map(async (path) => ({ path, text: await readFile(path, "utf8") })));
}
