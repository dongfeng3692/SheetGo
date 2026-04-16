import type { Accessor, Component } from "solid-js";
import { Show, createEffect, createSignal } from "solid-js";
import { getConfig, saveConfig } from "../lib/tauri-bridge";
import type { AppConfig } from "../lib/tauri";

interface Props {
  open: Accessor<boolean>;
  onClose: () => void;
}

function applyTheme(theme: AppConfig["ui"]["theme"]) {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const shouldUseDark = theme === "dark" || (theme === "system" && prefersDark);
  document.documentElement.classList.toggle("dark", shouldUseDark);
}

const Settings: Component<Props> = (props) => {
  const [config, setConfig] = createSignal<AppConfig | null>(null);
  const [saving, setSaving] = createSignal(false);
  const [saveError, setSaveError] = createSignal<string | null>(null);

  createEffect(() => {
    if (!props.open()) {
      return;
    }
    setSaveError(null);
    void getConfig().then((value) => setConfig(value));
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
        language: "zh-CN",
      },
    };

    setSaving(true);
    setSaveError(null);
    try {
      await saveConfig(normalizedConfig);
      applyTheme(normalizedConfig.ui.theme);
      props.onClose();
    } catch (error) {
      console.error("Failed to save config:", error);
      setSaveError(`保存设置失败：${String(error)}`);
    } finally {
      setSaving(false);
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
                    界面主题可切换为浅色、深色，或跟随系统。
                  </div>
                </div>

                <div class="grid gap-4 md:grid-cols-2">
                  <label class="field">
                    <span class="field-label">主题</span>
                    <select
                      class="field-input"
                      value={config()!.ui.theme}
                      onChange={(event) => updateUi("theme", event.currentTarget.value)}
                    >
                      <option value="light">浅色</option>
                      <option value="dark">深色</option>
                      <option value="system">跟随系统</option>
                    </select>
                  </label>

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
