import type { Component } from "solid-js";
import { Show, createEffect, createMemo, createSignal, onCleanup } from "solid-js";
import { createUniver, LocaleType, defaultTheme } from "@univerjs/presets";
import type { IWorkbookData } from "@univerjs/presets";
import { UniverSheetsCorePreset } from "@univerjs/presets/preset-sheets-core";
import LocaleZhCN from "@univerjs/preset-sheets-core/lib/es/locales/zh-CN";
import { fileState, selectFile, setActiveSheet, setFiles } from "../stores/fileStore";
import { sessionState } from "../stores/sessionStore";
import { getFileBytes, listFiles, saveWorkbookEdits } from "../lib/tauri-bridge";
import { buildWorkbookCellEdits, getSheetNames, parseExcelToUniver } from "../lib/sheetjs";
import "@univerjs/presets/lib/styles/preset-sheets-core.css";

interface DisposableLike {
  dispose: () => void;
}

interface UniverInstance {
  univer: { dispose: () => void };
  univerAPI: any;
  commandListener?: DisposableLike | null;
}

const ExcelPreview: Component = () => {
  const [workbookData, setWorkbookData] = createSignal<IWorkbookData | null>(null);
  const [loading, setLoading] = createSignal(false);
  const [loadError, setLoadError] = createSignal<string | null>(null);
  const [saving, setSaving] = createSignal(false);
  const [saveStatus, setSaveStatus] = createSignal<string | null>(null);

  let containerRef: HTMLDivElement | undefined;
  let univerInstance: UniverInstance | null = null;
  let statusTimer: ReturnType<typeof setTimeout> | undefined;
  let workbookLoadVersion = 0;

  const activeFile = createMemo(() =>
    fileState.files.find((file) => file.fileId === fileState.activeFileId)
  );
  const previewTitle = createMemo(() => activeFile()?.fileName ?? "未选择工作簿");

  const normalizeUiError = (errorValue: unknown, fallback = "发生未知错误，请稍后重试。") => {
    const raw =
      errorValue instanceof Error
        ? errorValue.message
        : typeof errorValue === "string"
          ? errorValue
          : errorValue
            ? String(errorValue)
            : "";

    return (
      raw
        .replace(/^Error:\s*/i, "")
        .replace(/^(?:Internal error|RuntimeError|ValueError|TypeError):\s*/i, "")
        .trim() || fallback
    );
  };

  const updateSaveStatus = (message: string | null, timeout = 2600) => {
    if (statusTimer) {
      clearTimeout(statusTimer);
      statusTimer = undefined;
    }

    setSaveStatus(message);
    if (message) {
      statusTimer = setTimeout(() => {
        setSaveStatus(null);
        statusTimer = undefined;
      }, timeout);
    }
  };

  const syncActiveSheetFromUniver = () => {
    const sheetName = univerInstance?.univerAPI.getActiveWorkbook?.()?.getActiveSheet()?.getSheetName?.();
    if (sheetName && sheetName !== fileState.activeSheet) {
      setActiveSheet(sheetName);
    }
  };

  const loadWorkbook = async (fileId: string, sessionId: string) => {
    const loadVersion = ++workbookLoadVersion;
    setLoading(true);
    setLoadError(null);

    try {
      let base64: string;

      try {
        base64 = await getFileBytes(fileId, sessionId);
      } catch (error) {
        const message = normalizeUiError(error);

        if (!/file not found/i.test(message)) {
          throw error;
        }

        const files = await listFiles(sessionId);
        if (loadVersion !== workbookLoadVersion) {
          return;
        }

        setFiles(files);

        const refreshedFile = files.find((file) => file.fileId === fileId);
        if (!refreshedFile) {
          if (fileState.activeFileId === fileId) {
            selectFile(files[0]?.fileId ?? null);
          }
          setLoadError(files.length > 0 ? "文件列表已刷新，请重新选择要预览的文件。" : "当前工作区还没有可预览的文件。");
          return;
        }

        base64 = await getFileBytes(fileId, sessionId);
      }

      if (
        loadVersion !== workbookLoadVersion ||
        sessionState.activeSessionId !== sessionId ||
        fileState.activeFileId !== fileId
      ) {
        return;
      }

      const data = parseExcelToUniver(base64);
      setWorkbookData(data);

      const sheetNames = getSheetNames(data);
      if (sheetNames.length > 0 && !sheetNames.includes(fileState.activeSheet)) {
        setActiveSheet(sheetNames[0]);
      }
    } catch (error) {
      if (
        loadVersion !== workbookLoadVersion ||
        sessionState.activeSessionId !== sessionId ||
        fileState.activeFileId !== fileId
      ) {
        return;
      }
      console.error("Failed to load Excel preview:", error);
      setLoadError(normalizeUiError(error));
    } finally {
      if (loadVersion === workbookLoadVersion) {
        setLoading(false);
      }
    }
  };

  const initUniver = (data: IWorkbookData) => {
    destroyUniver();

    if (!containerRef) {
      return;
    }

    const { univer, univerAPI } = createUniver({
      locale: LocaleType.ZH_CN,
      theme: defaultTheme,
      locales: {
        [LocaleType.ZH_CN]: LocaleZhCN as any,
      },
      presets: [
        UniverSheetsCorePreset({
          container: "univer-container",
        }),
      ],
    });

    const nextInstance: UniverInstance = { univer, univerAPI, commandListener: null };
    univerInstance = nextInstance;
    univerAPI.createUniverSheet(data);

    const workbook = univerAPI.getActiveWorkbook?.();
    if (workbook && fileState.activeSheet) {
      const targetSheet = workbook.getSheetByName(fileState.activeSheet);
      if (targetSheet) {
        workbook.setActiveSheet(targetSheet);
      }
    }

    if (univerAPI.addEvent && univerAPI.Event?.CommandExecuted) {
      nextInstance.commandListener = univerAPI.addEvent(
        univerAPI.Event.CommandExecuted,
        () => syncActiveSheetFromUniver()
      );
    }

    syncActiveSheetFromUniver();
  };

  const destroyUniver = () => {
    if (univerInstance) {
      try {
        univerInstance.commandListener?.dispose();
        univerInstance.univer.dispose();
      } catch {
        // Ignore cleanup errors from the third-party renderer.
      }
      univerInstance = null;
    }

    if (containerRef) {
      containerRef.innerHTML = "";
    }
  };

  createEffect(() => {
    const file = activeFile();
    const sessionId = sessionState.activeSessionId;

    if (!file || !sessionId) {
      workbookLoadVersion += 1;
      setWorkbookData(null);
      setLoadError(null);
      updateSaveStatus(null);
      destroyUniver();
      return;
    }

    updateSaveStatus(null);
    void loadWorkbook(file.fileId, sessionId);
  });

  createEffect(() => {
    const data = workbookData();
    if (data && containerRef) {
      initUniver(data);
    }
  });

  createEffect(() => {
    const targetSheet = fileState.activeSheet;
    const workbook = univerInstance?.univerAPI.getActiveWorkbook?.();
    if (!targetSheet || !workbook) {
      return;
    }

    const nextSheet = workbook.getSheetByName(targetSheet);
    const currentSheet = workbook.getActiveSheet()?.getSheetName?.();
    if (nextSheet && currentSheet !== targetSheet) {
      workbook.setActiveSheet(nextSheet);
    }
  });

  const handleSave = async () => {
    const fileId = fileState.activeFileId;
    const sessionId = sessionState.activeSessionId;
    const originalWorkbook = workbookData();
    const workbook = univerInstance?.univerAPI.getActiveWorkbook?.();

    if (!fileId || !sessionId || !originalWorkbook || !workbook) {
      return;
    }

    setSaving(true);
    updateSaveStatus(null);

    try {
      const edits = buildWorkbookCellEdits(originalWorkbook, workbook.save());
      if (edits.length === 0) {
        updateSaveStatus("当前没有需要保存的修改。");
        return;
      }

      const result = await saveWorkbookEdits(fileId, sessionId, edits);
      const files = await listFiles(sessionId);
      setFiles(files);
      await loadWorkbook(fileId, sessionId);

      if (!result.saved) {
        updateSaveStatus("保存没有完成，请稍后重试。", 3600);
        return;
      }

      const warnings = result.warnings.filter(Boolean);
      if (warnings.length > 0) {
        updateSaveStatus(warnings[0], 4200);
        return;
      }

      updateSaveStatus(`已保存 ${result.editCount} 处修改。`);
    } catch (error) {
      console.error("Failed to save workbook edits:", error);
      updateSaveStatus(normalizeUiError(error, "保存失败。"), 4200);
    } finally {
      setSaving(false);
    }
  };

  onCleanup(() => {
    if (statusTimer) {
      clearTimeout(statusTimer);
    }
    destroyUniver();
  });

  return (
    <section class="flex h-full min-h-0 flex-col overflow-hidden">
      <Show
        when={activeFile()}
        fallback={
          <div class="surface-muted flex h-full flex-col items-center justify-center gap-5 px-8 text-center">
            <div class="preview-placeholder-stack" aria-hidden="true">
              <span class="preview-placeholder-sheet back" />
              <span class="preview-placeholder-sheet middle" />
              <span class="preview-placeholder-sheet front" />
            </div>
            <div class="space-y-2">
              <div class="panel-kicker">主画布</div>
              <h3 class="text-[1.5rem] font-semibold tracking-tight text-[var(--text-primary)]">
                先导入一个工作簿
              </h3>
              <p class="max-w-xl text-[0.94rem] leading-7 text-[var(--text-secondary)]">
                表格会固定在这里显示，避免在预览、对话和变更记录之间来回切换。
              </p>
            </div>
          </div>
        }
      >
        <div class="preview-stage h-full">
          <div class="preview-stage-bar">
            <div class="preview-window-controls" aria-hidden="true">
              <span class="preview-window-dot red" />
              <span class="preview-window-dot amber" />
              <span class="preview-window-dot green" />
            </div>
            <div class="preview-stage-title">
              <span class="preview-stage-kicker">主预览区</span>
              <span class="preview-stage-separator">/</span>
              <span class="preview-stage-file">{previewTitle()}</span>
            </div>
            <div class="preview-stage-actions">
              <Show when={saveStatus()}>
                {(message) => <span class="preview-stage-status">{message()}</span>}
              </Show>
              <button
                class="soft-btn-primary preview-save-btn"
                onClick={() => void handleSave()}
                disabled={loading() || saving() || Boolean(loadError())}
              >
                {saving() ? "保存中..." : "保存修改"}
              </button>
            </div>
          </div>

          <div class="min-h-0 flex-1 px-2 pb-2">
            <div class="h-full overflow-hidden rounded-[20px] border border-[var(--border-subtle)] bg-white shadow-[0_1px_0_rgba(255,255,255,0.72)_inset]">
              <Show when={loading()}>
                <div class="flex h-full items-center justify-center gap-3 text-sm text-[var(--text-secondary)]">
                  <span class="loading-dot" />
                  正在加载工作簿预览...
                </div>
              </Show>

              <Show when={loadError()}>
                <div class="flex h-full items-center justify-center px-8 text-center text-sm leading-7 text-[var(--warning-text)]">
                  {loadError()}
                </div>
              </Show>

              <div
                ref={containerRef}
                id="univer-container"
                class="h-full bg-white"
                style={{
                  display: workbookData() && !loading() && !loadError() ? "block" : "none",
                }}
              />
            </div>
          </div>
        </div>
      </Show>
    </section>
  );
};

export default ExcelPreview;
