# 模块 1: App Shell — Tauri + SolidJS 应用壳

## 概述

负责 Tauri 项目初始化、Rust 后端骨架、SolidJS 前端骨架、IPC 通信桥接、应用布局和全局设置。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| Tauri 项目创建和配置 | 具体业务逻辑（文件处理、Agent） |
| Rust 端 Tauri Commands 定义和注册 | UI 组件实现（见模块 8） |
| Python Sidecar 进程生命周期管理 | 数据库操作（见模块 7） |
| SolidJS 应用入口和路由 | Excel 读写（见模块 4） |
| 全局状态管理框架 | LLM 通信（见模块 6） |
| 工作区目录初始化 | |
| 配置文件管理 | |

## 技术要求

### Tauri 配置

- Tauri 2.0
- 窗口尺寸默认 1280x800，最小 960x600
- 支持文件拖拽上传
- 支持系统托盘（最小化到托盘）
- Python sidecar 配置在 `tauri.conf.json` 的 `externalBin`

### Rust 端

```rust
// src-tauri/src/main.rs
fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            // 文件管理
            commands::file::upload_file,
            commands::file::list_files,
            commands::file::remove_file,
            commands::file::get_file_info,
            // Agent 通信
            commands::agent::chat,
            commands::agent::chat_stream,  // WebSocket 流式
            commands::agent::stop_chat,
            // 会话管理
            commands::session::list_sessions,
            commands::session::create_session,
            commands::session::delete_session,
            commands::session::rollback,
            commands::session::get_history,
            // 配置
            commands::config::get_config,
            commands::config::save_config,
        ])
        .setup(|app| {
            // 初始化工作区目录
            // 启动 Python sidecar
            // 初始化 SQLite
            Ok(())
        })
        .run(tauri::generate_context!()))
        .expect("error while running tauri application");
}
```

### Python Sidecar 管理

```rust
// src-tauri/src/sidecar.rs
use std::process::{Child, Command, Stdio};
use serde_json::Value;

pub struct PythonSidecar {
    process: Option<Child>,
}

impl PythonSidecar {
    /// 启动 Python sidecar 进程
    pub fn start() -> Result<Self, String>;

    /// 发送 JSON-RPC 请求并等待响应
    pub async fn call(&mut self, method: &str, params: Value) -> Result<Value, String>;

    /// 关闭 sidecar 进程
    pub fn shutdown(&mut self) -> Result<(), String>;
}
```

**关键实现**:
- Python 进程通过 stdin/stdout 交换 JSON-RPC 消息（每行一个 JSON 对象）
- Rust 侧维护一个请求 ID 计数器，匹配请求和响应
- Python 进程崩溃时自动重启
- 流式响应（chat_stream）通过 Tauri Event 系统推送

### SolidJS 前端骨架

```typescript
// src/App.tsx — 主布局
export default function App() {
  return (
    <div class="flex h-screen bg-gray-50">
      <FilePanel />           {/* 左侧: 文件面板 (200px) */}
      <div class="flex-1 flex flex-col">
        <ExcelPreview />      {/* 中间: Excel 预览 + Diff */}
        <StatusBar />         {/* 底部: 状态栏 */}
      </div>
      <div class="w-96 flex flex-col border-l">
        <ChatPanel />         {/* 右侧上: 对话面板 */}
        <Timeline />          {/* 右侧下: 操作历史 */}
      </div>
    </div>
  );
}
```

### IPC 桥接层

```typescript
// src/lib/tauri.ts
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

// 类型定义
export interface UploadResult {
  fileId: string;
  fileName: string;
  sheets: string[];
  totalRows: number;
}

export interface ChatRequest {
  sessionId: string;
  fileId: string;
  message: string;
}

export interface ChatResponse {
  messageId: string;
  text: string;
  toolCalls?: ToolCall[];
  modifiedCells?: CellRange[];
}

// 文件操作
export const uploadFile = (path: string) =>
  invoke<UploadResult>('upload_file', { path });

export const listFiles = (sessionId: string) =>
  invoke<FileInfo[]>('list_files', { sessionId });

// Agent 对话
export const sendMessage = (req: ChatRequest) =>
  invoke<ChatResponse>('chat', req);

// 监听流式事件
export const onChatStream = (callback: (event: StreamEvent) => void) =>
  listen('chat-stream', (event) => callback(event.payload as StreamEvent));

// 监听预加载进度
export const onPreloadProgress = (callback: (progress: PreloadProgress) => void) =>
  listen('preload-progress', (event) => callback(event.payload as PreloadProgress));
```

### 工作区目录管理

```rust
// src-tauri/src/workspace.rs
use std::path::PathBuf;

pub struct Workspace {
    base_dir: PathBuf,  // ~/.sheetgo/
}

impl Workspace {
    /// 初始化工作区（首次运行创建目录结构）
    pub fn init() -> Result<Self, String>;

    /// 创建新的会话工作区
    pub fn create_session(&self, session_id: &str) -> Result<SessionWorkspace, String>;

    /// 获取会话工作区
    pub fn get_session(&self, session_id: &str) -> Result<SessionWorkspace, String>;

    /// 清理过期会话
    pub fn cleanup(&self, max_age_days: u32) -> Result<(), String>;
}

pub struct SessionWorkspace {
    pub source_dir: PathBuf,    // source/
    pub working_dir: PathBuf,   // working/
    pub cache_dir: PathBuf,     // cache/
    pub snapshot_dir: PathBuf,  // snapshots/
    pub export_dir: PathBuf,    // exports/
}

impl SessionWorkspace {
    /// 复制上传文件到 source/ 和 working/
    pub fn import_file(&self, source_path: &PathBuf) -> Result<String, String>;

    /// 获取缓存路径
    pub fn cache_path(&self, file_id: &str, suffix: &str) -> PathBuf;

    /// 获取最新快照
    pub fn latest_snapshot(&self) -> Option<PathBuf>;
}
```

## 全局配置

```json
// ~/.sheetgo/config.json
{
  "llm": {
    "provider": "openai",          // openai / anthropic / azure / ollama / custom
    "model": "gpt-4o",
    "apiKey": "sk-xxx",
    "baseUrl": "",                 // 自定义端点
    "temperature": 0.1,
    "maxTokens": 4096
  },
  "ui": {
    "theme": "light",              // light / dark / system
    "language": "zh-CN",
    "previewRows": 100             // Excel 预览显示行数
  },
  "advanced": {
    "maxFileSize": 104857600,      // 100MB
    "preloadSampleRows": 20,
    "snapshotMaxCount": 50,
    "sandboxEnabled": true
  }
}
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `src-tauri/Cargo.toml` | Rust 依赖 |
| `src-tauri/tauri.conf.json` | Tauri 配置 |
| `src-tauri/src/main.rs` | 入口，Commands 注册 |
| `src-tauri/src/commands/mod.rs` | Commands 模块 |
| `src-tauri/src/commands/file.rs` | 文件管理 IPC 命令 |
| `src-tauri/src/commands/agent.rs` | Agent IPC 命令 |
| `src-tauri/src/commands/session.rs` | 会话 IPC 命令 |
| `src-tauri/src/commands/config.rs` | 配置 IPC 命令 |
| `src-tauri/src/sidecar.rs` | Python 进程管理 |
| `src-tauri/src/workspace.rs` | 工作区目录管理 |
| `src/main.tsx` | SolidJS 入口 |
| `src/App.tsx` | 主布局组件 |
| `src/index.html` | HTML 模板 |
| `src/lib/tauri.ts` | Tauri IPC 封装 |
| `src/stores/` | 状态管理 |
| `src/styles/global.css` | 全局样式 |

## 测试要求

- Rust: Tauri Commands 的单元测试（mock sidecar）
- TS: IPC 桥接层的类型测试
- 集成: 应用启动 → 创建会话 → 退出 的完整流程
