import type {
  AppConfig,
  ChatRequest,
  ChatResponse,
  FileChangeInfo,
  FileInfo,
  HistoryEntry,
  PreloadProgress,
  RollbackResult,
  Session,
  SnapshotInfo,
  StreamEvent,
  UploadResult,
} from "./lib/tauri";

interface SheetGoDesktopApi {
  pickExcelFile: () => Promise<string | null>;
  uploadFile: (path: string, sessionId: string) => Promise<UploadResult>;
  listFiles: (sessionId: string) => Promise<FileInfo[]>;
  removeFile: (fileId: string, sessionId: string) => Promise<void>;
  getFileInfo: (fileId: string, sessionId: string) => Promise<FileInfo>;
  getFileBytes: (fileId: string, sessionId: string) => Promise<string>;
  sendMessage: (req: ChatRequest) => Promise<ChatResponse>;
  sendMessageStream: (req: ChatRequest) => Promise<string>;
  stopGeneration: () => Promise<void>;
  confirmToolCall: (callId: string) => Promise<void>;
  listSessions: () => Promise<Session[]>;
  createSession: (name: string) => Promise<Session>;
  deleteSession: (sessionId: string) => Promise<void>;
  rollbackSnapshot: (snapshotId: string) => Promise<RollbackResult>;
  getSnapshots: (sessionId: string, fileId: string) => Promise<SnapshotInfo[]>;
  getHistory: (sessionId: string) => Promise<HistoryEntry[]>;
  getConfig: () => Promise<AppConfig>;
  saveConfig: (config: AppConfig) => Promise<void>;
  onChatStream: (callback: (event: StreamEvent) => void) => () => void;
  onPreloadProgress: (callback: (progress: PreloadProgress) => void) => () => void;
  onFileChanged: (callback: (info: FileChangeInfo) => void) => () => void;
}

declare global {
  interface Window {
    sheetgoDesktop?: SheetGoDesktopApi;
  }
}

export {};
