# 模块 7: Session Store — 会话存储与快照回滚

## 概述

负责会话持久化（SQLite）、分层记忆管理、操作快照和回滚引擎。确保用户关闭应用后可恢复会话，且每次修改都可追溯和撤销。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| SQLite 数据库 schema 和 CRUD | 对话循环（模块 6） |
| 会话创建/列表/删除 | LLM 通信（模块 6） |
| 消息持久化和检索 | UI 渲染（模块 8） |
| 分层记忆（短期/中期/长期） | |
| 对话压缩（上下文窗口管理） | |
| 操作快照创建和管理 | |
| 回滚引擎（恢复到任意快照） | |
| 数据库迁移 | |

## 数据结构

### SQLite Schema

```sql
-- 会话表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT 'New Session',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    agent_type TEXT DEFAULT 'main',
    settings TEXT DEFAULT '{}',          -- JSON: 会话级设置
    total_tokens INTEGER DEFAULT 0,
    total_cost REAL DEFAULT 0.0
);

-- 消息表
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,                  -- "user" | "assistant" | "tool_result" | "system"
    content TEXT NOT NULL DEFAULT '',
    tool_calls TEXT,                     -- JSON: 工具调用列表
    tool_results TEXT,                   -- JSON: 工具结果列表
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX idx_messages_session ON messages(session_id, created_at);

-- 快照表
CREATE TABLE snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    parent_id TEXT,                      -- 父快照 ID（形成链）
    description TEXT NOT NULL,           -- 操作描述
    tool_calls TEXT,                     -- JSON: 触发此快照的工具调用
    diff TEXT,                           -- JSON: 文件变更 diff
    file_hash TEXT,                      -- working 文件的 hash
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES snapshots(id)
);
CREATE INDEX idx_snapshots_session ON snapshots(session_id, created_at);

-- 记忆表（长期记忆）
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    category TEXT NOT NULL,              -- "preference" | "pattern" | "context"
    key TEXT NOT NULL,
    value TEXT NOT NULL,                 -- JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    UNIQUE(session_id, category, key)
);

-- 文件记录表
CREATE TABLE file_records (
    file_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_hash TEXT NOT NULL,
    file_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    working_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    preload_status TEXT DEFAULT 'pending',
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX idx_file_records_session ON file_records(session_id);
```

### Python 数据模型

```python
@dataclass
class Session:
    id: str
    name: str
    created_at: str
    updated_at: str
    agent_type: str
    settings: dict
    total_tokens: int
    total_cost: float

@dataclass
class MessageRecord:
    id: str
    session_id: str
    role: str
    content: str
    tool_calls: list[dict] | None
    tool_results: list[dict] | None
    tokens_in: int
    tokens_out: int
    created_at: str

@dataclass
class SnapshotRecord:
    id: str
    session_id: str
    file_id: str
    parent_id: str | None
    description: str
    tool_calls: list[dict] | None
    diff: dict                          # 文件变更 diff
    file_hash: str
    created_at: str

@dataclass
class MemoryEntry:
    id: str
    session_id: str
    category: str
    key: str
    value: Any
    created_at: str
    updated_at: str
```

## 接口定义

### Database — 数据库 CRUD

```python
class Database:
    """SQLite 数据库操作"""

    def __init__(self, db_path: str):
        """初始化连接，运行迁移"""

    # --- Session ---

    def create_session(self, name: str = "New Session") -> Session:
        """创建新会话"""

    def get_session(self, session_id: str) -> Session | None:
        """获取会话"""

    def list_sessions(self, limit: int = 50) -> list[Session]:
        """列出会话（按更新时间倒序）"""

    def update_session(self, session_id: str, **kwargs) -> None:
        """更新会话字段"""

    def delete_session(self, session_id: str) -> None:
        """删除会话（级联删除消息、快照、记忆）"""

    # --- Messages ---

    def save_message(self, message: MessageRecord) -> None:
        """保存消息"""

    def get_messages(self, session_id: str,
                     limit: int = 50,
                     before: str | None = None) -> list[MessageRecord]:
        """获取消息列表（分页）"""

    def get_recent_messages(self, session_id: str,
                            count: int = 10) -> list[MessageRecord]:
        """获取最近 N 条消息（用于构建 Prompt）"""

    def delete_old_messages(self, session_id: str,
                            keep_recent: int = 100) -> int:
        """删除旧消息（保留最近 N 条）"""

    # --- Snapshots ---

    def create_snapshot(self, snapshot: SnapshotRecord) -> None:
        """保存快照记录"""

    def get_snapshot(self, snapshot_id: str) -> SnapshotRecord | None:
        """获取快照"""

    def get_snapshot_chain(self, session_id: str,
                          file_id: str) -> list[SnapshotRecord]:
        """获取文件的快照链（按时间正序）"""

    def get_latest_snapshot(self, session_id: str,
                           file_id: str) -> SnapshotRecord | None:
        """获取文件最新快照"""

    def get_children(self, snapshot_id: str) -> list[SnapshotRecord]:
        """获取快照的子节点（用于回滚后的分支）"""

    # --- Memories ---

    def save_memory(self, session_id: str, category: str,
                    key: str, value: Any) -> None:
        """保存长期记忆（upsert）"""

    def get_memory(self, session_id: str, category: str,
                   key: str) -> Any | None:
        """获取长期记忆"""

    def list_memories(self, session_id: str,
                      category: str | None = None) -> list[MemoryEntry]:
        """列出记忆"""

    # --- File Records ---

    def save_file_record(self, record: FileRecord) -> None: ...
    def get_file_record(self, file_id: str) -> FileRecord | None: ...
    def list_file_records(self, session_id: str) -> list[FileRecord]: ...
    def update_preload_status(self, file_id: str, status: str) -> None: ...
```

### MemoryManager — 分层记忆

```python
class MemoryManager:
    """分层记忆管理"""

    def __init__(self, db: Database, llm: LLMProvider):
        self.db = db
        self.llm = llm

    # --- 短期记忆（内存中，构建 Prompt 时使用）---

    def get_conversation_context(self, session_id: str,
                                 max_messages: int = 10) -> list[dict]:
        """获取最近 N 条消息，格式化为 LLM 消息格式"""

    # --- 中期记忆（对话压缩摘要）---

    def get_or_create_summary(self, session_id: str) -> str:
        """
        获取对话摘要。
        如果消息数超过阈值，调用 LLM 生成摘要。
        """

    def compact_conversation(self, session_id: str,
                             keep_recent: int = 4) -> str:
        """
        压缩对话历史:
        1. 保留最近 keep_recent 条消息
        2. 将更早的消息发送给 LLM 生成摘要
        3. 将摘要保存为系统消息
        4. 删除已压缩的旧消息
        5. 返回摘要文本
        """

    # --- 长期记忆（用户偏好和模式）---

    def remember_preference(self, session_id: str,
                            key: str, value: Any) -> None:
        """记住用户偏好（如"喜欢使用中文列名"）"""

    def get_preferences(self, session_id: str) -> dict:
        """获取所有用户偏好"""

    def remember_pattern(self, session_id: str,
                         pattern: str, description: str) -> None:
        """记住操作模式（如"用户经常做数据透视"）"""

    # --- 工作记忆（当前工作簿状态）---

    def get_working_state(self, session_id: str) -> dict:
        """获取当前工作状态（哪些文件打开、哪些 sheet 修改过）"""
```

### SnapshotManager — 快照管理

```python
class SnapshotManager:
    """操作快照管理"""

    def __init__(self, db: Database, workspace: SessionWorkspace):
        self.db = db
        self.workspace = workspace

    def create_snapshot(self, session_id: str, file_id: str,
                        description: str,
                        tool_calls: list[dict] | None = None) -> SnapshotRecord:
        """
        创建快照:
        1. 计算 working 文件的 hash
        2. 计算 source 和当前 working 的 diff
        3. 保存 diff 和元信息到数据库
        4. 返回 SnapshotRecord
        """

    def list_snapshots(self, session_id: str,
                       file_id: str | None = None) -> list[SnapshotRecord]:
        """列出快照（时间线）"""

    def get_snapshot_diff(self, snapshot_id: str) -> dict:
        """获取快照的 diff 详情"""
```

### RollbackEngine — 回滚引擎

```python
class RollbackEngine:
    """回滚引擎"""

    def __init__(self, db: Database, workspace: SessionWorkspace):
        self.db = db
        self.workspace = workspace

    def rollback_to(self, session_id: str, file_id: str,
                    snapshot_id: str) -> RollbackResult:
        """
        回滚到指定快照:
        1. 从 source/ 复制原始文件到 working/
        2. 按顺序应用从 snap_001 到目标 snapshot 的所有 diff
        3. 验证最终文件的 hash
        4. 返回回滚结果

        注意: 不删除后续快照，只是创建一个新的分支点。
        用户可以前进到更新的快照。
        """

    def get_rollback_preview(self, snapshot_id: str) -> RollbackPreview:
        """
        预览回滚效果:
        - 将丢失哪些修改
        - 将恢复哪些修改
        - 影响的 sheet 和单元格范围
        """

@dataclass
class RollbackResult:
    success: bool
    snapshot_id: str
    restored_hash: str
    changes_lost: int          # 将丢失的修改数
    message: str

@dataclass
class RollbackPreview:
    snapshot: SnapshotRecord
    changes_to_lose: list[str]  # ["添加了柱状图", "修改了标题"]
    changes_to_restore: list[str]
```

## 实现要点

### 1. 对话压缩（借鉴 opencode-dev 的 compaction）

```python
async def compact_conversation(self, session_id: str, keep_recent: int = 4) -> str:
    """当消息数超过阈值时压缩"""
    messages = self.db.get_messages(session_id)
    if len(messages) <= keep_recent + 5:  # 还不急
        return ""

    # 分离: 要压缩的旧消息 vs 保留的新消息
    to_compress = messages[:-keep_recent]
    to_keep = messages[-keep_recent:]

    # 让 LLM 生成摘要
    summary_prompt = [
        {"role": "system", "content": "请总结以下对话的关键信息，包括: 用户需求、已完成的操作、当前文件状态。"},
        *[format_message(m) for m in to_compress]
    ]
    summary = await self.llm.chat_no_stream(summary_prompt)

    # 保存摘要为系统消息
    self.db.save_message(MessageRecord(
        id=str(uuid4()),
        session_id=session_id,
        role="system",
        content=f"[对话摘要] {summary}",
    ))

    # 删除旧消息
    for m in to_compress:
        self.db.delete_message(m.id)

    return summary
```

### 2. 快照 diff 计算

```python
def compute_diff(self, source_path: str, working_path: str) -> dict:
    """
    计算两个 xlsx 文件的 diff。
    不比较二进制，而是 unpack 后比较 XML。
    """
    source_dir = tempfile.mkdtemp()
    working_dir = tempfile.mkdtemp()
    self.xml_helpers.unpack(source_path, source_dir)
    self.xml_helpers.unpack(working_path, working_dir)

    diff = {
        "added_files": [],
        "deleted_files": [],
        "modified_files": {},
    }

    # 比较文件列表
    source_files = set(list_all_files(source_dir))
    working_files = set(list_all_files(working_dir))

    diff["added_files"] = list(working_files - source_files)
    diff["deleted_files"] = list(source_files - working_files)

    # 比较共同文件的差异
    for f in source_files & working_files:
        source_content = read_file(source_dir, f)
        working_content = read_file(working_dir, f)
        if source_content != working_content:
            diff["modified_files"][f] = compute_xml_diff(source_content, working_content)

    return diff
```

### 3. 回滚实现

```python
def rollback_to(self, session_id: str, file_id: str,
                snapshot_id: str) -> RollbackResult:
    """回滚: source + 应用 diff 链"""
    chain = self.db.get_snapshot_chain(session_id, file_id)

    # 找到目标快照在链中的位置
    target_idx = next(i for i, s in enumerate(chain) if s.id == snapshot_id)

    # 从 source 开始，逐步应用 diff
    source_path = self.workspace.source_dir / f"{file_id}.xlsx"
    working_path = self.workspace.working_dir / f"{file_id}.xlsx"

    # 复制 source 作为起点
    shutil.copy2(source_path, working_path)

    # 应用 diff 0 到 target_idx
    for i in range(target_idx + 1):
        apply_diff(working_path, chain[i].diff)

    # 验证 hash
    actual_hash = compute_hash(working_path)
    expected_hash = chain[target_idx].file_hash

    return RollbackResult(
        success=(actual_hash == expected_hash),
        snapshot_id=snapshot_id,
        restored_hash=actual_hash,
        changes_lost=len(chain) - target_idx - 1,
        message=f"已回滚到: {chain[target_idx].description}"
    )
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `python/session/__init__.py` | 模块入口 |
| `python/session/database.py` | Database 类（SQLite CRUD） |
| `python/session/memory.py` | MemoryManager（分层记忆） |
| `python/session/snapshot.py` | SnapshotManager（快照管理） |
| `python/session/rollback.py` | RollbackEngine（回滚引擎） |
| `python/session/migrations.py` | 数据库迁移脚本 |

## 依赖

- `sqlite3`（Python 标准库）
- 模块 4（Excel Engine）: XML helpers 用于 diff 计算
- 模块 6（Agent Core）: LLM 用于对话压缩

## 测试要求

- 创建会话 → 保存消息 → 关闭 → 重新打开 → 消息完整
- 对话压缩 → 验证摘要生成、旧消息删除
- 创建快照链（5 步操作）→ 回滚到第 3 步 → 文件状态正确
- 回滚后再操作 → 验证新快照正确追加
- 大量消息的分页查询性能
- 数据库迁移（schema 变更前后数据完整）
