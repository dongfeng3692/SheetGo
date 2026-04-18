const crypto = require("crypto");
const fs = require("fs");
const fsp = require("fs/promises");
const os = require("os");
const path = require("path");

const DEFAULT_CONFIG = {
  llm: {
    provider: "openai",
    model: "gpt-4o",
    apiKey: "",
    baseUrl: "",
    temperature: 0.1,
    maxTokens: 4096,
  },
  ui: {
    theme: "light",
    themePreset: "default",
    language: "zh-CN",
    previewRows: 100,
  },
  advanced: {
    maxFileSize: 104857600,
    preloadSampleRows: 20,
    snapshotMaxCount: 50,
    sandboxEnabled: true,
  },
};

function configPath() {
  return path.join(baseDir(), "config.json");
}

function apiKeyPath() {
  return path.join(baseDir(), "llm-api-key.txt");
}

function historyPath(sessionDir) {
  return path.join(sessionDir, "history.json");
}

function fileMetaPath(cacheDir, fileId) {
  return path.join(cacheDir, `${fileId}_meta.json`);
}

function baseDir() {
  return path.join(os.homedir(), ".sheetgo");
}

function workspaceRoot() {
  return path.join(baseDir(), "workspace");
}

function dbPath() {
  return path.join(baseDir(), "sheetgo.db");
}

async function initWorkspace() {
  await fsp.mkdir(workspaceRoot(), { recursive: true });
  return baseDir();
}

async function getSession(sessionId) {
  const basePath = path.join(workspaceRoot(), sessionId);
  const session = {
    baseDir: basePath,
    sourceDir: path.join(basePath, "source"),
    workingDir: path.join(basePath, "working"),
    cacheDir: path.join(basePath, "cache"),
    snapshotDir: path.join(basePath, "snapshots"),
    exportDir: path.join(basePath, "exports"),
  };

  await Promise.all([
    fsp.mkdir(session.sourceDir, { recursive: true }),
    fsp.mkdir(session.workingDir, { recursive: true }),
    fsp.mkdir(session.cacheDir, { recursive: true }),
    fsp.mkdir(session.snapshotDir, { recursive: true }),
    fsp.mkdir(session.exportDir, { recursive: true }),
  ]);

  return session;
}

async function createSession(name = "New Session") {
  const sessionId = crypto.randomUUID();
  const session = await getSession(sessionId);
  const meta = {
    sessionId,
    name,
    createdAt: nowSeconds(),
    updatedAt: nowSeconds(),
  };
  await writeSessionMeta(session.baseDir, meta);
  return meta;
}

async function listSessions() {
  await initWorkspace();
  const entries = await fsp.readdir(workspaceRoot(), { withFileTypes: true });
  const sessions = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const sessionId = entry.name;
    const sessionDir = path.join(workspaceRoot(), sessionId);
    const meta = await readSessionMeta(sessionId, sessionDir);
    sessions.push(meta);
  }

  sessions.sort((a, b) => (b.updatedAt || b.createdAt) - (a.updatedAt || a.createdAt));
  return sessions;
}

async function deleteSession(sessionId) {
  const sessionDir = path.join(workspaceRoot(), sessionId);
  await fsp.rm(sessionDir, { recursive: true, force: true });
}

async function importFile(sessionId, sourcePath) {
  const session = await getSession(sessionId);
  const originalName = path.basename(sourcePath);
  const parsed = path.parse(originalName);
  const safeStem = sanitizeStem(parsed.name);
  const ext = parsed.ext || ".xlsx";
  const shortId = crypto.randomUUID().split("-")[0];
  const fileId = `${safeStem}_${shortId}`;
  const destName = `${fileId}${ext}`;
  const sourceDest = path.join(session.sourceDir, destName);
  const workingDest = path.join(session.workingDir, destName);

  await fsp.copyFile(sourcePath, sourceDest);
  await fsp.copyFile(sourcePath, workingDest);
  await writeFileMeta(session.cacheDir, fileId, {
    fileId,
    fileName: originalName,
    importedAt: Date.now(),
  });
  await touchSession(sessionId);

  return {
    fileId,
    fileName: originalName,
    sourcePath: sourceDest,
    workingPath: workingDest,
    session,
  };
}

function cachePath(session, fileId, suffix) {
  return path.join(session.cacheDir, `${fileId}_${suffix}`);
}

async function listFiles(sessionId) {
  const session = await getSession(sessionId);
  const entries = await fsp.readdir(session.workingDir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    if (!entry.isFile()) {
      continue;
    }
    const ext = path.extname(entry.name).toLowerCase();
    if (ext !== ".xlsx" && ext !== ".xlsm") {
      continue;
    }

    const fileId = path.basename(entry.name, ext);
    const { sheets, totalRows } = await readSchema(session.cacheDir, fileId);
    const meta = await readFileMeta(session.cacheDir, fileId);
    const fullPath = path.join(session.workingDir, entry.name);
    const stats = await fsp.stat(fullPath);
    files.push({
      fileId,
      fileName: meta.fileName || entry.name,
      sheets,
      totalRows,
      importedAt: normalizeTimestamp(meta.importedAt, Math.floor(stats.mtimeMs)),
    });
  }

  return files
    .sort((a, b) => (b.importedAt || 0) - (a.importedAt || 0))
    .map(({ importedAt: _importedAt, ...file }) => file);
}

async function getFileInfo(fileId, sessionId) {
  const session = await getSession(sessionId);
  const workingPath = await findWorkingFile(fileId, session);
  if (!workingPath) {
    throw new Error("File not found");
  }
  const { sheets, totalRows } = await readSchema(session.cacheDir, fileId);
  const meta = await readFileMeta(session.cacheDir, fileId);
  return {
    fileId,
    fileName: meta.fileName || path.basename(workingPath),
    sheets,
    totalRows,
  };
}

async function getFileBytes(fileId, sessionId) {
  const session = await getSession(sessionId);
  const workingPath = await findWorkingFile(fileId, session);
  if (!workingPath) {
    throw new Error("File not found");
  }
  const bytes = await fsp.readFile(workingPath);
  return bytes.toString("base64");
}

async function removeFile(fileId, sessionId) {
  const session = await getSession(sessionId);
  await Promise.all([
    removeMatching(session.sourceDir, fileId),
    removeMatching(session.workingDir, fileId),
    removeMatching(session.cacheDir, fileId),
  ]);
  await touchSession(sessionId);
}

async function exportFile(fileId, sessionId, destPath) {
  const session = await getSession(sessionId);
  const workingPath = await findWorkingFile(fileId, session);
  if (!workingPath) {
    throw new Error("File not found");
  }
  await fsp.copyFile(workingPath, destPath);
}

async function getConfig() {
  await initWorkspace();
  const configFile = configPath();
  const storedApiKey = await readApiKey();
  try {
    const content = JSON.parse(await fsp.readFile(configFile, "utf8"));
    const legacyApiKey = typeof content?.llm?.apiKey === "string" ? content.llm.apiKey : "";
    return {
      llm: {
        ...DEFAULT_CONFIG.llm,
        ...(content.llm || {}),
        apiKey: storedApiKey || legacyApiKey,
      },
      ui: {
        ...DEFAULT_CONFIG.ui,
        ...(content.ui || {}),
      },
      advanced: {
        ...DEFAULT_CONFIG.advanced,
        ...(content.advanced || {}),
      },
    };
  } catch {
    return {
      ...structuredClone(DEFAULT_CONFIG),
      llm: {
        ...structuredClone(DEFAULT_CONFIG).llm,
        apiKey: storedApiKey,
      },
    };
  }
}

async function saveConfig(config) {
  await initWorkspace();
  const configFile = configPath();
  const llmInput = config?.llm || {};
  const nextApiKey = typeof llmInput.apiKey === "string" ? llmInput.apiKey : "";
  const { apiKey: _apiKey, ...llmWithoutApiKey } = llmInput;
  const { apiKey: _defaultApiKey, ...defaultLlm } = DEFAULT_CONFIG.llm;
  const normalized = {
    llm: {
      ...defaultLlm,
      ...llmWithoutApiKey,
    },
    ui: {
      ...DEFAULT_CONFIG.ui,
      ...(config?.ui || {}),
    },
    advanced: {
      ...DEFAULT_CONFIG.advanced,
      ...(config?.advanced || {}),
    },
  };
  await Promise.all([
    fsp.writeFile(configFile, `${JSON.stringify(normalized, null, 2)}\n`, "utf8"),
    writeApiKey(nextApiKey),
  ]);
}

async function readApiKey() {
  try {
    return (await fsp.readFile(apiKeyPath(), "utf8")).trim();
  } catch {
    return "";
  }
}

async function writeApiKey(apiKey) {
  const normalized = typeof apiKey === "string" ? apiKey.trim() : "";
  const target = apiKeyPath();
  if (!normalized) {
    await fsp.rm(target, { force: true }).catch(() => {});
    return;
  }
  await fsp.writeFile(target, `${normalized}\n`, "utf8");
}

async function listSnapshots(sessionId, fileId) {
  const session = await getSession(sessionId);
  const entries = await fsp.readdir(session.snapshotDir, { withFileTypes: true });
  const snapshots = [];

  for (const entry of entries) {
    if (!entry.isFile() || path.extname(entry.name) !== ".json") {
      continue;
    }
    const fullPath = path.join(session.snapshotDir, entry.name);
    let raw = {};
    try {
      raw = JSON.parse(await fsp.readFile(fullPath, "utf8"));
    } catch {
      raw = {};
    }
    const stats = await fsp.stat(fullPath);
    const snapshotFileId = raw.fileId || raw.file_id || fileId;
    if (snapshotFileId !== fileId) {
      continue;
    }
    snapshots.push({
      snapshotId: raw.snapshotId || raw.id || path.basename(entry.name, ".json"),
      sessionId: raw.sessionId || raw.session_id || sessionId,
      fileId: snapshotFileId,
      description: raw.description || "Spreadsheet update",
      createdAt: normalizeTimestamp(raw.createdAt || raw.created_at, Math.floor(stats.mtimeMs / 1000)),
    });
  }

  snapshots.sort((a, b) => a.createdAt - b.createdAt);
  return snapshots;
}

async function rollbackSnapshot(snapshotId) {
  return {
    success: true,
    snapshotId,
  };
}

async function touchSession(sessionId) {
  const sessionDir = path.join(workspaceRoot(), sessionId);
  const meta = await readSessionMeta(sessionId, sessionDir);
  meta.updatedAt = nowSeconds();
  await writeSessionMeta(sessionDir, meta);
}

function normalizeHistoryCreatedAt(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 1e12 ? Math.floor(value) : Math.floor(value * 1000);
  }
  if (typeof value === "string") {
    const direct = Number(value);
    if (Number.isFinite(direct)) {
      return normalizeHistoryCreatedAt(direct);
    }
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }
  return Date.now();
}

function normalizeHistoryEntry(entry, fallbackIndex = 0) {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const role = entry.role;
  const content = typeof entry.content === "string" ? entry.content : "";
  if (!content.trim()) {
    return null;
  }

  if (role !== "user" && role !== "assistant" && role !== "system") {
    return null;
  }

  const messageId =
    typeof entry.messageId === "string" && entry.messageId.trim()
      ? entry.messageId.trim()
      : `history_${normalizeHistoryCreatedAt(entry.createdAt)}_${fallbackIndex}`;

  return {
    messageId,
    role,
    content,
    createdAt: normalizeHistoryCreatedAt(entry.createdAt),
  };
}

async function getHistory(sessionId) {
  const session = await getSession(sessionId);
  const filePath = historyPath(session.baseDir);

  try {
    const content = await fsp.readFile(filePath, "utf8");
    const raw = JSON.parse(content);
    const entries = Array.isArray(raw) ? raw : raw?.entries;
    if (!Array.isArray(entries)) {
      return [];
    }

    return entries
      .map((entry, index) => normalizeHistoryEntry(entry, index))
      .filter(Boolean)
      .sort((a, b) => a.createdAt - b.createdAt);
  } catch (error) {
    if (
      error &&
      typeof error === "object" &&
      (error.code === "ENOENT" || error.name === "SyntaxError")
    ) {
      return [];
    }
    throw error;
  }
}

async function saveHistory(sessionId, entries) {
  const session = await getSession(sessionId);
  const filePath = historyPath(session.baseDir);
  const normalizedEntries = Array.isArray(entries)
    ? entries
        .map((entry, index) => normalizeHistoryEntry(entry, index))
        .filter(Boolean)
    : [];

  if (normalizedEntries.length === 0) {
    await fsp.rm(filePath, { force: true }).catch(() => {});
    return;
  }

  await fsp.writeFile(
    filePath,
    `${JSON.stringify({ version: 1, entries: normalizedEntries }, null, 2)}\n`,
    "utf8"
  );
  await touchSession(sessionId);
}

async function readSessionMeta(sessionId, sessionDir = path.join(workspaceRoot(), sessionId)) {
  const metaFile = path.join(sessionDir, "session.json");
  try {
    const content = await fsp.readFile(metaFile, "utf8");
    const raw = JSON.parse(content);
    return {
      sessionId: raw.sessionId || sessionId,
      name: raw.name || sessionId,
      createdAt: normalizeTimestamp(raw.createdAt, nowSeconds()),
      updatedAt: normalizeTimestamp(raw.updatedAt, normalizeTimestamp(raw.createdAt, nowSeconds())),
    };
  } catch {
    const fallbackCreated = await getDirectoryCreatedAt(sessionDir);
    return {
      sessionId,
      name: sessionId,
      createdAt: fallbackCreated,
      updatedAt: fallbackCreated,
    };
  }
}

async function writeSessionMeta(sessionDir, meta) {
  await fsp.writeFile(
    path.join(sessionDir, "session.json"),
    `${JSON.stringify(meta, null, 2)}\n`,
    "utf8"
  );
}

async function readSchema(cacheDir, fileId) {
  const schemaFile = path.join(cacheDir, `${fileId}_schema.json`);
  try {
    const content = await fsp.readFile(schemaFile, "utf8");
    const raw = JSON.parse(content);
    const sheets = Array.isArray(raw.sheets)
      ? raw.sheets
          .map((sheet) => sheet?.name)
          .filter((name) => typeof name === "string")
      : [];
    const totalRows = Array.isArray(raw.sheets)
      ? raw.sheets.reduce((sum, sheet) => sum + Number(sheet?.rowCount || 0), 0)
      : 0;
    return { sheets, totalRows };
  } catch {
    return { sheets: [], totalRows: 0 };
  }
}

async function readFileMeta(cacheDir, fileId) {
  try {
    const content = await fsp.readFile(fileMetaPath(cacheDir, fileId), "utf8");
    const raw = JSON.parse(content);
    return {
      fileName: typeof raw.fileName === "string" ? raw.fileName : "",
      importedAt: normalizeTimestamp(raw.importedAt, 0),
    };
  } catch {
    return {
      fileName: "",
      importedAt: 0,
    };
  }
}

async function writeFileMeta(cacheDir, fileId, meta) {
  await fsp.writeFile(
    fileMetaPath(cacheDir, fileId),
    `${JSON.stringify(meta, null, 2)}\n`,
    "utf8"
  );
}

async function removeMatching(dir, fileId) {
  if (!fs.existsSync(dir)) {
    return;
  }
  const entries = await fsp.readdir(dir);
  await Promise.all(
    entries
      .filter((name) => name.startsWith(fileId))
      .map((name) => fsp.rm(path.join(dir, name), { force: true }))
  );
}

async function findWorkingFile(fileId, session) {
  const entries = await fsp.readdir(session.workingDir);
  const match = entries.find((name) => name.startsWith(`${fileId}.`) || path.basename(name, path.extname(name)) === fileId);
  return match ? path.join(session.workingDir, match) : null;
}

function sanitizeStem(name) {
  const normalized = name
    .trim()
    .replace(/[^\p{L}\p{N}_-]+/gu, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48);
  return normalized || "file";
}

function normalizeTimestamp(value, fallback) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 1e12 ? Math.floor(value / 1000) : Math.floor(value);
  }
  if (typeof value === "string") {
    const direct = Number(value);
    if (Number.isFinite(direct)) {
      return normalizeTimestamp(direct, fallback);
    }
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) {
      return Math.floor(parsed / 1000);
    }
  }
  return fallback;
}

async function getDirectoryCreatedAt(dir) {
  try {
    const stats = await fsp.stat(dir);
    return Math.floor(stats.birthtimeMs / 1000);
  } catch {
    return nowSeconds();
  }
}

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

module.exports = {
  baseDir,
  cachePath,
  createSession,
  dbPath,
  deleteSession,
  exportFile,
  getConfig,
  getFileBytes,
  getFileInfo,
  getHistory,
  getSession,
  importFile,
  initWorkspace,
  listFiles,
  listSessions,
  listSnapshots,
  readSchema,
  removeFile,
  rollbackSnapshot,
  saveHistory,
  saveConfig,
};
