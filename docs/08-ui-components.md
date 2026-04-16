# 模块 8: UI Components — SolidJS 前端组件

## 概述

所有 SolidJS 前端 UI 组件：Excel 预览器、对话面板、差异对比、操作历史时间线、文件管理面板、设置页面、预加载进度。组件通过 Tauri IPC 与后端通信。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 所有 SolidJS 组件实现 | 后端逻辑 |
| 状态管理（SolidJS stores） | Tauri IPC 定义（模块 1） |
| Excel 预览渲染（SheetJS） | 数据处理（模块 3/4） |
| 对话消息渲染 | Agent 引擎（模块 6） |
| 差异对比展示 | |
| 操作历史时间线 | |
| 设置页面 | |
| 响应式布局 | |
| 主题（亮色/暗色） | |

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| SolidJS | ^1.9 | 响应式 UI 框架 |
| TailwindCSS | ^4.0 | 样式系统 |
| SheetJS (xlsx) | ^0.18 | Excel 前端解析和渲染 |
| @tauri-apps/api | ^2.0 | IPC 通信 |

## 组件清单

### 1. App.tsx — 主布局

```tsx
// 三栏布局：文件面板 | Excel预览+Diff | Chat+Timeline
// 响应式：窗口宽度 < 960px 时 Chat 面板覆盖在预览上方
export default function App() {
  return (
    <div class="flex h-screen bg-gray-50 dark:bg-gray-900">
      <FilePanel />              {/* 左侧 200px */}
      <div class="flex-1 flex flex-col min-w-0">
        <TabBar />               {/* Sheet 标签栏 */}
        <div class="flex-1 relative">
          <ExcelPreview />       {/* Excel 预览 */}
          <DiffOverlay />        {/* Diff 高亮叠层 */}
        </div>
        <StatusBar />            {/* 底部状态栏 */}
      </div>
      <div class="w-[380px] flex flex-col border-l dark:border-gray-700">
        <ChatPanel />            {/* 对话面板（上部分，flex-1） */}
        <Timeline />             {/* 操作历史（下部分，200px） */}
      </div>
    </div>
  );
}
```

### 2. FilePanel — 文件管理面板

```tsx
interface FilePanelProps {}

// 功能:
// - 拖拽上传区域（带虚线边框和图标）
// - 文件列表（文件名 + 行数 + 预加载状态）
// - 文件右键菜单（删除、导出、复制路径）
// - 预加载进度条（上传后显示）

// 状态:
// - files: FileInfo[]  （来自 fileStore）
// - dragOver: boolean
// - uploading: boolean
```

### 3. ExcelPreview — Excel 预览器

```tsx
interface ExcelPreviewProps {
  fileId: string;
  sheetName: string;
}

// 功能:
// - 使用 SheetJS 解析 working/ 文件并渲染为 HTML 表格
// - Sheet 标签栏（切换工作表）
// - 单元格选中（点击单元格时显示地址和值）
// - 冻结表头（滚动时第一行固定）
// - 公式/值切换（显示公式还是计算值）
// - 大文件虚拟滚动（只渲染可见行）
// - 变更高亮（Agent 修改的单元格用黄色背景标记）

// 实现:
// - 使用 <table> 渲染，CSS 控制冻结和滚动
// - 大文件（>1万行）使用虚拟滚动（只渲染可视区域 ± buffer）
// - 通过 Tauri invoke('read_file_bytes') 读取文件二进制，前端 SheetJS 解析
```

### 4. ChatPanel — 对话面板

```tsx
interface ChatPanelProps {}

// 功能:
// - 消息列表（用户消息 + AI 回复 + 工具调用记录）
// - 流式文本显示（逐字输出效果）
// - 工具调用展示（折叠卡片: 工具名 → 参数 → 结果）
// - 代码块渲染（语法高亮）
// - 表格结果渲染（工具返回的 DataFrame 展示为 HTML 表格）
// - 输入框（多行、Shift+Enter 换行、Enter 发送）
// - 快捷操作按钮（📎附加文件、📊生成图表、🔄撤销上一步）
// - 停止生成按钮（AI 回复过程中可中断）
// - 模型选择下拉（如果配置了多个 LLM）

// 消息类型渲染:
// - 用户消息: 右对齐，蓝色背景
// - AI 文本: 左对齐，白色背景，支持 Markdown 渲染
// - 工具调用: 折叠卡片，显示工具名和执行状态
//   - 执行中: 旋转 loading 图标
//   - 成功: 绿色勾 + 结果摘要
//   - 失败: 红色叉 + 错误信息
//   - 需要确认: 黄色提示 + 确认/拒绝按钮
```

### 5. DiffView — 差异对比

```tsx
interface DiffViewProps {
  snapshotId: string;
}

// 功能:
// - 修改前/后并排对比（split view）
// - 或统一视图（inline diff）
// - 变更单元格高亮（新增=绿色，删除=红色，修改=黄色）
// - 公式变更展示（显示旧公式 vs 新公式）
// - 位置导航（点击变更列表跳转到对应单元格）

// 展示形式:
// - 叠加在 ExcelPreview 上方（半透明覆盖层）
// - 或独立的 Diff 面板（在预览区域下方）
```

### 6. Timeline — 操作历史时间线

```tsx
interface TimelineProps {}

// 功能:
// - 垂直时间线，每个节点是一次操作
// - 节点显示: 操作描述 + 时间 + 工具图标
// - 当前位置标记（蓝色圆点）
// - 鼠标悬停显示 diff 摘要
// - 点击节点 → 回滚预览（显示将丢失的修改）
// - 确认回滚按钮
// - 分支显示（回滚后再修改会创建分支）

// 样式:
// - 竖线连接节点
// - 节点: 圆形图标（查询=🔍, 写入=✏️, 图表=📊, 公式=fx）
// - 当前节点高亮
// - 未来节点（回滚后的分支）灰色虚线
```

### 7. PreloadProgress — 预加载进度

```tsx
interface PreloadProgressProps {
  fileId: string;
}

// 功能:
// - 显示在文件列表项下方或 Excel 预览区域
// - 步骤进度条（10 个步骤）
// - 当前步骤描述（"正在加载到 DuckDB (45%)..."）
// - 已用时间
// - 完成后淡出

// 步骤列表:
// 1. 复制文件
// 2. 读取数据
// 3. 加载到 DuckDB
// 4. 提取 Schema
// 5. 提取样本
// 6. 计算统计
// 7. 扫描公式
// 8. 验证检查
// 9. 索引样式
// 10. 完成
```

### 8. Settings — 设置页面

```tsx
// 功能:
// - LLM 配置: Provider, Model, API Key, Base URL
// - 通用设置: 语言、主题、预览行数
// - 高级设置: 最大文件大小、快照数量上限
// - API Key 输入框用密码模式
// - 保存后立即生效

// 布局:
// - 从顶部滑下的面板（覆盖主界面）
// - 或独立的设置窗口
```

### 9. StatusBar — 状态栏

```tsx
// 功能:
// - LLM 连接状态（🟢已连接 / 🔴未连接 / 🟡连接中）
// - 当前模型名称
// - 当前文件的行数/列数
// - 本次会话 token 用量和费用
// - 上次操作耗时
```

## 状态管理

```typescript
// src/stores/fileStore.ts
interface FileState {
  files: FileInfo[];
  activeFileId: string | null;
  activeSheet: string;
  preloadStatus: Map<string, PreloadProgress>;
}

// Actions:
// uploadFile(path: string)
// selectFile(fileId: string)
// selectSheet(sheetName: string)
// removeFile(fileId: string)
// updatePreloadProgress(fileId: string, progress: PreloadProgress)

// src/stores/chatStore.ts
interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  currentToolCalls: ToolCallInfo[];
}

// Actions:
// sendMessage(text: string)
// stopGeneration()
// confirmToolCall(callId: string)
// rejectToolCall(callId: string)

// src/stores/sessionStore.ts
interface SessionState {
  sessions: Session[];
  activeSessionId: string | null;
  snapshots: SnapshotInfo[];
}

// Actions:
// createSession()
// switchSession(sessionId: string)
// rollback(snapshotId: string)
```

## Tauri IPC 调用

所有组件通过 `src/lib/tauri.ts` 封装层调用后端：

```typescript
// 文件操作
uploadFile(path: string): Promise<FileInfo>
removeFile(fileId: string): Promise<void>
getFileBytes(fileId: string): Promise<number[]>  // SheetJS 解析用

// Agent 对话
sendMessage(sessionId: string, fileId: string, text: string): Promise<ChatResponse>
stopGeneration(): Promise<void>
confirmToolCall(callId: string): Promise<void>

// 会话管理
listSessions(): Promise<Session[]>
createSession(): Promise<Session>
rollback(snapshotId: string): Promise<RollbackResult>
getSnapshots(sessionId: string, fileId: string): Promise<SnapshotInfo[]>

// 配置
getConfig(): Promise<Config>
saveConfig(config: Config): Promise<void>

// 事件监听
onChatStream(callback: (event: StreamEvent) => void): (() => void)
onPreloadProgress(callback: (p: PreloadProgress) => void): (() => void)
onFileChanged(callback: (info: FileChangeInfo) => void): (() => void)
```

## 样式规范

### 主题

```css
/* 亮色主题（默认） */
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f9fafb;
  --bg-tertiary: #f3f4f6;
  --text-primary: #111827;
  --text-secondary: #6b7280;
  --border: #e5e7eb;
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --success: #10b981;
  --warning: #f59e0b;
  --error: #ef4444;
}

/* 暗色主题 */
.dark {
  --bg-primary: #1f2937;
  --bg-secondary: #111827;
  --bg-tertiary: #374151;
  --text-primary: #f9fafb;
  --text-secondary: #9ca3af;
  --border: #4b5563;
}

/* Excel 预览区域特殊样式 */
.excel-cell {
  border: 1px solid var(--border);
  padding: 2px 6px;
  font-size: 13px;
  font-family: 'Consolas', 'Monaco', monospace;
}

.excel-cell-modified {
  background-color: #fef3c7 !important;  /* 黄色标记修改 */
}

.excel-cell-header {
  background-color: var(--bg-tertiary);
  font-weight: 600;
}
```

### Excel 预览虚拟滚动

```typescript
// 大文件（>10000 行）使用虚拟滚动
const VISIBLE_ROWS = 50;     // 可视区域渲染行数
const BUFFER_ROWS = 10;      // 上下缓冲区

function VirtualScroller(props: { data: Cell[][]; rowHeight: number }) {
  const [scrollTop, setScrollTop] = createSignal(0);
  const startIndex = () => Math.max(0, Math.floor(scrollTop() / props.rowHeight) - BUFFER_ROWS);
  const endIndex = () => Math.min(props.data.length, startIndex() + VISIBLE_ROWS + 2 * BUFFER_ROWS);
  const visibleData = () => props.data.slice(startIndex(), endIndex());
  const topPadding = () => startIndex() * props.rowHeight;
  const bottomPadding = () => (props.data.length - endIndex()) * props.rowHeight;

  return (
    <div class="overflow-auto flex-1" onScroll={e => setScrollTop(e.target.scrollTop)}>
      <div style={{ height: topPadding() }} />
      <table>{/* render visibleData() */}</table>
      <div style={{ height: bottomPadding() }} />
    </div>
  );
}
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `src/App.tsx` | 主布局 |
| `src/main.tsx` | 入口 |
| `src/index.html` | HTML 模板 |
| `src/components/FilePanel.tsx` | 文件管理面板 |
| `src/components/ExcelPreview.tsx` | Excel 预览器 |
| `src/components/ChatPanel.tsx` | 对话面板 |
| `src/components/DiffView.tsx` | 差异对比 |
| `src/components/Timeline.tsx` | 操作历史时间线 |
| `src/components/PreloadProgress.tsx` | 预加载进度 |
| `src/components/Settings.tsx` | 设置页面 |
| `src/components/StatusBar.tsx` | 状态栏 |
| `src/components/TabBar.tsx` | Sheet 标签栏 |
| `src/stores/fileStore.ts` | 文件状态管理 |
| `src/stores/chatStore.ts` | 对话状态管理 |
| `src/stores/sessionStore.ts` | 会话状态管理 |
| `src/lib/tauri.ts` | Tauri IPC 封装 |
| `src/lib/sheetjs.ts` | SheetJS 解析封装 |
| `src/styles/global.css` | 全局样式和主题变量 |

## 依赖

- 模块 1（App Shell）: Tauri 框架和 IPC 接口

## 测试要求

- 组件单元测试（SolidJS Testing Library）
- FilePanel: 拖拽上传交互
- ExcelPreview: 虚拟滚动性能（10 万行）
- ChatPanel: 流式消息渲染
- Timeline: 回滚交互
- 暗色/亮色主题切换
- 窗口缩放响应式布局
