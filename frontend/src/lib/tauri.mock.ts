/**
 * Mock Tauri IPC for browser-only development.
 * Auto-activated when `@tauri-apps/api` is unavailable (no Tauri runtime).
 */

import type {
  UploadResult,
  FileInfo,
  WorkbookCellEdit,
  SaveWorkbookResult,
  ChatRequest,
  ChatResponse,
  StreamEvent,
  DiagnosticsInfo,
  ParsedArtifacts,
  PreloadProgress,
  Session,
  SnapshotInfo,
  RollbackResult,
  HistoryEntry,
  AppConfig,
} from "./tauri";

// ==================== Mock Data ====================

const mockSessionId = "mock-session-001";
const mockFileId = "mock-file-001";
let mockMessageId = 1;

const defaultConfig: AppConfig = {
  llm: {
    provider: "openai",
    model: "gpt-4o",
    apiKey: "",
    baseUrl: "",
    temperature: 0.1,
    maxTokens: 4096,
  },
  ui: {
    theme: "light",
    themePreset: "default",
    language: "zh-CN",
    previewRows: 100,
  },
  advanced: {
    maxFileSize: 104857600,
    preloadSampleRows: 20,
    snapshotMaxCount: 50,
    sandboxEnabled: true,
  },
};

let currentConfig: AppConfig = structuredClone(defaultConfig);
const mockHistories = new Map<string, HistoryEntry[]>();

const mockFiles: FileInfo[] = [
  {
    fileId: "demo-file-001",
    fileName: "销售数据_Q1.xlsx",
    sheets: ["工作表1", "工作表2"],
    totalRows: 156,
  },
  {
    fileId: "demo-file-002",
    fileName: "员工信息表.xlsx",
    sheets: ["员工列表"],
    totalRows: 89,
  },
];

const mockSnapshots: SnapshotInfo[] = [
  {
    snapshotId: "snap-001",
    sessionId: mockSessionId,
    fileId: mockFileId,
    description: "write_cells 修改B2:D5",
    createdAt: Math.floor(Date.now() / 1000) - 600,
  },
  {
    snapshotId: "snap-002",
    sessionId: mockSessionId,
    fileId: mockFileId,
    description: "query_data 查询销售额",
    createdAt: Math.floor(Date.now() / 1000) - 300,
  },
  {
    snapshotId: "snap-003",
    sessionId: mockSessionId,
    fileId: mockFileId,
    description: "add_formula 添加SUM公式",
    createdAt: Math.floor(Date.now() / 1000) - 60,
  },
];

// ==================== Mock Implementations ====================

export const isMock = true;

export const pickExcelFile = async (): Promise<string | null> => null;

export const uploadFile = async (
  path: string,
  _sessionId: string
): Promise<UploadResult> => {
  await delay(500);
  return {
    fileId: `file-${Date.now()}`,
    fileName: path.split(/[/\\]/).pop() || "未命名.xlsx",
    sheets: ["工作表1"],
    totalRows: Math.floor(Math.random() * 500) + 10,
  };
};

export const listFiles = async (_sessionId: string): Promise<FileInfo[]> => {
  await delay(100);
  return mockFiles;
};

export const removeFile = async (
  _fileId: string,
  _sessionId: string
): Promise<void> => {
  await delay(200);
};

export const getFileInfo = async (
  fileId: string,
  _sessionId: string
): Promise<FileInfo> => {
  return mockFiles.find((f) => f.fileId === fileId) || mockFiles[0];
};

export const getFileBytes = async (
  _fileId: string,
  _sessionId: string
): Promise<string> => {
  const XLSX = await import("xlsx");
  const wb = XLSX.utils.book_new();
  const data = [
    ["姓名", "部门", "销售额", "季度"],
    ["张三", "销售部", 125000, "Q1"],
    ["李四", "技术部", 89000, "Q1"],
    ["王五", "市场部", 156000, "Q1"],
    ["赵六", "销售部", 98000, "Q1"],
    ["孙七", "技术部", 112000, "Q1"],
    ["周八", "市场部", 145000, "Q1"],
    ["吴九", "销售部", 167000, "Q1"],
    ["郑十", "技术部", 78000, "Q1"],
  ];
  const ws = XLSX.utils.aoa_to_sheet(data);
  XLSX.utils.book_append_sheet(wb, ws, "工作表1");

  const data2 = [
    ["月份", "收入", "支出", "利润"],
    ["1月", 58000, 32000, 26000],
    ["2月", 62000, 35000, 27000],
    ["3月", 71000, 38000, 33000],
    ["4月", 68000, 34000, 34000],
  ];
  const ws2 = XLSX.utils.aoa_to_sheet(data2);
  XLSX.utils.book_append_sheet(wb, ws2, "工作表2");

  const buf = XLSX.write(wb, { type: "array" }) as Uint8Array;
  let binary = "";
  for (let i = 0; i < buf.length; i++) binary += String.fromCharCode(buf[i]);
  return btoa(binary);
};

export const saveWorkbookEdits = async (
  _fileId: string,
  _sessionId: string,
  edits: WorkbookCellEdit[]
): Promise<SaveWorkbookResult> => {
  await delay(240);
  return {
    saved: edits.length > 0,
    cacheRefreshed: true,
    editCount: edits.length,
    affectedCells: edits.map((edit) => `${edit.sheet}!${edit.cell}`),
    warnings: [],
  };
};

export const sendMessage = async (
  req: ChatRequest
): Promise<ChatResponse> => {
  void req;
  await delay(800);
  return {
    messageId: `msg_${mockMessageId++}`,
    text: "这是一个模拟回复。当前运行在浏览器模式，Python 后端未启动。",
    toolCalls: [],
    modifiedCells: [],
  };
};

export const sendMessageStream = async (
  req: ChatRequest
): Promise<string> => {
  const streamId = `stream_${Date.now()}`;
  const text = `已收到您的指令："${req.message}"\n\n当前为浏览器 mock 模式，完整能力需要 Electron + Python 后端。\n\n您可以尝试：\n- 上传 Excel 文件预览\n- 切换工作表\n- 切换深色或浅色主题`;

  for (let i = 0; i < text.length; i += 3) {
    await delay(30);
  }

  return streamId;
};

export const stopGeneration = async (): Promise<void> => {};

export const confirmToolCall = async (_callId: string): Promise<void> => {};

export const listSessions = async (): Promise<Session[]> => {
  return [
    {
      sessionId: mockSessionId,
      name: "工作区 1",
      createdAt: Math.floor(Date.now() / 1000) - 3600,
    },
  ];
};

export const createSession = async (name: string): Promise<Session> => {
  return {
    sessionId: `session-${Date.now()}`,
    name,
    createdAt: Math.floor(Date.now() / 1000),
  };
};

export const deleteSession = async (_sessionId: string): Promise<void> => {};

export const rollbackSnapshot = async (
  snapshotId: string
): Promise<RollbackResult> => {
  return { success: true, snapshotId };
};

export const getSnapshots = async (
  _sessionId: string,
  _fileId: string
): Promise<SnapshotInfo[]> => {
  return mockSnapshots;
};

export const getHistory = async (
  sessionId: string
): Promise<HistoryEntry[]> => {
  return mockHistories.get(sessionId) ?? [];
};

export const saveHistory = async (
  sessionId: string,
  entries: HistoryEntry[]
): Promise<void> => {
  mockHistories.set(sessionId, [...entries]);
};

export const getConfig = async (): Promise<AppConfig> => {
  return structuredClone(currentConfig);
};

export const saveConfig = async (config: AppConfig): Promise<void> => {
  currentConfig = structuredClone(config);
};

export const getDiagnostics = async (): Promise<DiagnosticsInfo> => {
  return {
    logsDir: "C:\\Users\\demo\\.sheetgo\\logs",
    logFilePath: "C:\\Users\\demo\\.sheetgo\\logs\\desktop.log",
  };
};

export const readDesktopLog = async (_limit?: number): Promise<string> => {
  return `{"ts":"2026-04-17T08:30:12.000Z","level":"info","scope":"desktop.ready","message":"Desktop app initialized"}\n{"ts":"2026-04-17T08:31:04.000Z","level":"error","scope":"upload.preload","message":"Unsupported file format"}\n`;
};

export const openDesktopLog = async (): Promise<{ opened: boolean; target: string }> => {
  return { opened: true, target: "C:\\Users\\demo\\.sheetgo\\logs\\desktop.log" };
};

export const openLogsDirectory = async (): Promise<{ opened: boolean; target: string }> => {
  return { opened: true, target: "C:\\Users\\demo\\.sheetgo\\logs" };
};

export const getParsedArtifacts = async (
  fileId: string,
  _sessionId: string
): Promise<ParsedArtifacts> => {
  return {
    fileId,
    paths: {
      schema: "C:\\Users\\demo\\.sheetgo\\workspace\\mock\\cache\\demo_schema.json",
      stats: "C:\\Users\\demo\\.sheetgo\\workspace\\mock\\cache\\demo_stats.json",
      structure: "C:\\Users\\demo\\.sheetgo\\workspace\\mock\\cache\\demo_structure.json",
    },
    schema: {
      fileId,
      sheets: [
        {
          name: "Sheet1",
          rowCount: 156,
          colCount: 4,
          columns: [
            { name: "姓名", dtype: "object" },
            { name: "部门", dtype: "object" },
            { name: "销售额", dtype: "int64" },
          ],
        },
      ],
    },
    stats: {
      totalSheets: 1,
      totalRows: 156,
      totalCols: 4,
      totalFormulas: 3,
      dataQuality: {
        nullRate: 0.02,
        duplicateRows: 0,
      },
    },
    structure: {
      status: "ok",
      summary: "销售台账，按部门和季度记录销售额。",
    },
  };
};

// ==================== Event Listeners ====================

export const onChatStream = (
  _callback: (event: StreamEvent) => void
): Promise<() => void> => {
  return Promise.resolve(() => {});
};

export const onPreloadProgress = (
  callback: (progress: PreloadProgress) => void
): Promise<() => void> => {
  setTimeout(() => {
    const stages: PreloadProgress["stage"][] = [
      "copying",
      "reading",
      "duckdb",
      "schema",
      "sampling",
      "stats",
      "formulas",
      "validation",
      "styles",
      "structure",
      "done",
    ];
    let i = 0;
    const iv = setInterval(() => {
      callback({
        fileId: "demo-file-001",
        stage: stages[Math.min(i, stages.length - 1)],
        progress: Math.min((i + 1) * 10, 100),
        message: `${[
          "正在复制文件",
          "正在读取文件",
          "正在载入数据引擎",
          "正在解析结构",
          "正在提取样本",
          "正在计算统计信息",
          "正在扫描公式",
          "正在校验数据",
          "正在提取样式",
          "正在分析表格结构",
          "处理完成",
        ][Math.min(i, 10)]}`,
      });
      i++;
      if (i > 10) clearInterval(iv);
    }, 600);
  }, 1000);

  return Promise.resolve(() => {});
};

export const onFileChanged = (
  _callback: (info: import("./tauri").FileChangeInfo) => void
): Promise<() => void> => {
  return Promise.resolve(() => {});
};

// ==================== Helpers ====================

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
