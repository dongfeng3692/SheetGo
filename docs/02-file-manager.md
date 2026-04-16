# 模块 2: File Manager — 文件上传与隔离管理

## 概述

负责用户文件的上传、隔离存储、生命周期管理。确保每个文件在上传后立即进入隔离工作区，原始文件永远不被修改。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 文件上传处理（拖拽/选择/命令行参数） | 预加载管线（见模块 3） |
| 文件格式检测（xlsx/xlsm/csv/tsv） | 数据分析（见模块 4/6） |
| 文件 hash 计算 | Excel 预览渲染（见模块 8） |
| 复制到 source/（只读）和 working/（副本） | |
| 文件元信息记录 | |
| 重复文件检测 | |
| 文件删除/清理 | |
| 多文件管理（同一会话多文件） | |

## 数据结构

```typescript
// 前端使用的文件信息类型
interface FileInfo {
  fileId: string;           // UUID
  fileName: string;         // 原始文件名
  fileSize: number;         // 字节数
  fileHash: string;         // SHA-256
  fileType: 'xlsx' | 'xlsm' | 'csv' | 'tsv';
  sheets: SheetMeta[];      // 工作表列表
  totalRows: number;        // 总行数（所有 sheet）
  totalCols: number;        // 最大列数
  uploadTime: string;       // ISO 时间戳
  preloadStatus: 'pending' | 'loading' | 'done' | 'error';
  preloadProgress?: number; // 0-100
}
```

```rust
// Rust 端文件管理
#[derive(Serialize, Deserialize)]
pub struct FileRecord {
    pub file_id: String,
    pub session_id: String,
    pub file_name: String,
    pub file_size: u64,
    pub file_hash: String,
    pub file_type: String,
    pub source_path: PathBuf,    // source/ 下的路径
    pub working_path: PathBuf,   // working/ 下的路径
    pub created_at: DateTime<Utc>,
    pub preload_status: String,
}
```

## 接口定义

### Tauri Commands（Rust → 前端）

```rust
#[tauri::command]
async fn upload_file(
    path: String,              // 用户选择的文件路径
    session_id: String,        // 当前会话 ID
) -> Result<FileInfo, String>;

#[tauri::command]
async fn list_files(
    session_id: String,
) -> Result<Vec<FileInfo>, String>;

#[tauri::command]
async fn remove_file(
    file_id: String,
    session_id: String,
) -> Result<(), String>;

#[tauri::command]
async fn get_file_info(
    file_id: String,
) -> Result<FileInfo, String>;

#[tauri::command]
async fn export_file(
    file_id: String,
    dest_path: String,         // 用户选择的导出路径
    format: String,            // "xlsx" | "csv" | "pdf"
) -> Result<(), String>;
```

### Python JSON-RPC（文件管理相关）

```json
{ "method": "file.import", "params": { "file_id": "xxx", "source_path": "/path/source/xxx.xlsx", "working_path": "/path/working/xxx.xlsx" } }
```

## 实现要点

### 1. 上传流程

```
用户拖拽/选择文件
    │
    ▼
① 校验: 文件扩展名、大小（≤100MB）
    │
    ▼
② 计算 SHA-256 hash（流式读取，不阻塞 UI）
    │
    ▼
③ 复制到 source/{file_id}.xlsx（只读标记）
    │
    ▼
④ 复制到 working/{file_id}.xlsx（工作副本）
    │
    ▼
⑤ 记录到 SQLite（file_records 表）
    │
    ▼
⑥ 返回 FileInfo → 前端显示文件列表
    │
    ▼
⑦ 触发预加载管线（模块 3）→ 通过 Tauri Event 推送进度
```

### 2. 文件格式检测

```rust
fn detect_file_type(path: &Path) -> Result<FileType, String> {
    match path.extension().and_then(|e| e.to_str()) {
        Some("xlsx") => {
            // 进一步验证 ZIP magic bytes: PK\x03\x04
            let mut f = File::open(path)?;
            let mut magic = [0u8; 4];
            f.read_exact(&mut magic)?;
            if &magic == b"PK\x03\x04" { Ok(FileType::Xlsx) }
            else { Err("Invalid xlsx file".into()) }
        }
        Some("xlsm") => Ok(FileType::Xlsm),  // 同样检查 ZIP magic
        Some("csv") => Ok(FileType::Csv),
        Some("tsv") => Ok(FileType::Tsv),
        _ => Err("Unsupported file type".into()),
    }
}
```

### 3. 隔离策略

- `source/` 目录下的文件设置**只读属性**（Rust: `set_permissions` 只读）
- 每次修改操作作用于 `working/` 下的副本
- 快照系统（模块 7）记录 working 文件的增量变更
- 导出时从 working/ 复制到用户指定路径

### 4. 重复文件处理

```rust
fn check_duplicate(hash: &str, session_id: &str, db: &Database) -> Option<FileRecord> {
    // 按 hash 查找同一会话中是否已有相同文件
    // 如果有，提示用户是否复用（避免重复上传）
}
```

### 5. 多文件管理

同一会话可上传多个文件。每个文件独立预加载，DuckDB 中注册为不同的表名。LLM 可以跨文件查询（JOIN）。

## SQLite 表结构

```sql
CREATE TABLE file_records (
    file_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_hash TEXT NOT NULL,
    file_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    working_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    preload_status TEXT DEFAULT 'pending',
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_file_records_session ON file_records(session_id);
CREATE INDEX idx_file_records_hash ON file_records(file_hash);
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `src-tauri/src/commands/file.rs` | 文件管理 Tauri Commands |
| `src-tauri/src/workspace.rs` | 工作区目录操作 |
| `src/components/FilePanel.tsx` | 文件面板 UI |
| `src/stores/fileStore.ts` | 文件状态管理 |

## 依赖

- 模块 1（App Shell）: 提供 Tauri 框架、workspace 目录结构
- 模块 3（Preload Pipeline）: 上传完成后触发预加载

## 测试要求

- 上传 xlsx/csv/tsv 文件 → 验证 source/working 目录生成
- 上传重复文件 → 检测到并提示
- 上传超大文件 → 错误提示
- 删除文件 → source/working/cache 清理
- 文件格式校验 → 非 xlsx 文件拒绝
