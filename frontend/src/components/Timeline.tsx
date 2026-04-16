import type { Component } from "solid-js";
import { For, Show } from "solid-js";
import { fileState } from "../stores/fileStore";
import { sessionState, setSnapshots } from "../stores/sessionStore";
import { getSnapshots, rollbackSnapshot } from "../lib/tauri-bridge";

const Timeline: Component = () => {
  const handleRollback = async (snapshotId: string) => {
    try {
      await rollbackSnapshot(snapshotId);
      if (sessionState.activeSessionId && fileState.activeFileId) {
        const snapshots = await getSnapshots(
          sessionState.activeSessionId,
          fileState.activeFileId
        );
        setSnapshots(snapshots);
      }
    } catch (error) {
      console.error("Rollback failed:", error);
    }
  };

  const renderTimestamp = (value: number) =>
    new Date(value * 1000).toLocaleString("zh-CN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  return (
    <Show when={sessionState.snapshots.length > 0}>
      <section class="surface-card flex min-h-[184px] flex-col overflow-hidden">
        <header class="panel-header border-b border-[var(--border-subtle)] px-5 py-3.5">
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm font-semibold text-[var(--text-primary)]">最近变更</div>
            <span class="subtle-pill">{sessionState.snapshots.length} 条</span>
          </div>
        </header>

        <div class="min-h-0 flex-1 overflow-auto px-5 py-4">
          <div class="timeline-list space-y-3.5">
            <For each={sessionState.snapshots}>
              {(snapshot, index) => {
                const isLatest = index() === sessionState.snapshots.length - 1;
                return (
                  <div class="timeline-item">
                    <div class="timeline-marker" classList={{ latest: isLatest }} />
                    <div class="timeline-card flex-1">
                      <div class="flex items-start justify-between gap-3">
                        <div>
                          <div class="flex flex-wrap items-center gap-2">
                            <div class="text-sm font-medium text-[var(--text-primary)]">
                              {snapshot.description}
                            </div>
                            <Show when={isLatest}>
                              <span class="subtle-pill accent">最新</span>
                            </Show>
                          </div>
                          <div class="mt-2 text-xs text-[var(--text-secondary)]">
                            {renderTimestamp(snapshot.createdAt)}
                          </div>
                        </div>

                        <Show when={!isLatest}>
                          <button
                            class="soft-btn"
                            onClick={() => void handleRollback(snapshot.snapshotId)}
                          >
                            回滚
                          </button>
                        </Show>
                      </div>
                    </div>
                  </div>
                );
              }}
            </For>
          </div>
        </div>
      </section>
    </Show>
  );
};

export default Timeline;
