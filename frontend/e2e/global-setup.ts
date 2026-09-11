import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const SERVICE_PORT = "8099";
const APP_PORT = "3011";
const SERVICE_URL = `http://127.0.0.1:${SERVICE_PORT}`;
const APP_URL = `http://127.0.0.1:${APP_PORT}`;
const TOKEN = "e2e-token";

const FRONTEND = path.resolve(__dirname, "..");
const REPO = path.resolve(FRONTEND, "..");

async function waitFor(url: string, timeoutMs = 90_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.status < 500) return;
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`timed out waiting for ${url}: ${String(lastError)}`);
}

function stop(child: ChildProcess | null): void {
  if (child && !child.killed) child.kill("SIGTERM");
}

export default async function globalSetup(): Promise<() => void> {
  const workdir = mkdtempSync(path.join(tmpdir(), "ledger-e2e-"));
  const databasePath = path.join(workdir, "ledger.sqlite3");
  const manifestPath = path.join(__dirname, ".fixtures.json");

  // 1. Seed authoritative state with the repository's real pipeline driver.
  const seed = spawnSync(
    "python3",
    [path.join(__dirname, "seed_fixtures.py"), databasePath, manifestPath],
    { cwd: REPO, encoding: "utf8", env: { ...process.env, PYTHONPATH: path.join(REPO, "src") } },
  );
  if (seed.status !== 0) {
    throw new Error(`fixture seed failed (${seed.status}): ${seed.stderr || seed.stdout}`);
  }

  // 2. The real service over that database.
  const service = spawn("python3", ["-m", "ledger"], {
    cwd: REPO,
    stdio: "ignore",
    env: {
      ...process.env,
      PYTHONPATH: path.join(REPO, "src"),
      LEDGER_DATABASE_PATH: databasePath,
      LEDGER_HOST: "127.0.0.1",
      LEDGER_PORT: SERVICE_PORT,
      LEDGER_ENV: "test",
      LEDGER_API_TOKENS: `${TOKEN}:reconciliation_operator:source-a|source-b`,
    },
  });
  await waitFor(`${SERVICE_URL}/v1/health`);

  // 3. The dashboard in production mode, reading the token server-side only.
  const app = spawn("npx", ["next", "start", "-p", APP_PORT], {
    cwd: FRONTEND,
    stdio: "ignore",
    env: {
      ...process.env,
      LEDGER_API_BASE_URL: SERVICE_URL,
      LEDGER_API_TOKEN: TOKEN,
    },
  });
  await waitFor(APP_URL);

  return () => {
    stop(app);
    stop(service);
    rmSync(workdir, { recursive: true, force: true });
  };
}
