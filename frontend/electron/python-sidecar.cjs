const { EventEmitter } = require("events");
const { spawn, spawnSync } = require("child_process");
const readline = require("readline");

class PythonSidecar extends EventEmitter {
  constructor(projectRoot) {
    super();
    this.projectRoot = projectRoot;
    this.process = null;
    this.readline = null;
    this.pending = new Map();
    this.requestId = 1;
    this.startPromise = null;
    this.envOverrides = {};
  }

  setEnv(overrides = {}) {
    this.envOverrides = { ...overrides };
  }

  async start() {
    if (this.process) {
      return;
    }
    if (this.startPromise) {
      return this.startPromise;
    }

    this.startPromise = new Promise((resolve, reject) => {
      const runtime = findPythonRuntime();
      if (!runtime) {
        reject(new Error("Python not found in PATH. Set SHEETGO_PYTHON or install Python."));
        return;
      }

      const child = spawn(
        runtime.command,
        [...runtime.args, "-c", "from python.main import main; main()"],
        {
          cwd: this.projectRoot,
          env: {
            ...process.env,
            ...this.envOverrides,
            PYTHONUTF8: "1",
            PYTHONUNBUFFERED: "1",
          },
          stdio: ["pipe", "pipe", "pipe"],
        }
      );

      let settled = false;

      child.once("spawn", () => {
        this.process = child;
        this.readline = readline.createInterface({ input: child.stdout });
        this.readline.on("line", (line) => this.#handleLine(line));
        child.stderr.on("data", (chunk) => {
          this.emit("stderr", chunk.toString());
        });
        child.once("exit", (code) => {
          const err = new Error(`Python sidecar exited with code ${code ?? "unknown"}`);
          for (const pending of this.pending.values()) {
            pending.reject(err);
          }
          this.pending.clear();
          this.process = null;
          this.readline = null;
          this.startPromise = null;
          this.emit("exit", code);
        });
        settled = true;
        resolve();
      });

      child.once("error", (error) => {
        if (!settled) {
          reject(error);
        }
        this.startPromise = null;
      });
    });

    return this.startPromise;
  }

  async call(method, params = {}) {
    await this.start();
    if (!this.process?.stdin) {
      throw new Error("Python sidecar is not running.");
    }

    const id = this.requestId++;
    const payload = JSON.stringify({
      jsonrpc: "2.0",
      id,
      method,
      params,
    });

    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.process.stdin.write(`${payload}\n`, "utf8", (error) => {
        if (error) {
          this.pending.delete(id);
          reject(error);
        }
      });
    });
  }

  async shutdown() {
    if (!this.process) {
      return;
    }

    const child = this.process;
    await new Promise((resolve) => {
      let finished = false;
      const complete = () => {
        if (finished) {
          return;
        }
        finished = true;
        resolve();
      };

      child.once("exit", complete);
      this.readline?.close();
      child.kill();
      setTimeout(complete, 1000);
    });
  }

  async restart() {
    await this.shutdown();
    await this.start();
  }

  #handleLine(line) {
    const raw = line.trim();
    if (!raw) {
      return;
    }

    let message;
    try {
      message = JSON.parse(raw);
    } catch (error) {
      this.emit("stderr", `Failed to parse sidecar JSON: ${raw}\n${String(error)}`);
      return;
    }

    if (Object.prototype.hasOwnProperty.call(message, "id")) {
      const pending = this.pending.get(message.id);
      if (!pending) {
        return;
      }
      this.pending.delete(message.id);
      if (message.error) {
        pending.reject(new Error(message.error.message || JSON.stringify(message.error)));
      } else {
        pending.resolve(message.result);
      }
      return;
    }

    if (message.method) {
      this.emit(message.method, message.params || {});
    }
  }
}

function findPythonRuntime() {
  const candidates = [];
  if (process.env.SHEETGO_PYTHON) {
    candidates.push([process.env.SHEETGO_PYTHON]);
  }
  candidates.push(["python"]);
  candidates.push(["python3"]);
  if (process.platform === "win32") {
    candidates.push(["py", "-3"]);
  }

  for (const candidate of candidates) {
    const [command, ...args] = candidate;
    const result = spawnSync(command, [...args, "--version"], {
      stdio: "ignore",
      shell: false,
    });
    if (!result.error && result.status === 0) {
      return { command, args };
    }
  }

  return null;
}

module.exports = {
  PythonSidecar,
};
