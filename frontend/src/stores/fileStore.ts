import { createStore } from "solid-js/store";
import type { FileInfo, PreloadProgress } from "../lib/tauri-bridge";

export interface FileState {
  files: FileInfo[];
  activeFileId: string | null;
  activeSheet: string;
  isLoading: boolean;
  error: string | null;
  preloadStatus: Record<string, PreloadProgress | undefined>;
}

const [fileState, setFileState] = createStore<FileState>({
  files: [],
  activeFileId: null,
  activeSheet: "Sheet1",
  isLoading: false,
  error: null,
  preloadStatus: {},
});

export const setFiles = (files: FileInfo[]) => {
  setFileState("files", files);

  const activeFileId = fileState.activeFileId;
  if (!activeFileId) {
    if (files.length === 0) {
      setFileState("activeSheet", "Sheet1");
    }
    return;
  }

  const activeFile = files.find((file) => file.fileId === activeFileId);
  if (!activeFile) {
    setFileState("activeFileId", null);
    setFileState("activeSheet", "Sheet1");
    return;
  }

  if (activeFile.sheets.length > 0 && !activeFile.sheets.includes(fileState.activeSheet)) {
    setFileState("activeSheet", activeFile.sheets[0]);
  }
};
export const setActiveFileId = (id: string | null) =>
  setFileState("activeFileId", id);
export const setActiveSheet = (sheet: string) =>
  setFileState("activeSheet", sheet);
export const setFileLoading = (loading: boolean) =>
  setFileState("isLoading", loading);
export const setFileError = (error: string | null) =>
  setFileState("error", error);

export const updatePreloadProgress = (
  fileId: string,
  progress: PreloadProgress
) => {
  setFileState("preloadStatus", fileId, progress);
};

export const removePreloadProgress = (fileId: string) => {
  setFileState("preloadStatus", fileId, undefined);
};

export const selectFile = (fileId: string | null) => {
  setFileState("activeFileId", fileId);
  if (!fileId) {
    setFileState("activeSheet", "Sheet1");
    return;
  }
  const file = fileState.files.find((f) => f.fileId === fileId);
  if (file && file.sheets.length > 0) {
    setFileState("activeSheet", file.sheets[0]);
  }
};

export const removeFileFromStore = (fileId: string) => {
  setFileState("files", (prev) => prev.filter((f) => f.fileId !== fileId));
  if (fileState.activeFileId === fileId) {
    const nextFile = fileState.files.find((f) => f.fileId !== fileId) ?? null;
    selectFile(nextFile?.fileId ?? null);
  }
};

export { fileState };
