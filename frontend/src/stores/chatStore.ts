import { createStore } from "solid-js/store";

export interface ToolCallInfo {
  callId: string;
  name: string;
  arguments: Record<string, unknown>;
  status: "pending" | "executing" | "success" | "error" | "confirm";
  startedAt: number;
  updatedAt: number;
  finishedAt?: number;
  result?: string;
  error?: string;
  progressMessage?: string;
}

export interface ChatMessage {
  messageId: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp: number;
  isStreaming?: boolean;
  toolCalls?: ToolCallInfo[];
  tableData?: { headers: string[]; rows: (string | number)[][] };
}

export interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  currentToolCalls: ToolCallInfo[];
  error: string | null;
}

const [chatState, setChatState] = createStore<ChatState>({
  messages: [],
  isStreaming: false,
  currentToolCalls: [],
  error: null,
});

export const addMessage = (msg: ChatMessage) => {
  setChatState("messages", (prev) => [...prev, msg]);
};

export const setMessages = (messages: ChatMessage[]) => {
  setChatState("messages", messages);
};

export const updateLastMessageContent = (content: string) => {
  const msgs = chatState.messages;
  if (msgs.length > 0) {
    const lastIdx = msgs.length - 1;
    setChatState("messages", lastIdx, "content", msgs[lastIdx].content + content);
  }
};

export const updateLastMessageTable = (
  tableData: { headers: string[]; rows: (string | number)[][] }
) => {
  setChatState("messages", (prev) => {
    const next = [...prev];
    if (next.length > 0) {
      next[next.length - 1].tableData = tableData;
    }
    return next;
  });
};

export const setLastMessageContent = (content: string) => {
  const msgs = chatState.messages;
  if (msgs.length > 0) {
    const lastIdx = msgs.length - 1;
    setChatState("messages", lastIdx, "content", content);
  }
};

export const setStreaming = (streaming: boolean) =>
  setChatState("isStreaming", streaming);

export const setCurrentToolCalls = (calls: ToolCallInfo[]) =>
  setChatState("currentToolCalls", calls);

export const updateToolCallStatus = (
  callId: string,
  status: ToolCallInfo["status"],
  result?: string,
  error?: string,
  progressMessage?: string
) => {
  setChatState("currentToolCalls", (prev) =>
    prev.map((c) =>
      c.callId === callId
        ? {
            ...c,
            status,
            updatedAt: Date.now(),
            finishedAt: status === "executing" ? undefined : Date.now(),
            result: result ?? c.result,
            error: error ?? c.error,
            progressMessage:
              status === "executing" ? (progressMessage ?? c.progressMessage) : undefined,
          }
        : c
    )
  );
};

export const setChatError = (error: string | null) =>
  setChatState("error", error);
export const clearMessages = () =>
  setChatState({ messages: [], isStreaming: false, currentToolCalls: [], error: null });

export { chatState };
