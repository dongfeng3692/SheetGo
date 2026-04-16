const { contextBridge, ipcRenderer } = require("electron");

function subscribe(channel, callback) {
  const listener = (_event, payload) => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

contextBridge.exposeInMainWorld("sheetgoDesktop", {
  pickExcelFile: () => ipcRenderer.invoke("desktop:pickExcelFile"),
  uploadFile: (path, sessionId) => ipcRenderer.invoke("desktop:uploadFile", { path, sessionId }),
  listFiles: (sessionId) => ipcRenderer.invoke("desktop:listFiles", { sessionId }),
  removeFile: (fileId, sessionId) => ipcRenderer.invoke("desktop:removeFile", { fileId, sessionId }),
  getFileInfo: (fileId, sessionId) => ipcRenderer.invoke("desktop:getFileInfo", { fileId, sessionId }),
  getFileBytes: (fileId, sessionId) => ipcRenderer.invoke("desktop:getFileBytes", { fileId, sessionId }),
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
  getConfig: () => ipcRenderer.invoke("desktop:getConfig"),
  saveConfig: (config) => ipcRenderer.invoke("desktop:saveConfig", { config }),
  onChatStream: (callback) => subscribe("chat-stream", callback),
  onPreloadProgress: (callback) => subscribe("preload-progress", callback),
  onFileChanged: (callback) => subscribe("file-changed", callback),
});
