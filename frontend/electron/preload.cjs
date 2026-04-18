const { contextBridge, ipcRenderer } = require("electron");

function subscribe(channel, callback) {
  const listener = (_event, payload) => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

function normalizeForLog(value) {
  if (value instanceof Error) {
    return value.stack || value.message || String(value);
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function logRenderer(level, scope, message, details) {
  ipcRenderer.send("desktop:rendererLog", {
    level,
    scope,
    message: normalizeForLog(message),
    details,
  });
}

window.addEventListener("error", (event) => {
  logRenderer("error", "renderer.error", event.error || event.message || "Unknown renderer error", {
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
  });
});

window.addEventListener("unhandledrejection", (event) => {
  logRenderer("error", "renderer.unhandledrejection", event.reason || "Unhandled promise rejection");
});

contextBridge.exposeInMainWorld("sheetgoDesktop", {
  pickExcelFile: () => ipcRenderer.invoke("desktop:pickExcelFile"),
  uploadFile: (path, sessionId) => ipcRenderer.invoke("desktop:uploadFile", { path, sessionId }),
  listFiles: (sessionId) => ipcRenderer.invoke("desktop:listFiles", { sessionId }),
  removeFile: (fileId, sessionId) => ipcRenderer.invoke("desktop:removeFile", { fileId, sessionId }),
  getFileInfo: (fileId, sessionId) => ipcRenderer.invoke("desktop:getFileInfo", { fileId, sessionId }),
  getFileBytes: (fileId, sessionId) => ipcRenderer.invoke("desktop:getFileBytes", { fileId, sessionId }),
  saveWorkbookEdits: (fileId, sessionId, edits) =>
    ipcRenderer.invoke("desktop:saveWorkbookEdits", { fileId, sessionId, edits }),
  sendMessage: (req) => ipcRenderer.invoke("desktop:chat", req),
  sendMessageStream: (req) => ipcRenderer.invoke("desktop:chatStream", req),
  stopGeneration: () => ipcRenderer.invoke("desktop:stopChat"),
  confirmToolCall: (callId) => ipcRenderer.invoke("desktop:confirmToolCall", { callId }),
  listSessions: () => ipcRenderer.invoke("desktop:listSessions"),
  createSession: (name) => ipcRenderer.invoke("desktop:createSession", { name }),
  deleteSession: (sessionId) => ipcRenderer.invoke("desktop:deleteSession", { sessionId }),
  rollbackSnapshot: (snapshotId) => ipcRenderer.invoke("desktop:rollbackSnapshot", { snapshotId }),
  getSnapshots: (sessionId, fileId) => ipcRenderer.invoke("desktop:getSnapshots", { sessionId, fileId }),
  getHistory: (sessionId) => ipcRenderer.invoke("desktop:getHistory", { sessionId }),
  saveHistory: (sessionId, entries) => ipcRenderer.invoke("desktop:saveHistory", { sessionId, entries }),
  getConfig: () => ipcRenderer.invoke("desktop:getConfig"),
  saveConfig: (config) => ipcRenderer.invoke("desktop:saveConfig", { config }),
  getDiagnostics: () => ipcRenderer.invoke("desktop:getDiagnostics"),
  readDesktopLog: (limit) => ipcRenderer.invoke("desktop:readDesktopLog", { limit }),
  openDesktopLog: () => ipcRenderer.invoke("desktop:openDesktopLog"),
  openLogsDirectory: () => ipcRenderer.invoke("desktop:openLogsDirectory"),
  getParsedArtifacts: (fileId, sessionId) =>
    ipcRenderer.invoke("desktop:getParsedArtifacts", { fileId, sessionId }),
  onChatStream: (callback) => subscribe("chat-stream", callback),
  onPreloadProgress: (callback) => subscribe("preload-progress", callback),
  onFileChanged: (callback) => subscribe("file-changed", callback),
});
