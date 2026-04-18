const path = require("path");
const fs = require("fs/promises");
const { app, BrowserWindow, dialog, ipcMain, nativeTheme, shell } = require("electron");

const workspace = require("./workspace.cjs");
const { PythonSidecar } = require("./python-sidecar.cjs");

const projectRoot = path.resolve(__dirname, "..", "..");
const sidecar = new PythonSidecar(projectRoot);
const UTF8_BOM = "\uFEFF";

let mainWindow = null;
let loggingSetup = false;

function shouldUseDarkWindowTheme(themePreference = "light") {
  if (themePreference === "dark") {
    return true;
  }
  if (themePreference === "system") {
    return nativeTheme.shouldUseDarkColors;
  }
  return false;
}

function getWindowChrome(themePreference = "light") {
  const dark = shouldUseDarkWindowTheme(themePreference);

  return dark
    ? {
        backgroundColor: "#0e0a08",
        overlayColor: "#17120f",
        symbolColor: "#f4ede1",
      }
    : {
        backgroundColor: "#f3ede4",
        overlayColor: "#f3ede4",
        symbolColor: "#201915",
      };
}

function applyWindowChrome(win, themePreference = "light") {
  if (!win || win.isDestroyed()) {
    return;
  }

  const chrome = getWindowChrome(themePreference);
  win.setBackgroundColor(chrome.backgroundColor);

  if (process.platform === "win32" || process.platform === "linux") {
    win.setTitleBarOverlay({
      color: chrome.overlayColor,
      symbolColor: chrome.symbolColor,
      height: 38,
    });
  }
}

function logsDir() {
  return path.join(workspace.baseDir(), "logs");
}

function logFilePath() {
  return path.join(logsDir(), "desktop.log");
}

function normalizeErrorMessage(value) {
  if (value instanceof Error) {
    return value.stack || value.message || String(value);
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function summarizeErrorForUser(value) {
  const text = normalizeErrorMessage(value).trim();
  if (!text) {
    return "发生未知错误";
  }

  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const candidate = [...lines]
    .reverse()
    .find((line) => line !== "Traceback (most recent call last):");

  return (candidate || text)
    .replace(/^(?:Error|Internal error|RuntimeError|ValueError|TypeError):\s*/i, "")
    .trim();
}

function buildUserFacingError(value) {
  return `${summarizeErrorForUser(value)}。详细日志：${logFilePath()}`;
}

async function ensureUtf8LogFile() {
  await fs.mkdir(logsDir(), { recursive: true });

  try {
    const content = await fs.readFile(logFilePath(), "utf8");
    if (!content.startsWith(UTF8_BOM)) {
      await fs.writeFile(logFilePath(), `${UTF8_BOM}${content}`, "utf8");
    }
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") {
      await fs.writeFile(logFilePath(), UTF8_BOM, "utf8");
      return;
    }
    throw error;
  }
}

function stripUtf8Bom(content) {
  return typeof content === "string" && content.startsWith(UTF8_BOM)
    ? content.slice(1)
    : content;
}

async function appendDesktopLog(level, scope, message, details) {
  try {
    await ensureUtf8LogFile();
    const entry = {
      ts: new Date().toISOString(),
      level,
      scope,
      message: normalizeErrorMessage(message),
      ...(details !== undefined ? { details } : {}),
    };
    await fs.appendFile(logFilePath(), `${JSON.stringify(entry, null, 2)}\n`, "utf8");
  } catch (error) {
    console.error("Failed to write desktop log:", error);
  }
}

async function readJsonFileSafe(filePath) {
  try {
    return JSON.parse(stripUtf8Bom(await fs.readFile(filePath, "utf8")));
  } catch (error) {
    if (
      error &&
      typeof error === "object" &&
      (error.code === "ENOENT" || error.name === "SyntaxError")
    ) {
      return null;
    }
    throw error;
  }
}

async function readDesktopLog(limit = 120000) {
  try {
    await ensureUtf8LogFile();
    const content = stripUtf8Bom(await fs.readFile(logFilePath(), "utf8"));
    return content.length > limit ? content.slice(-limit) : content;
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") {
      return "";
    }
    throw error;
  }
}

async function openPathOrThrow(targetPath) {
  const result = await shell.openPath(targetPath);
  if (result) {
    throw new Error(result);
  }
}

function setupProcessLogging() {
  if (loggingSetup) {
    return;
  }
  loggingSetup = true;

  process.on("uncaughtException", (error) => {
    console.error(error);
    void appendDesktopLog("fatal", "electron.uncaughtException", error);
  });

  process.on("unhandledRejection", (reason) => {
    console.error(reason);
    void appendDesktopLog("fatal", "electron.unhandledRejection", reason);
  });
}

function buildSidecarEnv(config) {
  if (!config) {
    return {};
  }

  const env = {
    LLM_PROVIDER: config.llm?.provider || "openai",
    LLM_MODEL: config.llm?.model || "gpt-4o",
    LLM_TEMPERATURE: String(config.llm?.temperature ?? 0.1),
    LLM_MAX_TOKENS: String(config.llm?.maxTokens ?? 4096),
    PRELOAD_SAMPLE_ROWS: String(config.advanced?.preloadSampleRows ?? 20),
    FILE_MAX_SIZE_MB: String(
      Math.max(1, Math.round((config.advanced?.maxFileSize ?? 104857600) / 1048576))
    ),
  };

  if (typeof config.llm?.apiKey === "string" && config.llm.apiKey.trim()) {
    env.LLM_API_KEY = config.llm.apiKey.trim();
  }

  if (typeof config.llm?.baseUrl === "string" && config.llm.baseUrl.trim()) {
    env.LLM_BASE_URL = config.llm.baseUrl.trim();
  }

  return env;
}

function parseTimestamp(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
      return numeric;
    }
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }
  return 0;
}

async function listFilesForSession(sessionId) {
  const session = await workspace.getSession(sessionId);
  let records = [];

  try {
    records = await sidecar.call("file.list", {
      sessionId,
      dbPath: workspace.dbPath(),
    });
  } catch (error) {
    console.warn("file.list sidecar failed, falling back to workspace scan:", error);
  }

  if (!Array.isArray(records) || records.length === 0) {
    return workspace.listFiles(sessionId);
  }

  const files = await Promise.all(
    records.map(async (record) => {
      const fileId = record.fileId || record.file_id;
      const schema = await workspace.readSchema(session.cacheDir, fileId);
      return {
        fileId,
        fileName: record.fileName || record.file_name || `${fileId}.xlsx`,
        sheets: schema.sheets,
        totalRows: schema.totalRows,
        createdAt: parseTimestamp(record.createdAt || record.created_at),
      };
    })
  );

  return files
    .sort((a, b) => b.createdAt - a.createdAt || a.fileName.localeCompare(b.fileName))
    .map(({ createdAt: _createdAt, ...file }) => file);
}

function emit(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
}

function attachSidecarListeners() {
  sidecar.on("preload.progress", (payload) => emit("preload-progress", payload));
  sidecar.on("chat.event", (payload) => emit("chat-stream", payload));
  sidecar.on("stderr", (message) => {
    const text = String(message).trim();
    if (text) {
      console.error(text);
      void appendDesktopLog("error", "python.stderr", text);
    }
  });
  sidecar.on("exit", (code) => {
    void appendDesktopLog("error", "python.exit", `Python sidecar exited with code ${code ?? "unknown"}`);
  });
}

async function createMainWindow() {
  const config = await workspace.getConfig();
  const chrome = getWindowChrome(config.ui?.theme || "light");

  mainWindow = new BrowserWindow({
    width: 1540,
    height: 980,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: chrome.backgroundColor,
    title: "SheetGo",
    autoHideMenuBar: true,
    ...(process.platform === "win32" || process.platform === "linux"
      ? {
          titleBarStyle: "hidden",
          titleBarOverlay: {
            color: chrome.overlayColor,
            symbolColor: chrome.symbolColor,
            height: 38,
          },
        }
      : {}),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  const devServerUrl = process.env.VITE_DEV_SERVER_URL;
  if (devServerUrl) {
    await mainWindow.loadURL(devServerUrl);
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    await mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

async function ensureDesktopReady() {
  await workspace.initWorkspace();
  const config = await workspace.getConfig();
  sidecar.setEnv(buildSidecarEnv(config));
  await sidecar.start();
}

function registerIpc() {
  ipcMain.handle("desktop:pickExcelFile", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ["openFile"],
      filters: [{ name: "Excel", extensions: ["xlsx", "xlsm"] }],
    });
    return result.canceled ? null : result.filePaths[0] || null;
  });

  ipcMain.on("desktop:rendererLog", (_event, payload) => {
    void appendDesktopLog(
      payload?.level || "info",
      payload?.scope || "renderer",
      payload?.message || "",
      payload?.details
    );
  });

  ipcMain.handle("desktop:getDiagnostics", async () => ({
    logsDir: logsDir(),
    logFilePath: logFilePath(),
  }));
  ipcMain.handle("desktop:readDesktopLog", async (_event, { limit } = {}) => readDesktopLog(limit));
  ipcMain.handle("desktop:openDesktopLog", async () => {
    await ensureUtf8LogFile();
    await openPathOrThrow(logFilePath());
    return { opened: true, target: logFilePath() };
  });
  ipcMain.handle("desktop:openLogsDirectory", async () => {
    await fs.mkdir(logsDir(), { recursive: true });
    await openPathOrThrow(logsDir());
    return { opened: true, target: logsDir() };
  });
  ipcMain.handle("desktop:getParsedArtifacts", async (_event, { fileId, sessionId }) => {
    const session = await workspace.getSession(sessionId);
    const schemaPath = workspace.cachePath(session, fileId, "schema.json");
    const statsPath = workspace.cachePath(session, fileId, "stats.json");
    const structurePath = workspace.cachePath(session, fileId, "structure.json");

    const [schema, stats, structure] = await Promise.all([
      readJsonFileSafe(schemaPath),
      readJsonFileSafe(statsPath),
      readJsonFileSafe(structurePath),
    ]);

    return {
      fileId,
      paths: {
        schema: schemaPath,
        stats: statsPath,
        structure: structurePath,
      },
      schema,
      stats,
      structure,
    };
  });

  ipcMain.handle("desktop:uploadFile", async (_event, { path: filePath, sessionId }) => {
    void appendDesktopLog("info", "upload.start", "Import requested", {
      sessionId,
      filePath,
    });

    let imported;
    try {
      imported = await workspace.importFile(sessionId, filePath);
    } catch (error) {
      void appendDesktopLog("error", "upload.copy", error, {
        sessionId,
        filePath,
      });
      throw new Error(buildUserFacingError(error));
    }

    let importRecord;

    try {
      importRecord = await sidecar.call("file.import", {
        sessionId,
        fileId: imported.fileId,
        fileName: imported.fileName,
        sourcePath: imported.sourcePath,
        workingPath: imported.workingPath,
        dbPath: workspace.dbPath(),
      });
    } catch (error) {
      void appendDesktopLog("error", "upload.import", error, {
        sessionId,
        filePath,
      });
      await workspace.removeFile(imported.fileId, sessionId).catch(() => {});
      throw new Error(buildUserFacingError(error));
    }

    if (importRecord?.duplicateOf) {
      void appendDesktopLog("info", "upload.duplicate", "Duplicate file skipped", {
        sessionId,
        filePath,
        duplicateOf: importRecord.duplicateOf,
      });
      await workspace.removeFile(imported.fileId, sessionId).catch(() => {});
      const files = await listFilesForSession(sessionId);
      return files.find((file) => file.fileId === importRecord.duplicateOf) || {
        fileId: importRecord.duplicateOf,
        fileName: imported.fileName,
        sheets: [],
        totalRows: 0,
      };
    }

    const preloadArgs = {
      fileId: imported.fileId,
      sourcePath: imported.sourcePath,
      workingPath: imported.workingPath,
      duckdbPath: workspace.cachePath(imported.session, imported.fileId, "data.duckdb"),
      schemaPath: workspace.cachePath(imported.session, imported.fileId, "schema.json"),
      statsPath: workspace.cachePath(imported.session, imported.fileId, "stats.json"),
    };

    let preloadResult;
    try {
      preloadResult = await sidecar.call("preload.start", preloadArgs);
    } catch (error) {
      void appendDesktopLog("error", "upload.preload.rpc", error, {
        sessionId,
        fileId: imported.fileId,
        preloadArgs,
      });
      await workspace.removeFile(imported.fileId, sessionId).catch(() => {});
      throw new Error(buildUserFacingError(error));
    }

    if (preloadResult?.status !== "ok") {
      void appendDesktopLog("error", "upload.preload", preloadResult?.errorMessage || preloadResult, {
        sessionId,
        fileId: imported.fileId,
        preloadArgs,
      });
      await workspace.removeFile(imported.fileId, sessionId).catch(() => {});
      throw new Error(buildUserFacingError(preloadResult?.errorMessage || "文件预处理失败"));
    }

    const files = await listFilesForSession(sessionId);
    void appendDesktopLog("info", "upload.success", "Import completed", {
      sessionId,
      filePath,
      fileId: imported.fileId,
    });
    return files.find((file) => file.fileId === imported.fileId) || {
      fileId: imported.fileId,
      fileName: imported.fileName,
      sheets: [],
      totalRows: 0,
    };
  });

  ipcMain.handle("desktop:listFiles", async (_event, { sessionId }) => listFilesForSession(sessionId));
  ipcMain.handle("desktop:removeFile", async (_event, { fileId, sessionId }) => {
    await workspace.removeFile(fileId, sessionId);
    try {
      await sidecar.call("file.remove", { fileId, sessionId, dbPath: workspace.dbPath() });
    } catch (error) {
      console.warn("file.remove sidecar failed:", error);
    }
  });
  ipcMain.handle("desktop:getFileInfo", async (_event, { fileId, sessionId }) => {
    try {
      const record = await sidecar.call("file.info", {
        fileId,
        dbPath: workspace.dbPath(),
      });
      const session = await workspace.getSession(sessionId);
      const schema = await workspace.readSchema(session.cacheDir, fileId);
      return {
        fileId,
        fileName: record.fileName || record.file_name || `${fileId}.xlsx`,
        sheets: schema.sheets,
        totalRows: schema.totalRows,
      };
    } catch {
      return workspace.getFileInfo(fileId, sessionId);
    }
  });
  ipcMain.handle("desktop:getFileBytes", async (_event, { fileId, sessionId }) =>
    workspace.getFileBytes(fileId, sessionId)
  );
  ipcMain.handle("desktop:saveWorkbookEdits", async (_event, { fileId, sessionId, edits }) => {
    void appendDesktopLog("info", "save.start", "Workbook save requested", {
      sessionId,
      fileId,
      editCount: Array.isArray(edits) ? edits.length : 0,
    });

    try {
      const result = await sidecar.call("file.applyEdits", {
        fileId,
        sessionId,
        edits,
        dbPath: workspace.dbPath(),
      });
      emit("file-changed", { fileId, changeType: "modified" });
      void appendDesktopLog("info", "save.success", "Workbook save completed", {
        sessionId,
        fileId,
        editCount: result?.editCount ?? 0,
        cacheRefreshed: result?.cacheRefreshed ?? false,
      });
      return result;
    } catch (error) {
      void appendDesktopLog("error", "save.applyEdits", error, {
        sessionId,
        fileId,
        editCount: Array.isArray(edits) ? edits.length : 0,
      });
      throw new Error(buildUserFacingError(error));
    }
  });
  ipcMain.handle("desktop:chat", async (_event, req) =>
    sidecar.call("chat", {
      session_id: req.sessionId,
      file_id: req.fileId,
      message: req.message,
    })
  );
  ipcMain.handle("desktop:chatStream", async (_event, req) => {
    void sidecar.call("chat_stream", {
      session_id: req.sessionId,
      file_id: req.fileId,
      message: req.message,
    }).catch((error) => {
      emit("chat-stream", { type: "error", error: String(error) });
    });
    return `stream_${Date.now()}`;
  });
  ipcMain.handle("desktop:stopChat", async () => {
    await sidecar.call("stop", {});
  });
  ipcMain.handle("desktop:confirmToolCall", async () => ({ ok: true }));
  ipcMain.handle("desktop:listSessions", async () => workspace.listSessions());
  ipcMain.handle("desktop:createSession", async (_event, { name }) => workspace.createSession(name));
  ipcMain.handle("desktop:deleteSession", async (_event, { sessionId }) => workspace.deleteSession(sessionId));
  ipcMain.handle("desktop:rollbackSnapshot", async (_event, { snapshotId }) =>
    workspace.rollbackSnapshot(snapshotId)
  );
  ipcMain.handle("desktop:getSnapshots", async (_event, { sessionId, fileId }) =>
    workspace.listSnapshots(sessionId, fileId)
  );
  ipcMain.handle("desktop:getHistory", async (_event, { sessionId }) => workspace.getHistory(sessionId));
  ipcMain.handle("desktop:saveHistory", async (_event, { sessionId, entries }) =>
    workspace.saveHistory(sessionId, entries)
  );
  ipcMain.handle("desktop:getConfig", async () => workspace.getConfig());
  ipcMain.handle("desktop:saveConfig", async (_event, { config }) => {
    await workspace.saveConfig(config);
    sidecar.setEnv(buildSidecarEnv(config));
    await sidecar.restart();
    applyWindowChrome(mainWindow, config?.ui?.theme || "light");
  });
}

app.whenReady().then(async () => {
  setupProcessLogging();
  attachSidecarListeners();
  await ensureDesktopReady();
  await appendDesktopLog("info", "desktop.ready", "Desktop app initialized", {
    logsDir: logsDir(),
    logFilePath: logFilePath(),
  });
  registerIpc();
  await createMainWindow();

  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createMainWindow();
    }
  });
}).catch(async (error) => {
  console.error(error);
  await appendDesktopLog("fatal", "desktop.startup", error);
  dialog.showErrorBox("SheetGo 启动失败", buildUserFacingError(error));
  app.exit(1);
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async () => {
  await sidecar.shutdown();
});
