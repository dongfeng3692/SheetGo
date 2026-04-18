import type { Component } from "solid-js";
import { For, Show, createEffect, createMemo, createSignal, onCleanup, onMount } from "solid-js";
import {
  addMessage,
  chatState,
  clearMessages,
  setChatError,
  setCurrentToolCalls,
  setLastMessageContent,
  setMessages,
  setStreaming,
  updateLastMessageContent,
  updateToolCallStatus,
  type ChatMessage,
} from "../stores/chatStore";
import { fileState } from "../stores/fileStore";
import { sessionState } from "../stores/sessionStore";
import {
  getHistory,
  onChatStream,
  saveHistory,
  sendMessageStream,
  stopGeneration,
  type HistoryEntry,
} from "../lib/tauri-bridge";

const toolStatusLabels: Record<string, string> = {
  pending: "等待中",
  executing: "执行中",
  success: "已完成",
  error: "失败",
  confirm: "待确认",
};

const toolNameLabels: Record<string, string> = {
  write_cells: "写入单元格",
  query_data: "查询数据",
  add_formula: "插入公式",
  create_chart: "生成图表",
  read_sheet: "读取工作表",
  list_sheets: "列出工作表",
};

const CodeBlock: Component<{ code: string }> = (props) => (
  <pre class="markdown-code overflow-auto rounded-2xl bg-[#111111] px-4 py-3 text-xs text-white/90">
    <code>{props.code}</code>
  </pre>
);

const MarkdownText: Component<{ text: string; compact?: boolean }> = (props) => {
  const parts = () => {
    const chunks: { type: "text" | "code"; content: string }[] = [];
    const regex = /```(?:\w+)?\n([\s\S]*?)```/g;
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = regex.exec(props.text)) !== null) {
      if (match.index > lastIndex) {
        chunks.push({ type: "text", content: props.text.slice(lastIndex, match.index) });
      }
      chunks.push({ type: "code", content: match[1] });
      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < props.text.length) {
      chunks.push({ type: "text", content: props.text.slice(lastIndex) });
    }

    return chunks;
  };

  return (
    <div
      class="markdown-text"
      classList={{ compact: props.compact, "space-y-1.5": props.compact, "space-y-2.5": !props.compact }}
    >
      <For each={parts()}>
        {(part) =>
          part.type === "code" ? (
            <CodeBlock code={part.content} />
          ) : (
            <div
              class="markdown-paragraph whitespace-pre-wrap"
              classList={{ compact: props.compact, "leading-[1.48]": props.compact, "leading-[1.66]": !props.compact }}
            >
              {part.content}
            </div>
          )
        }
      </For>
    </div>
  );
};

const ChatPanel: Component = () => {
  let inputRef: HTMLTextAreaElement | undefined;
  let messagesEndRef: HTMLDivElement | undefined;
  const [draft, setDraft] = createSignal("");
  const [toolHistoryExpanded, setToolHistoryExpanded] = createSignal(false);
  const [loadingHistorySessionId, setLoadingHistorySessionId] = createSignal<string | null>(null);
  const historySignatures = new Map<string, string>();
  let historyLoadVersion = 0;
  let persistHistoryTimer: number | undefined;

  const normalizeHistoryTimestamp = (value: number) => (value > 1e12 ? value : value * 1000);

  const mapHistoryToMessages = (entries: HistoryEntry[]): ChatMessage[] =>
    entries.map((entry) => ({
      messageId: entry.messageId,
      role: entry.role,
      content: entry.content,
      timestamp: normalizeHistoryTimestamp(entry.createdAt),
    }));

  const mapMessagesToHistory = (messages: ChatMessage[]): HistoryEntry[] =>
    messages
      .filter(
        (message): message is ChatMessage & { role: HistoryEntry["role"] } =>
          (message.role === "user" || message.role === "assistant" || message.role === "system") &&
          message.content.trim().length > 0
      )
      .map((message) => ({
        messageId: message.messageId,
        role: message.role,
        content: message.content,
        createdAt: message.timestamp,
      }));

  createEffect(() => {
    const sessionId = sessionState.activeSessionId;
    const currentLoadVersion = ++historyLoadVersion;

    clearMessages();
    setToolHistoryExpanded(false);

    if (!sessionId) {
      setLoadingHistorySessionId(null);
      return;
    }

    setLoadingHistorySessionId(sessionId);

    void getHistory(sessionId)
      .then((entries) => {
        if (currentLoadVersion !== historyLoadVersion || sessionState.activeSessionId !== sessionId) {
          return;
        }

        const normalizedEntries = Array.isArray(entries) ? entries : [];
        historySignatures.set(sessionId, JSON.stringify(normalizedEntries));
        setMessages(mapHistoryToMessages(normalizedEntries));
        setLoadingHistorySessionId((current) => (current === sessionId ? null : current));
      })
      .catch((error) => {
        if (currentLoadVersion !== historyLoadVersion || sessionState.activeSessionId !== sessionId) {
          return;
        }

        console.error("Failed to load chat history:", error);
        historySignatures.set(sessionId, "[]");
        setLoadingHistorySessionId((current) => (current === sessionId ? null : current));
      });
  });

  createEffect(() => {
    const sessionId = sessionState.activeSessionId;
    const loadingSessionId = loadingHistorySessionId();
    const entries = mapMessagesToHistory(chatState.messages);
    const signature = JSON.stringify(entries);

    if (!sessionId || loadingSessionId === sessionId) {
      return;
    }

    if (historySignatures.get(sessionId) === signature) {
      return;
    }

    if (persistHistoryTimer) {
      window.clearTimeout(persistHistoryTimer);
    }

    persistHistoryTimer = window.setTimeout(() => {
      if (sessionState.activeSessionId !== sessionId) {
        return;
      }

      void saveHistory(sessionId, entries)
        .then(() => {
          historySignatures.set(sessionId, signature);
        })
        .catch((error) => {
          console.error("Failed to persist chat history:", error);
        });
    }, chatState.isStreaming ? 720 : 220);
  });

  createEffect(() => {
    chatState.messages.length;
    queueMicrotask(() => {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      messagesEndRef?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "end" });
    });
  });

  onMount(() => {
    let dispose = () => {};
    void onChatStream((event) => {
      switch (event.type) {
        case "text_delta":
          if (event.text) {
            updateLastMessageContent(event.text);
          }
          break;
        case "text_end":
          if (event.full_text) {
            setLastMessageContent(event.full_text);
          }
          break;
        case "tool_call_start":
          if (event.id && event.name) {
            const now = Date.now();
            setCurrentToolCalls([
              ...chatState.currentToolCalls,
              {
                callId: event.id,
                name: event.name,
                arguments: {},
                status: "executing",
                startedAt: now,
                updatedAt: now,
                progressMessage: "准备执行...",
              },
            ]);
          }
          break;
        case "tool_call_progress":
          if (event.id) {
            updateToolCallStatus(
              event.id,
              "executing",
              undefined,
              undefined,
              event.message || "正在处理..."
            );
          }
          break;
        case "tool_call_end":
          if (event.id) {
            updateToolCallStatus(
              event.id,
              event.error ? "error" : "success",
              event.result ?? undefined,
              event.error
            );
          }
          break;
        case "done":
          setStreaming(false);
          break;
        case "error":
          setChatError(event.error || event.message || "对话失败。");
          setStreaming(false);
          break;
      }
    }).then((unlisten) => {
      dispose = unlisten;
    });

    onCleanup(() => {
      dispose();
      if (persistHistoryTimer) {
        window.clearTimeout(persistHistoryTimer);
      }
    });
  });

  const canSend = createMemo(() => draft().trim().length > 0 && !chatState.isStreaming);

  const handleSend = async () => {
    const content = draft().trim();
    if (!content) {
      return;
    }

    const sessionId = sessionState.activeSessionId;
    const fileId = fileState.activeFileId ?? "";
    if (!sessionId) {
      setChatError("请先创建工作区，再开始对话。");
      return;
    }

    addMessage({
      messageId: `user_${Date.now()}`,
      role: "user",
      content,
      timestamp: Date.now(),
    });
    addMessage({
      messageId: `assistant_${Date.now()}`,
      role: "assistant",
      content: "",
      timestamp: Date.now(),
      isStreaming: true,
    });

    setChatError(null);
    setCurrentToolCalls([]);
    setToolHistoryExpanded(false);
    setStreaming(true);

    if (inputRef) {
      setDraft("");
      inputRef.style.height = "auto";
    }

    try {
      await sendMessageStream({
        sessionId,
        fileId,
        message: content,
      });
    } catch (error) {
      console.error("Failed to send message:", error);
      setChatError(`发送失败：${String(error)}`);
      setStreaming(false);
    }
  };

  const renderTimestamp = (value: number) =>
    new Date(value).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });

  const renderToolStatus = (status: string) => toolStatusLabels[status] ?? status;
  const renderToolName = (name: string) => toolNameLabels[name] ?? name;
  const latestToolCall = createMemo(
    () => chatState.currentToolCalls[chatState.currentToolCalls.length - 1] ?? null
  );
  const collapsedToolCount = createMemo(() => Math.max(chatState.currentToolCalls.length - 1, 0));
  const activeToolCount = createMemo(
    () => chatState.currentToolCalls.filter((call) => call.status === "executing").length
  );
  const completedToolRun = createMemo(
    () => chatState.currentToolCalls.length > 0 && activeToolCount() === 0
  );
  const visibleToolCall = createMemo(() => (completedToolRun() ? null : latestToolCall()));
  const toolRunDurationMs = createMemo(() => {
    if (chatState.currentToolCalls.length === 0) {
      return 0;
    }

    const startedAt = Math.min(...chatState.currentToolCalls.map((call) => call.startedAt));
    const endedAt = Math.max(
      ...chatState.currentToolCalls.map((call) => call.finishedAt ?? call.updatedAt)
    );

    return Math.max(endedAt - startedAt, 0);
  });

  createEffect(() => {
    if (activeToolCount() > 0 || chatState.currentToolCalls.length === 0) {
      setToolHistoryExpanded(false);
    }
  });

  const truncateInline = (value: string, max = 72) =>
    value.length > max ? `${value.slice(0, max).trim()}...` : value;

  const formatDuration = (durationMs: number) => {
    const totalSeconds = Math.max(1, Math.round(durationMs / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    if (minutes <= 0) {
      return `${totalSeconds}s`;
    }

    return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  };

  const renderToolSummary = () => {
    const call = latestToolCall();
    if (!call) {
      return "";
    }

    if (call.status === "executing") {
      return call.progressMessage || "正在处理...";
    }

    if (call.status === "error") {
      return call.error ? truncateInline(call.error) : "执行失败，请查看日志或重试。";
    }

    if (call.result) {
      return truncateInline(call.result.replace(/\s+/g, " ").trim());
    }

    if (collapsedToolCount() > 0) {
      return `保留最近一条，其余 ${collapsedToolCount()} 条已折叠。`;
    }

    return "本轮工具调用已完成。";
  };

  const renderToolHistorySummary = (result?: string, error?: string, progressMessage?: string) => {
    if (error) {
      return truncateInline(error, 84);
    }
    if (result) {
      return truncateInline(result.replace(/\s+/g, " ").trim(), 84);
    }
    if (progressMessage) {
      return truncateInline(progressMessage, 84);
    }
    return "工具状态已更新。";
  };

  return (
    <section class="surface-card conversation-panel flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      <header class="panel-header border-b border-[var(--border-subtle)] px-5 py-3">
        <div class="panel-kicker">对话</div>
      </header>

      <div class="min-h-0 flex-1 overflow-auto px-5 py-4">
        <Show
          when={chatState.messages.length > 0}
          fallback={
            <div class="chat-empty-shell">
              <div class="chat-empty-mark" aria-hidden="true">
                <span />
              </div>
              <div class="chat-empty-title">开始对话</div>
              <div class="chat-empty-note">输入问题或修改要求</div>
            </div>
          }
        >
          <div class="chat-thread mx-auto w-full max-w-3xl space-y-2">
            <For each={chatState.messages}>
              {(message: ChatMessage) => (
                <div
                  class="flex"
                  classList={{
                    "justify-end": message.role === "user",
                    "justify-start": message.role !== "user",
                  }}
                >
                  <div
                    class="message-card"
                    classList={{
                      user: message.role === "user",
                      assistant: message.role !== "user",
                    }}
                  >
                    <Show when={message.content}>
                      <div class="message-card-body">
                        <MarkdownText text={message.content} compact />
                      </div>
                    </Show>
                    <div class="message-card-time">
                      {renderTimestamp(message.timestamp)}
                    </div>
                  </div>
                </div>
              )}
            </For>

            <Show when={visibleToolCall()}>
              {(call) => (
                <div
                  class="tool-call-strip"
                  classList={{
                    live: call().status === "executing",
                    error: call().status === "error",
                    success: call().status === "success",
                  }}
                >
                  <div class="tool-call-strip-head">
                    <div class="panel-kicker">工具调用</div>
                    <div class="tool-call-strip-meta">
                      <Show when={collapsedToolCount() > 0}>
                        <span class="tool-call-collapse-badge">
                          折叠 {collapsedToolCount()} 条
                        </span>
                      </Show>
                      <Show when={activeToolCount() > 0}>
                        <span class="tool-call-live-chip">运行中 {activeToolCount()}</span>
                      </Show>
                    </div>
                  </div>

                  <div class="tool-call-inline">
                    <div
                      class="tool-call-orb"
                      classList={{
                        live: call().status === "executing",
                        error: call().status === "error",
                        success: call().status === "success",
                      }}
                      aria-hidden="true"
                    >
                      <span class="tool-call-orb-core" />
                    </div>

                    <div class="min-w-0 flex-1">
                      <div class="tool-call-title-row">
                        <div class="tool-call-title">{renderToolName(call().name)}</div>
                        <span
                          class="tool-call-status-pill"
                          classList={{
                            live: call().status === "executing",
                            error: call().status === "error",
                          }}
                        >
                          {renderToolStatus(call().status)}
                        </span>
                      </div>
                      <div class="tool-call-summary">{renderToolSummary()}</div>
                    </div>
                  </div>

                  <Show when={call().status === "executing"}>
                    <div class="tool-call-beam" aria-hidden="true">
                      <span />
                    </div>
                  </Show>
                </div>
              )}
            </Show>

            <Show when={completedToolRun()}>
              <div class="tool-history-shell">
                <button
                  type="button"
                  class="tool-history-toggle"
                  aria-expanded={toolHistoryExpanded()}
                  onClick={() => setToolHistoryExpanded((value) => !value)}
                >
                  <span class="tool-history-toggle-label">
                    已处理 {formatDuration(toolRunDurationMs())}
                  </span>
                  <span
                    class="tool-history-toggle-icon"
                    classList={{ expanded: toolHistoryExpanded() }}
                    aria-hidden="true"
                  >
                    ›
                  </span>
                </button>

                <Show when={toolHistoryExpanded()}>
                  <div class="tool-history-panel">
                    <div class="tool-history-caption">
                      共 {chatState.currentToolCalls.length} 个工具步骤
                    </div>
                    <div class="tool-history-list">
                      <For each={chatState.currentToolCalls}>
                        {(call) => (
                          <div class="tool-history-item">
                            <div class="tool-history-item-head">
                              <div class="tool-history-item-title">{renderToolName(call.name)}</div>
                              <span
                                class="tool-history-item-status"
                                classList={{
                                  error: call.status === "error",
                                  live: call.status === "executing",
                                }}
                              >
                                {renderToolStatus(call.status)}
                              </span>
                            </div>
                            <div class="tool-history-item-body">
                              {renderToolHistorySummary(
                                call.result,
                                call.error,
                                call.progressMessage
                              )}
                            </div>
                          </div>
                        )}
                      </For>
                    </div>
                  </div>
                </Show>
              </div>
            </Show>

            <Show when={chatState.isStreaming}>
              <div class="surface-muted flex items-center gap-3 px-4 py-2.5 text-sm text-[var(--text-secondary)]">
                <span class="loading-dot" />
                正在生成回复...
              </div>
            </Show>

            <Show when={chatState.error}>
              <div class="rounded-2xl border border-[var(--border-strong)] bg-[var(--warning-soft)] px-4 py-3 text-sm text-[var(--warning-text)]">
                {chatState.error}
              </div>
            </Show>

            <div ref={messagesEndRef} />
          </div>
        </Show>
      </div>

      <div class="composer-panel">
        <div class="composer-shell">
          <div class="composer-topline">
            <div class="composer-title">输入</div>
            <span class="composer-shortcut">Enter 发送</span>
          </div>

          <div class="composer-surface">
            <textarea
              ref={inputRef}
              rows={1}
              class="composer-input"
              aria-label="消息输入框"
              placeholder="输入问题或修改要求"
              value={draft()}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
              onInput={(event) => {
                setDraft(event.currentTarget.value);
                event.currentTarget.style.height = "auto";
                event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 160)}px`;
              }}
            />

            <div class="composer-actions">
              <Show when={chatState.isStreaming}>
                <button class="soft-btn composer-stop-btn" onClick={() => void stopGeneration()}>
                  停止
                </button>
              </Show>

              <button
                class="soft-btn-primary composer-send-btn"
                disabled={!canSend()}
                onClick={() => void handleSend()}
              >
                <span class="composer-send-label">发送</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ChatPanel;
