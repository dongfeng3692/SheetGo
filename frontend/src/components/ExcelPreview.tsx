import type { Component } from "solid-js";
import { Show, createEffect, createMemo, createSignal, onCleanup } from "solid-js";
import { createUniver, LocaleType, defaultTheme } from "@univerjs/presets";
import type { IWorkbookData } from "@univerjs/presets";
import { UniverSheetsCorePreset } from "@univerjs/presets/preset-sheets-core";
import LocaleZhCN from "@univerjs/preset-sheets-core/lib/es/locales/zh-CN";
import { fileState, setActiveSheet } from "../stores/fileStore";
import { sessionState } from "../stores/sessionStore";
import { getFileBytes } from "../lib/tauri-bridge";
import { getSheetNames, parseExcelToUniver } from "../lib/sheetjs";
import "@univerjs/presets/lib/styles/preset-sheets-core.css";

interface UniverInstance {
  univer: { dispose: () => void };
  univerAPI: {
    createUniverSheet: (data: IWorkbookData) => unknown;
    disposeUnit: (id: string) => boolean;
  };
}

const ExcelPreview: Component = () => {
  const [workbookData, setWorkbookData] = createSignal<IWorkbookData | null>(null);
  const [loading, setLoading] = createSignal(false);
  const [loadError, setLoadError] = createSignal<string | null>(null);

  let containerRef: HTMLDivElement | undefined;
  let univerInstance: UniverInstance | null = null;

  const activeFile = createMemo(() =>
    fileState.files.find((file) => file.fileId === fileState.activeFileId)
  );
  const previewTitle = createMemo(() => activeFile()?.fileName ?? "未选择工作簿");

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

    univerInstance = { univer, univerAPI };
    univerAPI.createUniverSheet(data);
  };

  const destroyUniver = () => {
    if (univerInstance) {
      try {
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
    const fileId = fileState.activeFileId;
    const sessionId = sessionState.activeSessionId;

    if (!fileId || !sessionId) {
      setWorkbookData(null);
      setLoadError(null);
      destroyUniver();
      return;
    }

    const load = async () => {
      setLoading(true);
      setLoadError(null);

      try {
        const base64 = await getFileBytes(fileId, sessionId);
        const data = parseExcelToUniver(base64);
        setWorkbookData(data);

        const sheetNames = getSheetNames(data);
        if (sheetNames.length > 0 && !sheetNames.includes(fileState.activeSheet)) {
          setActiveSheet(sheetNames[0]);
        }
      } catch (error) {
        console.error("Failed to load Excel preview:", error);
        setLoadError(String(error));
      } finally {
        setLoading(false);
      }
    };

    void load();
  });

  createEffect(() => {
    const data = workbookData();
    if (data && containerRef) {
      initUniver(data);
    }
  });

  onCleanup(() => {
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
