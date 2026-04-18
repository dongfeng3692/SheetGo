import type { Component } from "solid-js";
import { Show, createEffect, createMemo, createSignal, onMount } from "solid-js";
import FilePanel from "./components/FilePanel";
import ExcelPreview from "./components/ExcelPreview";
import ChatPanel from "./components/ChatPanel";
import Timeline from "./components/Timeline";
import Settings from "./components/Settings";
import ParseInspector from "./components/ParseInspector";
import PreloadProgress from "./components/PreloadProgress";
import WorkspaceDrawer from "./components/WorkspaceDrawer";
import LaunchScreen from "./components/LaunchScreen";
import { createSession, getConfig, getSnapshots, listFiles, listSessions } from "./lib/tauri-bridge";
import { applyUiTheme } from "./lib/themes";
import { fileState, selectFile, setFiles } from "./stores/fileStore";
import { closeParseInspector, inspectorState, openParseInspector } from "./stores/inspectorStore";
import { sessionState, setActiveSessionId, setSessions, setSnapshots } from "./stores/sessionStore";

const App: Component = () => {
  const [settingsOpen, setSettingsOpen] = createSignal(false);
  const [workspaceDrawerOpen, setWorkspaceDrawerOpen] = createSignal(false);
  const [bootVisible, setBootVisible] = createSignal(true);
  const [bootClosing, setBootClosing] = createSignal(false);

  const wait = (ms: number) =>
    new Promise<void>((resolve) => {
      window.setTimeout(resolve, ms);
    });

  onMount(async () => {
    const bootStartedAt = performance.now();
    const bootTotalDuration = 3500;
    const bootExitDuration = 620;

    try {
      const config = await getConfig();
      applyUiTheme(config.ui);
    } catch (error) {
      console.error("Failed to load config:", error);
    }

    try {
      let sessions = await listSessions();
      if (sessions.length === 0) {
        sessions = [await createSession("工作区 1")];
      }

      setSessions(sessions);
      const initialSession = sessions[0] ?? null;
      setActiveSessionId(initialSession?.sessionId ?? null);

      if (!initialSession) {
        setFiles([]);
        selectFile(null);
      } else {
        const files = await listFiles(initialSession.sessionId);
        setFiles(files);
        selectFile(files[0]?.fileId ?? null);
      }
    } catch (error) {
      console.error("App init failed:", error);
    } finally {
      const elapsed = performance.now() - bootStartedAt;
      const remainingShowTime = bootTotalDuration - bootExitDuration - elapsed;
      if (remainingShowTime > 0) {
        await wait(remainingShowTime);
      }

      setBootClosing(true);
      await wait(bootExitDuration);
      setBootVisible(false);
    }
  });

  createEffect(() => {
    const sessionId = sessionState.activeSessionId;
    const fileId = fileState.activeFileId;
    if (!sessionId || !fileId) {
      setSnapshots([]);
      return;
    }

    void getSnapshots(sessionId, fileId)
      .then((snapshots) => setSnapshots(snapshots))
      .catch((error) => {
        console.error("Failed to load snapshots:", error);
        setSnapshots([]);
      });
  });

  const activePreload = createMemo(() => {
    const entries = Object.values(fileState.preloadStatus).filter(
      (item): item is NonNullable<(typeof fileState.preloadStatus)[string]> => Boolean(item)
    );
    return entries.length > 0 ? entries[entries.length - 1] : null;
  });

  const preloadFile = createMemo(() =>
    fileState.files.find((file) => file.fileId === activePreload()?.fileId)
  );

  const activeFile = createMemo(() =>
    fileState.files.find((file) => file.fileId === fileState.activeFileId)
  );

  return (
    <>
      <div class="app-shell" classList={{ booting: bootVisible() }}>
        <a class="skip-link" href="#workspace-main">
          跳到主工作区
        </a>
        <div class="window-drag-strip" aria-hidden="true" />
        <div class="app-backdrop" />

        <aside class="sidebar-shell app-entrance stage-2" aria-label="文件导航">
          <FilePanel
            workspaceDrawerOpen={workspaceDrawerOpen()}
            onToggleWorkspaceDrawer={() => setWorkspaceDrawerOpen((open) => !open)}
          />
        </aside>

        <WorkspaceDrawer
          open={workspaceDrawerOpen()}
          onClose={() => setWorkspaceDrawerOpen(false)}
        />

        <main class="workspace-shell" id="workspace-main" tabIndex={-1}>
          <header class="topbar-shell app-entrance stage-3">
            <div class="min-w-0 flex flex-1 flex-col gap-2">
              <div class="topbar-copy">
                <div class="panel-kicker">当前文件</div>
                <h1 class="topbar-title">
                  {activeFile()?.fileName ?? "Excel 工作台"}
                </h1>
                <div class="topbar-note">
                  <Show
                    when={activeFile()}
                    fallback={"导入一个工作簿后，就能在预览、对话和回滚之间直接联动处理。"}
                  >
                    {(file) =>
                      `${Math.max(file().sheets.length, 1)} 张表 · ${file().totalRows.toLocaleString()} 行 · 右侧可直接提要求修改`
                    }
                  </Show>
                </div>
              </div>

              <Show when={activePreload()}>
                {(progress) => (
                  <div class="topbar-meta">
                    <span class="subtle-pill accent">导入中 {Math.round(progress().progress)}%</span>
                  </div>
                )}
              </Show>
            </div>

            <div class="topbar-utilities">
              <Show when={activeFile()}>
                <span class="subtle-pill">
                  {activeFile()!.sheets.length || 1} 张表 · {activeFile()!.totalRows.toLocaleString()} 行
                </span>
              </Show>
              <Show when={activeFile()}>
                <button
                  class="soft-btn"
                  onClick={() => {
                    setSettingsOpen(false);
                    openParseInspector();
                  }}
                >
                  解析结果
                </button>
              </Show>
              <button
                class="soft-btn"
                onClick={() => {
                  closeParseInspector();
                  setSettingsOpen(true);
                }}
              >
                偏好设置
              </button>
            </div>
          </header>

          <div class="workspace-grid app-entrance stage-4">
            <section class="min-h-0">
              <ExcelPreview />
            </section>

            <aside class="assistant-column" aria-label="助手与变更记录">
              <ChatPanel />
              <Timeline />
            </aside>
          </div>
        </main>

        <Settings open={settingsOpen} onClose={() => setSettingsOpen(false)} />
        <ParseInspector open={() => inspectorState.parseInspectorOpen} onClose={closeParseInspector} />

        <Show when={activePreload()}>
          {(progress) => (
            <PreloadProgress
              fileName={preloadFile()?.fileName}
              progress={progress().progress}
              stage={progress().stage}
              message={progress().message}
            />
          )}
        </Show>
      </div>

      <Show when={bootVisible()}>
        <LaunchScreen closing={bootClosing()} />
      </Show>
    </>
  );
};

export default App;
