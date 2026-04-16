const path = require("path");
const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");

const workspace = require("./workspace.cjs");
const { PythonSidecar } = require("./python-sidecar.cjs");

const projectRoot = path.resolve(__dirname, "..", "..");
const sidecar = new PythonSidecar(projectRoot);

let mainWindow = null;

function buildSidecarEnv(config) {
  if (!config) {
    return {};
  }

  return {
    LLM_PROVIDER: config.llm?.provider || "openai",
    LLM_MODEL: config.llm?.model || "gpt-4o",
    LLM_API_KEY: config.llm?.apiKey || "",
    LLM_BASE_URL: config.llm?.baseUrl || "",
    LLM_TEMPERATURE: String(config.llm?.temperature ?? 0.1),
    LLM_MAX_TOKENS: String(config.llm?.maxTokens ?? 4096),
    PRELOAD_SAMPLE_ROWS: String(config.advanced?.preloadSampleRows ?? 20),
    FILE_MAX_SIZE_MB: String(
      Math.max(1, Math.round((config.advanced?.maxFileSize ?? 104857600) / 1048576))
    ),
  };
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
    if (String(message).trim()) {
      console.error(message);
    }
  });
}

async function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1540,
    height: 980,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#f3f3f0",
    title: "SheetGo",
    autoHideMenuBar: true,
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
      filters: [{ name: "Excel", extensions: ["xlsx", "xls"] }],
    });
    return result.canceled ? null : result.filePaths[0] || null;
  });

  ipcMain.handle("desktop:uploadFile", async (_event, { path: filePath, sessionId }) => {
    const imported = await workspace.importFile(sessionId, filePath);
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
      await workspace.removeFile(imported.fileId, sessionId).catch(() => {});
      throw error;
    }

    if (importRecord?.duplicateOf) {
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

    void sidecar.call("preload.start", preloadArgs).catch((error) => {
      emit("preload-progress", {
        fileId: imported.fileId,
        stage: "done",
        progress: 100,
        message: String(error),
      });
    });

    const files = await listFilesForSession(sessionId);
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
  ipcMain.handle("desktop:getConfig", async () => workspace.getConfig());
  ipcMain.handle("desktop:saveConfig", async (_event, { config }) => {
    await workspace.saveConfig(config);
    sidecar.setEnv(buildSidecarEnv(config));
    await sidecar.restart();
  });
}

app.whenReady().then(async () => {
  attachSidecarListeners();
  await ensureDesktopReady();
  registerIpc();
  await createMainWindow();

  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createMainWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async () => {
  await sidecar.shutdown();
});
