import type { Component } from "solid-js";
import { For, Show, createSignal } from "solid-js";
import { deleteSession, listFiles, listSessions, createSession } from "../lib/tauri-bridge";
import { fileState, selectFile, setFiles } from "../stores/fileStore";
import { sessionState, setActiveSessionId, setSessions } from "../stores/sessionStore";
import { formatSessionName } from "../lib/session-display";

interface WorkspaceDrawerProps {
  open: boolean;
  onClose: () => void;
}

const WorkspaceDrawer: Component<WorkspaceDrawerProps> = (props) => {
  const [errorMsg, setErrorMsg] = createSignal("");

  const activeSession = () =>
    sessionState.sessions.find((session) => session.sessionId === sessionState.activeSessionId);

  const activeSessionIndex = () =>
    sessionState.sessions.findIndex((session) => session.sessionId === sessionState.activeSessionId);

  const loadSessionFiles = async (sessionId: string) => {
    const files = await listFiles(sessionId);
    setFiles(files);
    selectFile(files[0]?.fileId ?? null);
  };

  const handleSwitchSession = async (sessionId: string) => {
    try {
      setActiveSessionId(sessionId);
      await loadSessionFiles(sessionId);
      props.onClose();
    } catch (error) {
      console.error("Failed to switch session:", error);
      setErrorMsg(`切换工作区失败：${String(error)}`);
    }
  };

  const handleNewSession = async () => {
    try {
      const session = await createSession(`工作区 ${sessionState.sessions.length + 1}`);
      const sessions = await listSessions();
      setSessions(sessions);
      setActiveSessionId(session.sessionId);
      setFiles([]);
      selectFile(null);
      props.onClose();
    } catch (error) {
      console.error("Failed to create session:", error);
      setErrorMsg(`创建工作区失败：${String(error)}`);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      const sessions = await listSessions();
      setSessions(sessions);

      if (sessionState.activeSessionId === sessionId) {
        const nextSession = sessions[0] ?? null;
        setActiveSessionId(nextSession?.sessionId ?? null);
        if (nextSession) {
          await loadSessionFiles(nextSession.sessionId);
        } else {
          setFiles([]);
          selectFile(null);
        }
      }
    } catch (error) {
      console.error("Failed to delete session:", error);
      setErrorMsg(`删除工作区失败：${String(error)}`);
    }
  };

  return (
    <>
      <Show when={props.open}>
        <button class="drawer-backdrop" aria-label="关闭工作区抽屉" onClick={props.onClose} />
      </Show>

      <aside class="workspace-drawer" classList={{ open: props.open }} aria-label="工作区切换抽屉">
        <div class="workspace-drawer-head">
          <div>
            <div class="section-kicker">工作区</div>
            <div class="section-title">
              {formatSessionName(activeSession()?.name, activeSessionIndex())}
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span class="subtle-pill">{sessionState.sessions.length} 个</span>
            <button class="soft-btn" onClick={handleNewSession}>
              新建
            </button>
            <button class="ghost-btn px-1.5 text-[var(--text-tertiary)]" onClick={props.onClose} aria-label="关闭工作区抽屉">
              ×
            </button>
          </div>
        </div>

        <div class="mt-4 space-y-2 overflow-auto">
          <For each={sessionState.sessions}>
            {(session, index) => (
              <div
                class="sidebar-item flex items-center justify-between gap-3"
                classList={{ active: session.sessionId === sessionState.activeSessionId }}
              >
                <button
                  class="min-w-0 flex-1 text-left"
                  aria-pressed={session.sessionId === sessionState.activeSessionId}
                  onClick={() => void handleSwitchSession(session.sessionId)}
                >
                  <div class="truncate text-sm font-medium text-[var(--text-primary)]">
                    {formatSessionName(session.name, index())}
                  </div>
                  <div class="mt-1 text-xs text-[var(--text-secondary)]">
                    {session.sessionId === sessionState.activeSessionId
                      ? `${fileState.files.length} 个文件`
                      : "点击切换"}
                  </div>
                </button>

                <Show when={sessionState.sessions.length > 1}>
                  <button
                    class="rounded-full p-1 text-[var(--text-tertiary)] transition hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]"
                    aria-label="删除工作区"
                    onClick={(event) => {
                      event.stopPropagation();
                      void handleDeleteSession(session.sessionId);
                    }}
                  >
                    <span class="block h-4 w-4 text-center leading-4">×</span>
                  </button>
                </Show>
              </div>
            )}
          </For>
        </div>

        <Show when={errorMsg()}>
          <div class="mt-4 rounded-2xl border border-[var(--border-strong)] bg-[var(--warning-soft)] px-3 py-2 text-xs text-[var(--warning-text)]">
            {errorMsg()}
          </div>
        </Show>
      </aside>
    </>
  );
};

export default WorkspaceDrawer;
