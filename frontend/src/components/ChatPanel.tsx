import type { Component } from "solid-js";
import { For, Show, createEffect, onCleanup, onMount } from "solid-js";
import {
  addMessage,
  chatState,
  clearMessages,
  setChatError,
  setCurrentToolCalls,
  setLastMessageContent,
  setStreaming,
  updateLastMessageContent,
  updateToolCallStatus,
  type ChatMessage,
} from "../stores/chatStore";
import { fileState } from "../stores/fileStore";
import { sessionState } from "../stores/sessionStore";
import { onChatStream, sendMessageStream, stopGeneration } from "../lib/tauri-bridge";

const suggestions = [
  {
    title: "概览工作簿",
    detail: "先梳理工作表、字段和关键列，再决定下一步怎么改。",
    prompt: "请先概览这个工作簿的主要工作表、字段和关键列。",
  },
  {
    title: "查找异常",
    detail: "找出异常行、缺失值和可疑模式，并说明为什么值得关注。",
    prompt: "请找出这份数据里的异常值、缺失项或可疑行，并解释原因。",
  },
  {
    title: "推荐图表",
    detail: "根据当前数据结构推荐最合适的图表，并说明理由。",
    prompt: "请为这份数据推荐最合适的图表，并说明原因。",
  },
];

const toolStatusLabels: Record<string, string> = {
  executing: "执行中",
  success: "已完成",
  error: "失败",
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
  <pre class="overflow-auto rounded-2xl bg-[#111111] px-4 py-3 text-xs text-white/90">
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
    <div classList={{ "space-y-2": props.compact, "space-y-3": !props.compact }}>
      <For each={parts()}>
        {(part) =>
          part.type === "code" ? (
            <CodeBlock code={part.content} />
          ) : (
            <div classList={{ "whitespace-pre-wrap leading-6": props.compact, "whitespace-pre-wrap leading-7": !props.compact }}>
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

  createEffect(() => {
    sessionState.activeSessionId;
    clearMessages();
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
            setCurrentToolCalls([
              ...chatState.currentToolCalls,
              { callId: event.id, name: event.name, arguments: {}, status: "executing" },
            ]);
          }
          break;
        case "tool_call_progress":
          if (event.id) {
            updateToolCallStatus(event.id, "executing");
          }
          break;
        case "tool_call_end":
          if (event.id) {
            updateToolCallStatus(event.id, event.error ? "error" : "success", event.result ?? undefined, event.error);
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

    onCleanup(() => dispose());
  });

  const handleSend = async (presetText?: string) => {
    const content = presetText ?? inputRef?.value.trim() ?? "";
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
    setStreaming(true);

    if (inputRef) {
      inputRef.value = "";
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

  return (
    <section class="surface-card conversation-panel flex min-h-0 flex-1 flex-col overflow-hidden">
      <header class="panel-header border-b border-[var(--border-subtle)] px-5 py-3">
        <div class="panel-kicker">对话</div>
      </header>

      <div class="min-h-0 flex-1 overflow-auto px-5 py-4">
        <Show
          when={chatState.messages.length > 0}
          fallback={
            <div class="chat-empty-shell">
              <div class="panel-kicker">快速开始</div>

              <div class="space-y-2.5">
                <For each={suggestions}>
                  {(suggestion) => (
                    <button class="prompt-card prompt-card-rich" onClick={() => void handleSend(suggestion.prompt)}>
                      <div class="text-left text-sm font-semibold text-[var(--text-primary)]">
                        {suggestion.title}
                      </div>
                      <div class="prompt-card-action text-xs font-medium text-[var(--text-tertiary)]">
                        开始
                      </div>
                    </button>
                  )}
                </For>
              </div>
            </div>
          }
        >
          <div class="mx-auto w-full max-w-3xl space-y-3.5">
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
                      <div classList={{ "text-[0.88rem] leading-6": message.role === "user" }}>
                        <MarkdownText text={message.content} compact={message.role === "user"} />
                      </div>
                    </Show>
                    <div class="mt-2 text-[10px] text-[var(--text-tertiary)]">
                      {renderTimestamp(message.timestamp)}
                    </div>
                  </div>
                </div>
              )}
            </For>

            <Show when={chatState.currentToolCalls.length > 0}>
              <div class="surface-muted space-y-3 px-4 py-3.5">
                <div class="panel-kicker">
                  执行轨迹
                </div>
                <For each={chatState.currentToolCalls}>
                  {(call) => (
                    <div class="tool-call-row">
                      <div>
                        <div class="text-sm font-medium text-[var(--text-primary)]">
                          {renderToolName(call.name)}
                        </div>
                        <div class="mt-1 text-xs text-[var(--text-secondary)]">
                          工具状态会在这里实时刷新
                        </div>
                      </div>
                      <span class="subtle-pill accent">{renderToolStatus(call.status)}</span>
                    </div>
                  )}
                </For>
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

      <div class="border-t border-[var(--border-subtle)] p-3.5">
        <div class="composer-shell">
          <div class="mb-2.5 flex items-center justify-between gap-3">
            <div class="panel-kicker">
              直接提问
            </div>
            <div class="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
              <span class="composer-hint">回车发送</span>
            </div>
          </div>

          <textarea
            ref={inputRef}
            rows={1}
            class="composer-input"
            aria-label="消息输入框"
            placeholder="例如：找出销售额异常的行"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
            onInput={(event) => {
              event.currentTarget.style.height = "auto";
              event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 160)}px`;
            }}
          />

          <div class="flex items-center justify-between gap-3">
            <div class="max-w-[18rem] text-xs leading-5 text-[var(--text-secondary)]">
              例：找出销售额异常的行
            </div>

            <div class="flex items-center gap-2">
              <Show when={chatState.isStreaming}>
                <button class="soft-btn" onClick={() => void stopGeneration()}>
                  停止
                </button>
              </Show>
              <button class="soft-btn-primary" onClick={() => void handleSend()}>
                发送
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ChatPanel;
