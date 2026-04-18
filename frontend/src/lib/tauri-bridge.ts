/**
 * Desktop API facade.
 * Browser → mock, Electron runtime → real IPC.
 */

// Re-export all types
export type {
  UploadResult,
  FileInfo,
  WorkbookCellEdit,
  SaveWorkbookResult,
  FileChangeInfo,
  ChatRequest,
  ToolCall,
  CellRange,
  ChatResponse,
  StreamEvent,
  PreloadProgress,
  DiagnosticsInfo,
  ParsedArtifacts,
  Session,
  SnapshotInfo,
  RollbackResult,
  HistoryEntry,
  AppConfig,
} from "./tauri";

const isDesktop = typeof window !== "undefined" && "sheetgoDesktop" in window;

// Dynamically resolved at runtime; typed to match the real module's public API
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let runtimeModule: any;

async function init() {
  runtimeModule = isDesktop
    ? await import("./tauri")
    : await import("./tauri.mock");
}

const ready = typeof window === "undefined" ? Promise.resolve() : init();

function wrap<T extends (...args: never[]) => Promise<unknown>>(fn: string) {
  return ((...args: Parameters<T>) => ready.then(() => runtimeModule[fn](...args))) as T;
}

export const isMock = !isDesktop;
export const pickExcelFile = wrap<typeof import("./tauri").pickExcelFile>("pickExcelFile");
export const uploadFile = wrap<typeof import("./tauri").uploadFile>("uploadFile");
export const listFiles = wrap<typeof import("./tauri").listFiles>("listFiles");
export const removeFile = wrap<typeof import("./tauri").removeFile>("removeFile");
export const getFileInfo = wrap<typeof import("./tauri").getFileInfo>("getFileInfo");
export const getFileBytes = wrap<typeof import("./tauri").getFileBytes>("getFileBytes");
export const saveWorkbookEdits = wrap<typeof import("./tauri").saveWorkbookEdits>("saveWorkbookEdits");
export const sendMessage = wrap<typeof import("./tauri").sendMessage>("sendMessage");
export const sendMessageStream = wrap<typeof import("./tauri").sendMessageStream>("sendMessageStream");
export const stopGeneration = wrap<typeof import("./tauri").stopGeneration>("stopGeneration");
export const confirmToolCall = wrap<typeof import("./tauri").confirmToolCall>("confirmToolCall");
export const listSessions = wrap<typeof import("./tauri").listSessions>("listSessions");
export const createSession = wrap<typeof import("./tauri").createSession>("createSession");
export const deleteSession = wrap<typeof import("./tauri").deleteSession>("deleteSession");
export const rollbackSnapshot = wrap<typeof import("./tauri").rollbackSnapshot>("rollbackSnapshot");
export const getSnapshots = wrap<typeof import("./tauri").getSnapshots>("getSnapshots");
export const getHistory = wrap<typeof import("./tauri").getHistory>("getHistory");
export const saveHistory = wrap<typeof import("./tauri").saveHistory>("saveHistory");
export const getConfig = wrap<typeof import("./tauri").getConfig>("getConfig");
export const saveConfig = wrap<typeof import("./tauri").saveConfig>("saveConfig");
export const getDiagnostics = wrap<typeof import("./tauri").getDiagnostics>("getDiagnostics");
export const readDesktopLog = wrap<typeof import("./tauri").readDesktopLog>("readDesktopLog");
export const openDesktopLog = wrap<typeof import("./tauri").openDesktopLog>("openDesktopLog");
export const openLogsDirectory = wrap<typeof import("./tauri").openLogsDirectory>("openLogsDirectory");
export const getParsedArtifacts = wrap<typeof import("./tauri").getParsedArtifacts>("getParsedArtifacts");
export const onChatStream = wrap<typeof import("./tauri").onChatStream>("onChatStream");
export const onPreloadProgress = wrap<typeof import("./tauri").onPreloadProgress>("onPreloadProgress");
export const onFileChanged = wrap<typeof import("./tauri").onFileChanged>("onFileChanged");
