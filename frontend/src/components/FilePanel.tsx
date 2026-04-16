import type { Component } from "solid-js";
import { For, Show, createSignal, onCleanup, onMount } from "solid-js";
import {
  fileState,
  removeFileFromStore,
  removePreloadProgress,
  selectFile,
  setFileLoading,
  setFiles,
  updatePreloadProgress,
} from "../stores/fileStore";
import { sessionState } from "../stores/sessionStore";
import {
  listFiles,
  onPreloadProgress,
  pickExcelFile,
  removeFile,
  uploadFile,
} from "../lib/tauri-bridge";
import { formatPreloadLabel } from "../lib/preload-display";

type NativeFile = File & { path?: string };

interface FilePanelProps {
  workspaceDrawerOpen?: boolean;
  onToggleWorkspaceDrawer?: () => void;
}

const FilePanel: Component<FilePanelProps> = (props) => {
  const [dragOver, setDragOver] = createSignal(false);
  const [errorMsg, setErrorMsg] = createSignal("");

  const hasSupportedExcelExtension = (filePath: string) => /\.(xlsx|xls|xlsm)$/i.test(filePath);

  onMount(() => {
    let dispose = () => {};
    void onPreloadProgress((progress) => {
      updatePreloadProgress(progress.fileId, progress);
      if (progress.stage === "done") {
        if (sessionState.activeSessionId) {
          void listFiles(sessionState.activeSessionId).then((files) => setFiles(files));
        }
        setTimeout(() => removePreloadProgress(progress.fileId), 1600);
      }
    }).then((unlisten) => {
      dispose = unlisten;
    });

    onCleanup(() => dispose());
  });

  const doUpload = async (filePath: string) => {
    const sessionId = sessionState.activeSessionId;
    if (!sessionId) {
      setErrorMsg("请先创建工作区，再导入文件。");
      return;
    }

    setFileLoading(true);
    setErrorMsg("");

    try {
      const uploaded = await uploadFile(filePath, sessionId);
      const files = await listFiles(sessionId);
      setFiles(files);
      selectFile(uploaded.fileId);
    } catch (error) {
      console.error("Upload failed:", error);
      setErrorMsg(`导入失败：${String(error)}`);
    } finally {
      setFileLoading(false);
    }
  };

  const handlePickFile = async () => {
    const filePath = await pickExcelFile();
    if (filePath) {
      await doUpload(filePath);
    }
  };

  const handleDrop = async (event: DragEvent) => {
    event.preventDefault();
    setDragOver(false);
    const droppedPaths = Array.from(event.dataTransfer?.files ?? [])
      .map((file) => (file as NativeFile).path)
      .filter((value): value is string => Boolean(value));

    const validPaths = droppedPaths.filter(hasSupportedExcelExtension);

    if (droppedPaths.length === 0) {
      setErrorMsg("没有读取到可导入的文件，请改用点击导入。");
      return;
    }

    if (validPaths.length === 0) {
      setErrorMsg("仅支持 `.xlsx`、`.xls` 或 `.xlsm` 文件。");
      return;
    }

    for (const filePath of validPaths) {
      await doUpload(filePath);
    }
  };

  const handleDeleteFile = async (fileId: string) => {
    const sessionId = sessionState.activeSessionId;
    if (!sessionId) {
      return;
    }

    try {
      await removeFile(fileId, sessionId);
      removeFileFromStore(fileId);
    } catch (error) {
      console.error("Failed to remove file:", error);
      setErrorMsg(`删除文件失败：${String(error)}`);
    }
  };

  return (
    <div class="surface-card sidebar-panel flex h-full flex-col gap-4 overflow-hidden px-4 py-4">
      <div class="flex items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <button
            type="button"
            class="brand-trigger"
            classList={{ active: props.workspaceDrawerOpen }}
            aria-label="切换工作区"
            aria-pressed={props.workspaceDrawerOpen}
            onClick={() => props.onToggleWorkspaceDrawer?.()}
          >
            <span class="brand-orb">E</span>
          </button>
          <div class="min-w-0">
            <div class="text-sm font-semibold tracking-tight text-[var(--text-primary)]">Exceler</div>
            <div class="mt-1 text-xs text-[var(--text-secondary)]">本地表格工作台</div>
          </div>
        </div>

        <Show when={fileState.isLoading}>
          <span class="loading-dot" />
        </Show>
      </div>

      <section class="sidebar-section flex min-h-0 flex-1 flex-col">
        <div class="sidebar-section-head">
          <div>
            <div class="section-kicker">文件库</div>
            <div class="section-title">{fileState.files.length} 个工作簿</div>
          </div>
        </div>

        <Show when={errorMsg()}>
          <div class="mt-3 rounded-2xl border border-[var(--border-strong)] bg-[var(--warning-soft)] px-3 py-2 text-xs text-[var(--warning-text)]">
            {errorMsg()}
          </div>
        </Show>

        <div class="mt-3 flex min-h-0 flex-1 flex-col">
          <div class="flex-1 space-y-2 overflow-auto pr-1">
            <Show
              when={fileState.files.length > 0}
              fallback={
                <div class="flex min-h-full flex-col justify-between gap-4">
                  <div class="flex flex-1 items-center justify-center px-3 text-center text-sm leading-6 text-[var(--text-secondary)]">
                    导入一个工作簿后，这里会固定展示当前工作区的文件列表。
                  </div>
                </div>
              }
            >
              <For each={fileState.files}>
                {(file) => {
                  const progress = () => fileState.preloadStatus[file.fileId];
                  return (
                    <div
                      class="file-card w-full text-left"
                      classList={{ active: fileState.activeFileId === file.fileId }}
                      role="button"
                      aria-pressed={fileState.activeFileId === file.fileId}
                      tabindex="0"
                      onClick={() => selectFile(file.fileId)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          selectFile(file.fileId);
                        }
                      }}
                    >
                      <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0 flex-1">
                          <div class="truncate text-sm font-medium text-[var(--text-primary)]">
                            {file.fileName}
                          </div>
                          <div class="file-card-meta mt-1.5">
                            {Math.max(file.sheets.length, 1)} 张表 · {file.totalRows.toLocaleString()} 行
                            <Show when={fileState.activeFileId === file.fileId}> · 当前</Show>
                          </div>
                        </div>

                        <button
                          class="rounded-full p-1 text-[var(--text-tertiary)] transition hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]"
                          onClick={(event) => {
                            event.stopPropagation();
                            void handleDeleteFile(file.fileId);
                          }}
                          aria-label="删除文件"
                        >
                          <span class="block h-4 w-4 text-center leading-4">×</span>
                        </button>
                      </div>

                      <Show when={progress()}>
                        <div class="mt-3 space-y-1.5">
                          <div class="h-1.5 overflow-hidden rounded-full bg-[var(--bg-muted)]">
                            <div
                              class="h-full rounded-full bg-[var(--accent-strong)] transition-all duration-300"
                              style={{ width: `${progress()!.progress}%` }}
                            />
                          </div>
                          <div class="text-[11px] text-[var(--text-secondary)]">
                            {formatPreloadLabel(progress()!.stage, progress()!.message)}
                          </div>
                        </div>
                      </Show>
                    </div>
                  );
                }}
              </For>
            </Show>
          </div>

          <div
            class="dropzone file-library-dropzone mt-3"
            classList={{ active: dragOver() }}
            role="button"
            tabindex="0"
            onClick={() => void handlePickFile()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                void handlePickFile();
              }
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(event) => void handleDrop(event)}
          >
            <div class="text-sm font-medium text-[var(--text-primary)]">拖入或选择 Excel 文件</div>
            <div class="mt-1 text-xs leading-6 text-[var(--text-secondary)]">
              支持 `.xlsx` / `.xls`，导入后会自动出现在上方列表。
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default FilePanel;
