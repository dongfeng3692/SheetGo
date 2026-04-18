import type { Accessor, Component } from "solid-js";
import { For, Show, createEffect, createMemo, createSignal } from "solid-js";
import { getParsedArtifacts } from "../lib/tauri-bridge";
import { fileState } from "../stores/fileStore";
import { sessionState } from "../stores/sessionStore";

type TabKey = "schema" | "stats" | "structure";

interface Props {
  open: Accessor<boolean>;
  onClose: () => void;
}

const ParseInspector: Component<Props> = (props) => {
  const [activeTab, setActiveTab] = createSignal<TabKey>("schema");
  const [payload, setPayload] = createSignal<Awaited<ReturnType<typeof getParsedArtifacts>> | null>(null);
  const [loading, setLoading] = createSignal(false);
  const [error, setError] = createSignal<string | null>(null);

  const activeFile = createMemo(() =>
    fileState.files.find((file) => file.fileId === fileState.activeFileId)
  );

  const normalizeUiError = (errorValue: unknown, fallback = "读取解析结果失败。") => {
    const raw =
      errorValue instanceof Error
        ? errorValue.message
        : typeof errorValue === "string"
          ? errorValue
          : errorValue
            ? String(errorValue)
            : "";

    return raw.replace(/^Error:\s*/i, "").trim() || fallback;
  };

  const tabs = createMemo(() => {
    const current = payload();
    return [
      { key: "schema" as const, label: "Schema", data: current?.schema, path: current?.paths.schema },
      { key: "stats" as const, label: "Stats", data: current?.stats, path: current?.paths.stats },
      { key: "structure" as const, label: "Structure", data: current?.structure, path: current?.paths.structure },
    ];
  });

  const currentTab = createMemo(() => tabs().find((item) => item.key === activeTab()) ?? tabs()[0]);

  const summaryItems = createMemo(() => {
    const current = payload();
    const stats = current?.stats as Record<string, unknown> | null;
    const schema = current?.schema as { sheets?: Array<{ rowCount?: number; colCount?: number }> } | null;
    const totalSheets =
      typeof stats?.totalSheets === "number"
        ? stats.totalSheets
        : Array.isArray(schema?.sheets)
          ? schema.sheets.length
          : 0;
    const totalRows =
      typeof stats?.totalRows === "number"
        ? stats.totalRows
        : Array.isArray(schema?.sheets)
          ? schema.sheets.reduce((sum, sheet) => sum + Number(sheet.rowCount || 0), 0)
          : 0;
    const totalCols =
      typeof stats?.totalCols === "number"
        ? stats.totalCols
        : Array.isArray(schema?.sheets)
          ? schema.sheets.reduce((sum, sheet) => sum + Number(sheet.colCount || 0), 0)
          : 0;
    const totalFormulas = typeof stats?.totalFormulas === "number" ? stats.totalFormulas : 0;

    return [
      { label: "工作表", value: `${totalSheets}` },
      { label: "总行数", value: totalRows.toLocaleString() },
      { label: "总列数", value: totalCols.toLocaleString() },
      { label: "公式", value: totalFormulas.toLocaleString() },
    ];
  });

  const refresh = async () => {
    const file = activeFile();
    const sessionId = sessionState.activeSessionId;
    if (!props.open() || !file || !sessionId) {
      setPayload(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const result = await getParsedArtifacts(file.fileId, sessionId);
      setPayload(result);
    } catch (errorValue) {
      console.error("Failed to load parsed artifacts:", errorValue);
      setPayload(null);
      setError(normalizeUiError(errorValue));
    } finally {
      setLoading(false);
    }
  };

  createEffect(() => {
    if (!props.open()) {
      return;
    }
    activeFile()?.fileId;
    sessionState.activeSessionId;
    void refresh();
  });

  createEffect(() => {
    const availableTabs = tabs().filter((item) => item.data !== null);
    if (availableTabs.length === 0) {
      setActiveTab("schema");
      return;
    }
    if (!availableTabs.some((item) => item.key === activeTab())) {
      setActiveTab(availableTabs[0].key);
    }
  });

  const stringifyData = (value: unknown) => {
    if (value == null) {
      return "";
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  };

  return (
    <div
      class="fixed inset-0 z-50 transition"
      classList={{
        "pointer-events-none opacity-0": !props.open(),
        "pointer-events-auto opacity-100": props.open(),
      }}
    >
      <div class="absolute inset-0 bg-black/18 backdrop-blur-sm" onClick={props.onClose} />

      <aside
        class="absolute right-0 top-0 h-full w-full max-w-[620px] border-l border-[var(--border-subtle)] bg-[var(--bg-overlay)] shadow-2xl transition-transform duration-300"
        classList={{ "translate-x-full": !props.open(), "translate-x-0": props.open() }}
      >
        <div class="flex h-full flex-col">
          <header class="border-b border-[var(--border-subtle)] px-6 py-5">
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <div class="text-xs uppercase tracking-[0.18em] text-[var(--text-tertiary)]">解析结果</div>
                <h2 class="mt-2 truncate text-2xl font-semibold tracking-tight text-[var(--text-primary)]">
                  {activeFile()?.fileName ?? "未选择工作簿"}
                </h2>
                <div class="mt-2 text-sm text-[var(--text-secondary)]">
                  这里展示上传后实际写入缓存的解析产物。
                </div>
              </div>

              <div class="flex items-center gap-2">
                <button class="soft-btn" onClick={() => void refresh()} disabled={loading()}>
                  {loading() ? "刷新中..." : "刷新"}
                </button>
                <button class="soft-btn" onClick={props.onClose}>
                  关闭
                </button>
              </div>
            </div>
          </header>

          <div class="flex-1 overflow-auto px-6 py-6">
            <Show
              when={activeFile()}
              fallback={
                <div class="surface-muted px-4 py-4 text-sm text-[var(--text-secondary)]">
                  先选择一个工作簿，再查看解析结果。
                </div>
              }
            >
              <div class="space-y-5">
                <div class="grid grid-cols-2 gap-3">
                  <For each={summaryItems()}>
                    {(item) => (
                      <div class="surface-muted px-4 py-3">
                        <div class="text-xs uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                          {item.label}
                        </div>
                        <div class="mt-2 text-lg font-semibold tracking-tight text-[var(--text-primary)]">
                          {item.value}
                        </div>
                      </div>
                    )}
                  </For>
                </div>

                <Show when={error()}>
                  {(message) => (
                    <div class="rounded-2xl border border-[var(--border-strong)] bg-[var(--warning-soft)] px-4 py-3 text-sm text-[var(--warning-text)]">
                      {message()}
                    </div>
                  )}
                </Show>

                <div class="flex flex-wrap gap-2">
                  <For each={tabs()}>
                    {(tab) => (
                      <button
                        class="inspector-tab"
                        classList={{
                          active: activeTab() === tab.key,
                          muted: tab.data == null,
                        }}
                        onClick={() => setActiveTab(tab.key)}
                      >
                        {tab.label}
                      </button>
                    )}
                  </For>
                </div>

                <div class="surface-muted overflow-hidden">
                  <div class="border-b border-[var(--border-subtle)] px-4 py-3">
                    <div class="text-xs uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      {currentTab()?.path ?? "暂无缓存路径"}
                    </div>
                  </div>

                  <Show
                    when={currentTab()?.data != null}
                    fallback={
                      <div class="px-4 py-6 text-sm leading-7 text-[var(--text-secondary)]">
                        这一项暂时还没有生成内容。
                      </div>
                    }
                  >
                    <pre class="inspector-code-block">{stringifyData(currentTab()?.data)}</pre>
                  </Show>
                </div>
              </div>
            </Show>
          </div>
        </div>
      </aside>
    </div>
  );
};

export default ParseInspector;
