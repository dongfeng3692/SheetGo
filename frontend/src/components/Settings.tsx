import type { Accessor, Component } from "solid-js";
import { For, Show, createEffect, createSignal } from "solid-js";
import {
  getConfig,
  getDiagnostics,
  openDesktopLog,
  openLogsDirectory,
  readDesktopLog,
  saveConfig,
} from "../lib/tauri-bridge";
import {
  applyUiTheme,
  resolveThemeMode,
  resolveThemePreset,
  themeModeOptions,
  themePresets,
} from "../lib/themes";
import type { AppConfig, DiagnosticsInfo } from "../lib/tauri";

interface Props {
  open: Accessor<boolean>;
  onClose: () => void;
}

const Settings: Component<Props> = (props) => {
  const [config, setConfig] = createSignal<AppConfig | null>(null);
  const [diagnostics, setDiagnostics] = createSignal<DiagnosticsInfo | null>(null);
  const [desktopLog, setDesktopLog] = createSignal("");
  const [diagnosticError, setDiagnosticError] = createSignal<string | null>(null);
  const [loadingLog, setLoadingLog] = createSignal(false);
  const [saving, setSaving] = createSignal(false);
  const [saveError, setSaveError] = createSignal<string | null>(null);

  const normalizeUiError = (error: unknown, fallback = "操作失败，请稍后重试。") => {
    const raw =
      error instanceof Error
        ? error.message
        : typeof error === "string"
          ? error
          : error
            ? String(error)
            : "";

    const cleaned = raw
      .replace(/^Error:\s*/i, "")
      .replace(/^(?:Internal error|RuntimeError|ValueError|TypeError):\s*/i, "")
      .trim();

    return cleaned || fallback;
  };

  const refreshDiagnostics = async () => {
    setLoadingLog(true);
    setDiagnosticError(null);
    try {
      const [info, logText] = await Promise.all([getDiagnostics(), readDesktopLog(120000)]);
      setDiagnostics(info);
      setDesktopLog(logText);
    } catch (error) {
      console.error("Failed to load diagnostics:", error);
      setDiagnosticError(normalizeUiError(error, "读取日志失败。"));
    } finally {
      setLoadingLog(false);
    }
  };

  createEffect(() => {
    if (!props.open()) {
      return;
    }
    setSaveError(null);
    void getConfig().then((value) => setConfig(value));
    void refreshDiagnostics();
  });

  const updateLlm = (key: keyof AppConfig["llm"], value: string | number) => {
    setConfig((previous) =>
      previous ? { ...previous, llm: { ...previous.llm, [key]: value } } : previous
    );
  };

  const updateUi = (key: keyof AppConfig["ui"], value: string | number) => {
    setConfig((previous) =>
      previous ? { ...previous, ui: { ...previous.ui, [key]: value } } : previous
    );
  };

  const updateAdvanced = (
    key: keyof AppConfig["advanced"],
    value: number | boolean
  ) => {
    setConfig((previous) =>
      previous
        ? { ...previous, advanced: { ...previous.advanced, [key]: value } }
        : previous
    );
  };

  const handleSave = async () => {
    const value = config();
    if (!value) {
      return;
    }

    const normalizedConfig = {
      ...value,
      ui: {
        ...value.ui,
        theme: resolveThemeMode(value.ui.theme),
        themePreset: resolveThemePreset(value.ui.themePreset),
        language: "zh-CN",
      },
    };

    setSaving(true);
    setSaveError(null);
    try {
      await saveConfig(normalizedConfig);
      applyUiTheme(normalizedConfig.ui);
      props.onClose();
    } catch (error) {
      console.error("Failed to save config:", error);
      setSaveError(`保存设置失败：${String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleOpenLogFile = async () => {
    setDiagnosticError(null);
    try {
      await openDesktopLog();
    } catch (error) {
      console.error("Failed to open desktop log:", error);
      setDiagnosticError(normalizeUiError(error, "打开日志文件失败。"));
    }
  };

  const handleOpenLogsDirectory = async () => {
    setDiagnosticError(null);
    try {
      await openLogsDirectory();
    } catch (error) {
      console.error("Failed to open logs directory:", error);
      setDiagnosticError(normalizeUiError(error, "打开日志目录失败。"));
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
      <div class="absolute inset-0 bg-black/20 backdrop-blur-sm" onClick={props.onClose} />

      <aside
        class="absolute right-0 top-0 h-full w-full max-w-[540px] border-l border-[var(--border-subtle)] bg-[var(--bg-overlay)] shadow-2xl transition-transform duration-300"
        classList={{ "translate-x-full": !props.open(), "translate-x-0": props.open() }}
      >
        <div class="flex h-full flex-col">
          <header class="border-b border-[var(--border-subtle)] px-6 py-5">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-xs uppercase tracking-[0.18em] text-[var(--text-tertiary)]">偏好设置</div>
                <h2 class="mt-2 text-2xl font-semibold tracking-tight text-[var(--text-primary)]">
                  应用设置
                </h2>
              </div>
              <button class="soft-btn" onClick={props.onClose}>
                关闭
              </button>
            </div>
          </header>

          <div class="flex-1 space-y-6 overflow-auto px-6 py-6">
            <Show when={config()}>
              <section class="surface-muted space-y-4 px-4 py-4">
                <div>
                  <div class="text-sm font-semibold text-[var(--text-primary)]">模型连接</div>
                  <div class="mt-1 text-sm text-[var(--text-secondary)]">
                    配置桌面助手所使用的模型服务商和模型名称。
                  </div>
                </div>

                <div class="grid gap-4 md:grid-cols-2">
                  <label class="field">
                    <span class="field-label">服务商</span>
                    <select
                      class="field-input"
                      value={config()!.llm.provider}
                      onChange={(event) => updateLlm("provider", event.currentTarget.value)}
                    >
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                      <option value="azure">Azure</option>
                      <option value="ollama">Ollama</option>
                      <option value="custom">自定义</option>
                    </select>
                  </label>

                  <label class="field">
                    <span class="field-label">模型</span>
                    <input
                      class="field-input"
                      value={config()!.llm.model}
                      onInput={(event) => updateLlm("model", event.currentTarget.value)}
                    />
                  </label>

                  <label class="field md:col-span-2">
                    <span class="field-label">API 密钥</span>
                    <input
                      class="field-input"
                      type="password"
                      value={config()!.llm.apiKey}
                      onInput={(event) => updateLlm("apiKey", event.currentTarget.value)}
                    />
                  </label>

                  <label class="field md:col-span-2">
                    <span class="field-label">接口地址</span>
                    <input
                      class="field-input"
                      value={config()!.llm.baseUrl}
                      onInput={(event) => updateLlm("baseUrl", event.currentTarget.value)}
                    />
                  </label>

                  <label class="field">
                    <span class="field-label">温度</span>
                    <input
                      class="field-input"
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={config()!.llm.temperature}
                      onInput={(event) => updateLlm("temperature", parseFloat(event.currentTarget.value))}
                    />
                  </label>

                  <label class="field">
                    <span class="field-label">最大 Token 数</span>
                    <input
                      class="field-input"
                      type="number"
                      value={config()!.llm.maxTokens}
                      onInput={(event) => updateLlm("maxTokens", parseInt(event.currentTarget.value, 10))}
                    />
                  </label>
                </div>
              </section>

              <section class="surface-muted space-y-4 px-4 py-4">
                <div>
                  <div class="text-sm font-semibold text-[var(--text-primary)]">外观</div>
                  <div class="mt-1 text-sm text-[var(--text-secondary)]">
                    把配色模式和界面风格拆开，后续新增主题也能继续复用。
                  </div>
                </div>

                <div class="space-y-3">
                  <div class="field-label">配色模式</div>
                  <div class="theme-mode-grid">
                    <For each={themeModeOptions}>
                      {(option) => (
                        <button
                          type="button"
                          class="theme-mode-chip"
                          classList={{ active: config()!.ui.theme === option.id }}
                          onClick={() => updateUi("theme", option.id)}
                        >
                          <span class="theme-mode-title">{option.label}</span>
                          <span class="theme-mode-description">{option.description}</span>
                        </button>
                      )}
                    </For>
                  </div>
                </div>

                <div class="space-y-3">
                  <div class="field-label">主题风格</div>
                  <div class="theme-preset-grid">
                    <For each={themePresets}>
                      {(preset) => (
                        <button
                          type="button"
                          class="theme-preset-card"
                          data-theme-preview={preset.id}
                          classList={{ active: config()!.ui.themePreset === preset.id }}
                          onClick={() => updateUi("themePreset", preset.id)}
                        >
                          <div class="theme-preset-head">
                            <div>
                              <div class="theme-preset-title">{preset.label}</div>
                              <div class="theme-preset-headline">{preset.headline}</div>
                            </div>
                            <Show when={config()!.ui.themePreset === preset.id}>
                              <span class="subtle-pill accent">当前</span>
                            </Show>
                          </div>

                          <div class="theme-preset-swatches" aria-hidden="true">
                            <For each={preset.swatches}>
                              {(swatch) => (
                                <span style={{ "background-color": swatch }} />
                              )}
                            </For>
                          </div>

                          <div class="theme-preset-description">{preset.description}</div>
                          <div class="theme-preset-mood">{preset.mood}</div>
                        </button>
                      )}
                    </For>
                  </div>
                </div>

                <div class="grid gap-4 md:grid-cols-2">
                  <label class="field">
                    <span class="field-label">预览行数</span>
                    <input
                      class="field-input"
                      type="number"
                      value={config()!.ui.previewRows}
                      onInput={(event) => updateUi("previewRows", parseInt(event.currentTarget.value, 10))}
                    />
                  </label>
                </div>
              </section>

              <section class="surface-muted space-y-4 px-4 py-4">
                <div>
                  <div class="text-sm font-semibold text-[var(--text-primary)]">高级选项</div>
                  <div class="mt-1 text-sm text-[var(--text-secondary)]">
                    调整限制、预加载行为和沙箱策略。
                  </div>
                </div>

                <div class="grid gap-4 md:grid-cols-2">
                  <label class="field">
                    <span class="field-label">最大文件大小 (MB)</span>
                    <input
                      class="field-input"
                      type="number"
                      value={Math.round(config()!.advanced.maxFileSize / 1048576)}
                      onInput={(event) =>
                        updateAdvanced("maxFileSize", parseInt(event.currentTarget.value, 10) * 1048576)
                      }
                    />
                  </label>

                  <label class="field">
                    <span class="field-label">快照数量上限</span>
                    <input
                      class="field-input"
                      type="number"
                      value={config()!.advanced.snapshotMaxCount}
                      onInput={(event) =>
                        updateAdvanced("snapshotMaxCount", parseInt(event.currentTarget.value, 10))
                      }
                    />
                  </label>

                  <label class="field md:col-span-2">
                    <span class="field-label">预加载采样行数</span>
                    <input
                      class="field-input"
                      type="number"
                      value={config()!.advanced.preloadSampleRows}
                      onInput={(event) =>
                        updateAdvanced("preloadSampleRows", parseInt(event.currentTarget.value, 10))
                      }
                    />
                  </label>
                </div>

                <label class="mt-2 flex items-center gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-3 text-sm text-[var(--text-primary)]">
                  <input
                    type="checkbox"
                    checked={config()!.advanced.sandboxEnabled}
                    onChange={(event) => updateAdvanced("sandboxEnabled", event.currentTarget.checked)}
                  />
                  对高风险操作启用沙箱保护
                </label>
              </section>

              <section class="surface-muted space-y-4 px-4 py-4">
                <div>
                  <div class="text-sm font-semibold text-[var(--text-primary)]">诊断与日志</div>
                  <div class="mt-1 text-sm text-[var(--text-secondary)]">
                    上传、预处理和桌面端异常会记录在本地日志里。
                  </div>
                </div>

                <div class="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-3">
                  <div class="text-xs uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                    日志文件
                  </div>
                  <div class="mt-2 break-all font-mono text-[11px] leading-5 text-[var(--text-secondary)]">
                    {diagnostics()?.logFilePath ?? "正在读取..."}
                  </div>
                </div>

                <div class="flex flex-wrap gap-2">
                  <button class="soft-btn" onClick={() => void refreshDiagnostics()} disabled={loadingLog()}>
                    {loadingLog() ? "刷新中..." : "刷新日志"}
                  </button>
                  <button class="soft-btn" onClick={() => void handleOpenLogFile()}>
                    打开日志文件
                  </button>
                  <button class="soft-btn" onClick={() => void handleOpenLogsDirectory()}>
                    打开日志目录
                  </button>
                </div>

                <Show when={diagnosticError()}>
                  {(message) => (
                    <div class="rounded-2xl border border-[var(--border-strong)] bg-[var(--warning-soft)] px-3 py-2 text-xs text-[var(--warning-text)]">
                      {message()}
                    </div>
                  )}
                </Show>

                <div class="overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)]">
                  <div class="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-4 py-3">
                    <div class="text-xs uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                      最近日志
                    </div>
                    <span class="subtle-pill">
                      {loadingLog() ? "刷新中" : desktopLog() ? "已加载" : "暂无记录"}
                    </span>
                  </div>
                  <pre class="max-h-72 overflow-auto whitespace-pre-wrap break-all px-4 py-4 font-mono text-[11px] leading-5 text-[var(--text-secondary)]">{desktopLog() || "当前还没有桌面日志。发生导入或预处理错误后，这里会显示最近记录。"}</pre>
                </div>
              </section>
            </Show>
          </div>

          <footer class="border-t border-[var(--border-subtle)] px-6 py-4">
            <div class="flex flex-wrap items-center justify-between gap-4">
              <div class="flex-1 text-sm text-[var(--text-secondary)]">
                所有改动都会保存在当前设备本地。
              </div>
              <Show when={saveError()}>
                {(message) => (
                  <div class="rounded-full border border-[var(--border-strong)] bg-[var(--warning-soft)] px-3 py-2 text-xs text-[var(--warning-text)]">
                    {message()}
                  </div>
                )}
              </Show>
              <button class="soft-btn-primary" onClick={() => void handleSave()} disabled={saving()}>
                {saving() ? "正在保存..." : "保存设置"}
              </button>
            </div>
          </footer>
        </div>
      </aside>
    </div>
  );
};

export default Settings;
