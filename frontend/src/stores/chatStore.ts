import { createStore } from "solid-js/store";

export interface ToolCallInfo {
  callId: string;
  name: string;
  arguments: Record<string, unknown>;
  status: "pending" | "executing" | "success" | "error" | "confirm";
  result?: string;
  error?: string;
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
  error?: string
) => {
  setChatState("currentToolCalls", (prev) =>
    prev.map((c) =>
      c.callId === callId ? { ...c, status, result, error } : c
    )
  );
};

export const setChatError = (error: string | null) =>
  setChatState("error", error);
export const clearMessages = () =>
  setChatState({ messages: [], isStreaming: false, currentToolCalls: [], error: null });

export { chatState };
