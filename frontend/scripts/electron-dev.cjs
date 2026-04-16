const http = require("http");
const path = require("path");
const { spawn } = require("child_process");

const root = path.resolve(__dirname, "..");
const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
const electronCmd = process.platform === "win32"
  ? path.join(root, "node_modules", ".bin", "electron.cmd")
  : path.join(root, "node_modules", ".bin", "electron");

let viteProcess = null;
let electronProcess = null;

run().catch((error) => {
  console.error(error);
  cleanup(1);
});

async function run() {
  viteProcess = spawn(npmCmd, ["run", "renderer:dev"], {
    cwd: root,
    stdio: "inherit",
    shell: false,
  });

  viteProcess.on("exit", (code) => {
    if (code !== 0) {
      cleanup(code || 1);
    }
  });

  await waitForUrl("http://127.0.0.1:1420", 60000);

  electronProcess = spawn(electronCmd, ["."], {
    cwd: root,
    stdio: "inherit",
    env: {
      ...process.env,
      VITE_DEV_SERVER_URL: "http://127.0.0.1:1420",
    },
  });

  electronProcess.on("exit", (code) => {
    cleanup(code || 0);
  });

  process.on("SIGINT", () => cleanup(0));
  process.on("SIGTERM", () => cleanup(0));
}

function waitForUrl(url, timeoutMs) {
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve();
      });

      req.on("error", () => {
        if (Date.now() - startedAt > timeoutMs) {
          reject(new Error(`Timed out waiting for ${url}`));
          return;
        }
        setTimeout(attempt, 350);
      });
    };

    attempt();
  });
}

function cleanup(code) {
  if (electronProcess && !electronProcess.killed) {
    electronProcess.kill();
  }
  if (viteProcess && !viteProcess.killed) {
    viteProcess.kill();
  }
  process.exit(code);
}
