import type { Component } from "solid-js";
import { fileState } from "../stores/fileStore";
import { formatSessionName } from "../lib/session-display";
import { sessionState } from "../stores/sessionStore";

const StatusBar: Component = () => {
  const activeFile = () =>
    fileState.files.find((file) => file.fileId === fileState.activeFileId);

  const activeSession = () =>
    sessionState.sessions.find((session) => session.sessionId === sessionState.activeSessionId);

  const activeSessionIndex = () =>
    sessionState.sessions.findIndex((session) => session.sessionId === sessionState.activeSessionId);

  return (
    <footer class="surface-muted flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-[13px] text-[var(--text-secondary)]">
      <div class="flex flex-wrap items-center gap-2.5">
        <span class="subtle-pill accent">本地模式</span>
        <span>{formatSessionName(activeSession()?.name, activeSessionIndex())}</span>
        <span class="hidden text-[var(--text-tertiary)] md:inline">/</span>
        <ShowFileInfo
          activeFile={activeFile()?.fileName}
          rows={activeFile()?.totalRows}
          sheets={activeFile()?.sheets.length}
        />
      </div>

      <div class="flex flex-wrap items-center gap-2.5">
        <span>{sessionState.snapshots.length} 条快照</span>
        <span>Solid + Electron + Python</span>
      </div>
    </footer>
  );
};

const ShowFileInfo: Component<{ activeFile?: string; rows?: number; sheets?: number }> = (props) => {
  if (!props.activeFile) {
    return <span>未选择工作簿</span>;
  }

  return (
    <span>
      {props.activeFile} · {props.sheets ?? 0} 张表 · {(props.rows ?? 0).toLocaleString()} 行
    </span>
  );
};

export default StatusBar;
