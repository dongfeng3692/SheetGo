// ==================== Types ====================

export interface UploadResult {
  fileId: string;
  fileName: string;
  sheets: string[];
  totalRows: number;
}

export interface FileInfo {
  fileId: string;
  fileName: string;
  sheets: string[];
  totalRows: number;
}

export interface FileChangeInfo {
  fileId: string;
  changeType: "modified" | "created" | "deleted";
}

export interface ChatRequest {
  sessionId: string;
  fileId: string;
  message: string;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
}

export interface CellRange {
  sheet: string;
  start: string;
  end: string;
}

export interface ChatResponse {
  messageId: string;
  text: string;
  toolCalls?: ToolCall[];
  modifiedCells?: CellRange[];
}

export interface StreamEvent {
  type:
    | "text_delta"
    | "text_start"
    | "text_end"
    | "tool_call_start"
    | "tool_call_progress"
    | "tool_call_end"
    | "done"
    | "error";
  text?: string;
  full_text?: string;
  id?: string;
  name?: string;
  message?: string;
  error?: string;
  result?: string | null;
}

export interface PreloadProgress {
  fileId: string;
  stage: "reading" | "schema" | "stats" | "formula" | "done";
  progress: number;
  message?: string;
}

export interface Session {
  sessionId: string;
  name: string;
  createdAt: number;
}

export interface SnapshotInfo {
  snapshotId: string;
  sessionId: string;
  fileId: string;
  description: string;
  createdAt: number;
}

export interface RollbackResult {
  success: boolean;
  snapshotId: string;
}

export interface HistoryEntry {
  messageId: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: number;
}

export interface AppConfig {
  llm: {
    provider: string;
    model: string;
    apiKey: string;
    baseUrl: string;
    temperature: number;
    maxTokens: number;
  };
  ui: {
    theme: "light" | "dark" | "system";
    language: string;
    previewRows: number;
  };
  advanced: {
    maxFileSize: number;
    preloadSampleRows: number;
    snapshotMaxCount: number;
    sandboxEnabled: boolean;
  };
}

type UnlistenFn = () => void;

function getDesktopApi() {
  const api = window.sheetgoDesktop;
  if (!api) {
    throw new Error("Electron 桌面 API 不可用。");
  }
  return api;
}

// ==================== File Operations ====================

export const pickExcelFile = () => getDesktopApi().pickExcelFile();

export const uploadFile = (path: string, sessionId: string) =>
  getDesktopApi().uploadFile(path, sessionId);

export const listFiles = (sessionId: string) =>
  getDesktopApi().listFiles(sessionId);

export const removeFile = (fileId: string, sessionId: string) =>
  getDesktopApi().removeFile(fileId, sessionId);

export const getFileInfo = (fileId: string, sessionId: string) =>
  getDesktopApi().getFileInfo(fileId, sessionId);

export const getFileBytes = (fileId: string, sessionId: string) =>
  getDesktopApi().getFileBytes(fileId, sessionId);

// ==================== Agent Chat ====================

export const sendMessage = (req: ChatRequest) => getDesktopApi().sendMessage(req);

export const sendMessageStream = (req: ChatRequest) =>
  getDesktopApi().sendMessageStream(req);

export const stopGeneration = () => getDesktopApi().stopGeneration();

export const confirmToolCall = (callId: string) =>
  getDesktopApi().confirmToolCall(callId);

// ==================== Event Listeners ====================

export const onChatStream = (
  callback: (event: StreamEvent) => void
): Promise<UnlistenFn> => Promise.resolve(getDesktopApi().onChatStream(callback));

export const onPreloadProgress = (
  callback: (progress: PreloadProgress) => void
): Promise<UnlistenFn> =>
  Promise.resolve(getDesktopApi().onPreloadProgress(callback));

export const onFileChanged = (
  callback: (info: FileChangeInfo) => void
): Promise<UnlistenFn> => Promise.resolve(getDesktopApi().onFileChanged(callback));

// ==================== Session Operations ====================

export const listSessions = () => getDesktopApi().listSessions();

export const createSession = (name: string) => getDesktopApi().createSession(name);

export const deleteSession = (sessionId: string) =>
  getDesktopApi().deleteSession(sessionId);

export const rollbackSnapshot = (snapshotId: string) =>
  getDesktopApi().rollbackSnapshot(snapshotId);

export const getSnapshots = (sessionId: string, fileId: string) =>
  getDesktopApi().getSnapshots(sessionId, fileId);

export const getHistory = (sessionId: string) => getDesktopApi().getHistory(sessionId);

// ==================== Config ====================

export const getConfig = () => getDesktopApi().getConfig();

export const saveConfig = (config: AppConfig) => getDesktopApi().saveConfig(config);
