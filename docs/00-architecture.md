# SheetGo — 总架构文档

## 项目定位

开源 AI Excel 桌面客户端。用户上传 Excel 文件，通过自然语言对话完成数据分析、清洗、图表、公式等操作。无需服务端，本地运行。

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 桌面壳 | Tauri 2.0 | Rust 后端，~5MB 安装包，跨平台 |
| 前端 | SolidJS + TailwindCSS | 响应式，无虚拟 DOM |
| Excel 预览 | SheetJS (xlsx) | 前端渲染 Excel 内容 |
| 数据引擎 | Python Sidecar | pandas/DuckDB/openpyxl/calamine |
| LLM | LiteLLM | 100+ 模型统一接口，用户自带 API Key |
| 本地存储 | SQLite | 会话、文件元信息、快照 |
| Excel 读写 | openpyxl + calamine + XML 辅助脚本 | 混合策略 |

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Tauri Desktop App                        │
│                                                             │
│  ┌─── Frontend (SolidJS + TailwindCSS) ──────────────────┐ │
│  │                                                         │ │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐ │ │
│  │  │ FilePanel│  │ ExcelPreview │  │   ChatPanel      │ │ │
│  │  │ 文件管理  │  │ SheetJS 渲染  │  │   对话面板       │ │ │
│  │  └──────────┘  └──────────────┘  └──────────────────┘ │ │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐ │ │
│  │  │ DiffView │  │ ChartPreview │  │   Timeline       │ │ │
│  │  │ 差异对比  │  │ 图表预览      │  │   操作历史       │ │ │
│  │  └──────────┘  └──────────────┘  └──────────────────┘ │ │
│  └───────────────────────┬────────────────────────────────┘ │
│                          │ Tauri IPC (invoke)                │
│  ┌─── Rust Backend ──────┴────────────────────────────────┐ │
│  │                                                         │ │
│  │  FileManager ←→ Python Sidecar ←→ AgentEngine          │ │
│  │       │              │                   │               │ │
│  │  文件隔离       数据预加载/DuckDB     LiteLLM/对话循环   │ │
│  │  目录管理       Excel 读写/验证        工具注册/调用     │ │
│  │                XML 辅助脚本           Prompt 构建        │ │
│  │       │              │                   │               │ │
│  │  ┌─────────────────────────────────────────────────┐    │ │
│  │  │              SessionStore (SQLite)               │    │ │
│  │  │    会话 │ 消息 │ 快照 │ 记忆 │ 文件元信息         │    │ │
│  │  └─────────────────────────────────────────────────┘    │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 目录结构

```
sheetgo/
├── src-tauri/                    # Rust 后端（Tauri）
│   ├── src/
│   │   ├── main.rs               # Tauri 入口
│   │   ├── commands/             # Tauri Commands（IPC 接口）
│   │   │   ├── mod.rs
│   │   │   ├── file.rs           # 文件管理命令
│   │   │   ├── agent.rs          # Agent 通信命令
│   │   │   └── session.rs        # 会话管理命令
│   │   ├── sidecar.rs            # Python 进程管理
│   │   └── workspace.rs          # 工作区目录管理
│   ├── Cargo.toml
│   └── tauri.conf.json
│
├── src/                           # SolidJS 前端
│   ├── App.tsx                    # 主布局
│   ├── main.tsx                   # 入口
│   ├── index.html
│   ├── components/
│   │   ├── FilePanel.tsx          # 文件面板
│   │   ├── ExcelPreview.tsx       # Excel 预览
│   │   ├── ChatPanel.tsx          # 对话面板
│   │   ├── DiffView.tsx           # 差异对比
│   │   ├── Timeline.tsx           # 操作历史时间线
│   │   ├── Settings.tsx           # 设置页面
│   │   └── PreloadProgress.tsx    # 预加载进度
│   ├── stores/
│   │   ├── fileStore.ts           # 文件状态
│   │   ├── chatStore.ts           # 对话状态
│   │   └── sessionStore.ts        # 会话状态
│   ├── lib/
│   │   └── tauri.ts               # Tauri IPC 封装
│   └── styles/
│       └── global.css
│
├── python/                        # Python Sidecar
│   ├── main.py                    # Sidecar 入口（stdin/stdout JSON-RPC）
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── engine.py              # Agent 对话循环
│   │   ├── prompt_builder.py      # Prompt 构建
│   │   ├── tool_registry.py       # 工具注册中心
│   │   └── llm_provider.py        # LiteLLM 封装
│   ├── tools/                     # Excel 操作工具
│   │   ├── __init__.py
│   │   ├── base.py                # 工具基类
│   │   ├── query_data.py          # SQL 查询（DuckDB）
│   │   ├── read_sheet.py          # 读取工作表
│   │   ├── write_cells.py         # 写入单元格
│   │   ├── add_formula.py         # 添加公式
│   │   ├── add_column.py          # 增加列
│   │   ├── insert_row.py          # 插入行
│   │   ├── create_chart.py        # 创建图表
│   │   ├── apply_style.py         # 应用样式
│   │   ├── sheet_info.py          # 工作簿元信息
│   │   ├── export_file.py         # 导出文件
│   │   └── validate.py            # 验证工具
│   ├── excel/                     # Excel 底层操作
│   │   ├── __init__.py
│   │   ├── reader.py              # calamine/openpyxl 读取
│   │   ├── writer.py              # XML 级精确写入
│   │   ├── xml_helpers.py         # XML pack/unpack/shift
│   │   ├── formula_parser.py      # 公式解析与依赖分析
│   │   ├── style_engine.py        # 样式系统（金融格式模板）
│   │   └── templates/             # XML 模板（新建文件用）
│   │       └── minimal_xlsx/      # 最小 xlsx 骨架
│   ├── preload/                   # 预加载管线
│   │   ├── __init__.py
│   │   ├── pipeline.py            # 预加载主流程
│   │   ├── schema_extractor.py    # Schema 提取
│   │   ├── stats_calculator.py    # 统计信息计算
│   │   └── formula_scanner.py     # 公式扫描
│   ├── validation/                # 验证引擎
│   │   ├── __init__.py
│   │   ├── formula_check.py       # 公式错误检测
│   │   ├── reference_check.py     # 引用范围校验
│   │   ├── compat_check.py        # 兼容性检查（禁用函数）
│   │   ├── data_quality.py        # 数据质量评估
│   │   └── openxml_validate.py    # OpenXML 结构验证
│   ├── session/                   # 会话与存储
│   │   ├── __init__.py
│   │   ├── database.py            # SQLite CRUD
│   │   ├── memory.py              # 分层记忆管理
│   │   ├── snapshot.py            # 操作快照
│   │   └── rollback.py            # 回滚引擎
│   ├── sandbox/                   # 代码执行沙箱
│   │   ├── __init__.py
│   │   ├── ast_validator.py       # AST 代码校验
│   │   └── executor.py            # 受限执行环境
│   └── requirements.txt
│
├── docs/                          # 开发文档
│   ├── 00-architecture.md         # 本文件
│   ├── 01-app-shell.md            # 模块1: 应用壳
│   ├── 02-file-manager.md         # 模块2: 文件管理
│   ├── 03-preload-pipeline.md     # 模块3: 预加载管线
│   ├── 04-excel-engine.md         # 模块4: Excel 引擎
│   ├── 05-validation.md           # 模块5: 验证引擎
│   ├── 06-agent-core.md           # 模块6: Agent 核心
│   ├── 07-session-store.md        # 模块7: 会话存储
│   └── 08-ui-components.md        # 模块8: UI 组件
│
├── CLAUDE.md
└── README.md
```

## 模块拆分与依赖

共 8 个模块，按独立可分派的原则拆分。每个模块有清晰的对外接口。

```
模块依赖关系（箭头表示"依赖"）:

  01-app-shell
    ├──→ 02-file-manager
    ├──→ 06-agent-core
    ├──→ 07-session-store
    └──→ 08-ui-components

  02-file-manager
    └──→ 03-preload-pipeline

  03-preload-pipeline
    ├──→ 04-excel-engine (reader 部分)
    └──→ 05-validation

  06-agent-core
    ├──→ 04-excel-engine (tools 部分)
    ├──→ 05-validation
    └──→ 07-session-store

  08-ui-components
    └──→ 01-app-shell (Tauri IPC)
```

**模块开发顺序建议**:

```
第一批（可并行）: 01-app-shell, 04-excel-engine, 05-validation
第二批（依赖第一批）: 02-file-manager, 03-preload-pipeline, 07-session-store
第三批（依赖第二批）: 06-agent-core
第四批（依赖第三批）: 08-ui-components
```

## 模块间通信接口

所有模块间通信通过 Tauri IPC + Python JSON-RPC 两条路径：

### Tauri IPC（Rust ↔ SolidJS 前端）

前端通过 `invoke()` 调用 Rust 命令：

```typescript
// 前端调用示例
import { invoke } from '@tauri-apps/api/core';

// 文件管理
const result = await invoke('upload_file', { path: '/path/to/file.xlsx' });
const preloadStatus = await invoke('get_preload_status', { fileId: 'xxx' });

// Agent 对话
const response = await invoke('chat', { fileId: 'xxx', message: '按地区汇总' });

// 会话管理
const sessions = await invoke('list_sessions');
await invoke('rollback', { snapshotId: 'snap_003' });
```

### Python JSON-RPC（Rust ↔ Python Sidecar）

Rust 启动 Python sidecar 进程，通过 stdin/stdout 交换 JSON-RPC 消息：

```json
// Request
{ "jsonrpc": "2.0", "id": 1, "method": "preload", "params": { "file_id": "xxx", "file_path": "/path/working/xxx.xlsx" } }

// Response
{ "jsonrpc": "2.0", "id": 1, "result": { "status": "ok", "schema": {...}, "stats": {...} } }

// Streaming (tool execution progress)
{ "jsonrpc": "2.0", "method": "progress", "params": { "type": "tool_call", "tool": "query_data", "status": "executing" } }
```

### 数据文件约定

所有模块通过文件系统共享数据，路径约定：

```
~/.sheetgo/
├── config.json                   # 全局配置（LLM API Key 等）
├── sessions.db                   # SQLite 数据库
└── workspace/{session_id}/
    ├── source/{file_id}.xlsx     # 原始文件（只读）
    ├── working/{file_id}.xlsx    # 工作副本
    ├── cache/
    │   ├── {file_id}.duckdb      # DuckDB 数据库
    │   ├── {file_id}_schema.json # Schema 缓存
    │   ├── {file_id}_sample.json # 样本数据缓存
    │   └── {file_id}_stats.json  # 统计信息缓存
    ├── snapshots/
    │   └── {snapshot_id}.json    # 操作快照
    └── exports/                  # 导出文件
```
