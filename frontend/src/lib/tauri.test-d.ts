/**
 * Type-level tests for Tauri IPC bridge types.
 * This file is checked by TypeScript compiler but does not produce runtime output.
 */
import {
  pickExcelFile,
  uploadFile,
  listFiles,
  removeFile,
  getFileInfo,
  getFileBytes,
  sendMessage,
  sendMessageStream,
  stopGeneration,
  confirmToolCall,
  listSessions,
  createSession,
  deleteSession,
  rollbackSnapshot,
  getSnapshots,
  getHistory,
  saveHistory,
  getConfig,
  saveConfig,
  onChatStream,
  onPreloadProgress,
  onFileChanged,
  type UploadResult,
  type FileInfo,
  type FileChangeInfo,
  type ChatRequest,
  type ChatResponse,
  type Session,
  type SnapshotInfo,
  type RollbackResult,
  type HistoryEntry,
  type AppConfig,
  type StreamEvent,
  type PreloadProgress,
} from "./tauri";
import { expectType, type TypeEqual } from "ts-expect";

// UploadResult shape
expectType<TypeEqual<UploadResult["fileId"], string>>(true);
expectType<TypeEqual<UploadResult["fileName"], string>>(true);

// FileInfo shape
expectType<TypeEqual<FileInfo["sheets"], string[]>>(true);

// FileChangeInfo
expectType<TypeEqual<FileChangeInfo["changeType"], "modified" | "created" | "deleted">>(true);

// ChatRequest shape
expectType<TypeEqual<ChatRequest["sessionId"], string>>(true);
expectType<TypeEqual<ChatRequest["message"], string>>(true);

// ChatResponse shape
expectType<TypeEqual<ChatResponse["messageId"], string>>(true);
expectType<TypeEqual<ChatResponse["text"], string>>(true);

// Session shape
expectType<TypeEqual<Session["sessionId"], string>>(true);
expectType<TypeEqual<Session["createdAt"], number>>(true);

// SnapshotInfo
expectType<TypeEqual<SnapshotInfo["snapshotId"], string>>(true);

// RollbackResult
expectType<TypeEqual<RollbackResult["success"], boolean>>(true);

// HistoryEntry role
expectType<TypeEqual<HistoryEntry["role"], "user" | "assistant" | "system">>(true);

// AppConfig nested shape
expectType<TypeEqual<AppConfig["llm"]["provider"], string>>(true);
expectType<TypeEqual<AppConfig["ui"]["theme"], "light" | "dark" | "system">>(true);
expectType<TypeEqual<AppConfig["ui"]["themePreset"], "default" | "graphite" | "spruce" | "oled">>(true);

// Event types
expectType<TypeEqual<StreamEvent["type"], "text_delta" | "text_start" | "text_end" | "tool_call_start" | "tool_call_progress" | "tool_call_end" | "done" | "error">>(true);
expectType<TypeEqual<PreloadProgress["progress"], number>>(true);

// Functions exist and are callable (type-only)
export const _pickFile: typeof pickExcelFile = pickExcelFile;
export const _upload: typeof uploadFile = uploadFile;
export const _list: typeof listFiles = listFiles;
export const _remove: typeof removeFile = removeFile;
export const _info: typeof getFileInfo = getFileInfo;
export const _bytes: typeof getFileBytes = getFileBytes;
export const _send: typeof sendMessage = sendMessage;
export const _stream: typeof sendMessageStream = sendMessageStream;
export const _stop: typeof stopGeneration = stopGeneration;
export const _confirm: typeof confirmToolCall = confirmToolCall;
export const _listSessions: typeof listSessions = listSessions;
export const _createSession: typeof createSession = createSession;
export const _deleteSession: typeof deleteSession = deleteSession;
export const _rollback: typeof rollbackSnapshot = rollbackSnapshot;
export const _snapshots: typeof getSnapshots = getSnapshots;
export const _history: typeof getHistory = getHistory;
export const _saveHistory: typeof saveHistory = saveHistory;
export const _getConfig: typeof getConfig = getConfig;
export const _saveConfig: typeof saveConfig = saveConfig;
export const _onChat: typeof onChatStream = onChatStream;
export const _onPreload: typeof onPreloadProgress = onPreloadProgress;
export const _onFile: typeof onFileChanged = onFileChanged;
