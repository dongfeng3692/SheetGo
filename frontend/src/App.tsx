import type { Component } from "solid-js";
import { Show, createEffect, createMemo, createSignal, onMount } from "solid-js";
import FilePanel from "./components/FilePanel";
import ExcelPreview from "./components/ExcelPreview";
import ChatPanel from "./components/ChatPanel";
import Timeline from "./components/Timeline";
import Settings from "./components/Settings";
import PreloadProgress from "./components/PreloadProgress";
import WorkspaceDrawer from "./components/WorkspaceDrawer";
import { createSession, getConfig, getSnapshots, listFiles, listSessions } from "./lib/tauri-bridge";
import { fileState, selectFile, setFiles } from "./stores/fileStore";
import { sessionState, setActiveSessionId, setSessions, setSnapshots } from "./stores/sessionStore";

function applyTheme(theme: "light" | "dark" | "system") {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const shouldUseDark = theme === "dark" || (theme === "system" && prefersDark);
  document.documentElement.classList.toggle("dark", shouldUseDark);
}

const App: Component = () => {
  const [settingsOpen, setSettingsOpen] = createSignal(false);
  const [workspaceDrawerOpen, setWorkspaceDrawerOpen] = createSignal(false);

  onMount(async () => {
    try {
      const config = await getConfig();
      applyTheme(config.ui.theme);
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
        return;
      }

      const files = await listFiles(initialSession.sessionId);
      setFiles(files);
      selectFile(files[0]?.fileId ?? null);
    } catch (error) {
      console.error("App init failed:", error);
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
    <div class="app-shell">
      <a class="skip-link" href="#workspace-main">
        跳到主工作区
      </a>
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
          <Show when={activePreload()}>
            {(progress) => (
              <div class="topbar-meta">
                <span class="subtle-pill accent">导入中 {Math.round(progress().progress)}%</span>
              </div>
            )}
          </Show>

          <div class="topbar-utilities" classList={{ "ml-auto": !activePreload() }}>
            <Show when={activeFile()}>
              <span class="subtle-pill">
                {activeFile()!.sheets.length || 1} 张表 · {activeFile()!.totalRows.toLocaleString()} 行
              </span>
            </Show>
            <button class="soft-btn" onClick={() => setSettingsOpen(true)}>
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
  );
};

export default App;
