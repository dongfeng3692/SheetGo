# 模块 6: Agent Core — Agent 对话引擎

## 概述

Agent 系统的核心：LLM 通信、Prompt 构建、工具注册与调度、对话循环。采用 function calling 模式——LLM 不写代码，只做决策和调用预置工具函数。

设计参考 opencode-dev 的多 Agent 类型和对话循环，pandas-ai 的工具注入，claw-code 的 Hook 系统。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| LLM 提供商抽象（LiteLLM） | 具体工具实现（模块 4） |
| Prompt 构建器 | 验证逻辑（模块 5） |
| 工具注册中心 | 会话持久化（模块 7） |
| 对话循环编排 | UI 渲染（模块 8） |
| Function calling 解析和分发 | |
| 流式响应处理 | |
| 错误恢复/重试 | |
| 工具执行前后 Hook | |
| Agent 类型管理 | |

## 数据结构

```python
@dataclass
class Message:
    id: str
    role: str             # "user" | "assistant" | "tool_result" | "system"
    content: str
    tool_calls: list[ToolCall] | None
    tool_results: list[ToolResult] | None
    timestamp: str
    tokens: TokenUsage | None

@dataclass
class ToolCall:
    id: str               # 调用 ID（LLM 生成）
    name: str             # 工具名
    arguments: dict       # 参数

@dataclass
class ToolResult:
    call_id: str          # 对应 ToolCall.id
    name: str
    result: Any           # 工具返回值
    error: str | None     # 错误信息

@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_cost: float     # 美元

@dataclass
class ConversationState:
    session_id: str
    file_ids: list[str]
    messages: list[Message]
    agent_type: str       # "main" | "explore" | "formula" | "chart"
    total_tokens: int
```

## 接口定义

### LLMProvider — LLM 提供商

```python
class LLMProvider:
    """LLM 统一接口（基于 LiteLLM）"""

    def __init__(self, config: LLMConfig):
        """
        config 包含: provider, model, api_key, base_url, temperature, max_tokens
        """

    async def chat(self, messages: list[dict], tools: list[dict],
                   stream: bool = True) -> AsyncIterator[ChatEvent]:
        """
        发送对话请求，流式返回事件。

        ChatEvent 类型:
        - TextDelta(text: str)          — 文本增量
        - ToolCallStart(id, name)       — 工具调用开始
        - ToolCallDelta(id, args_delta) — 参数增量
        - ToolCallEnd(id, args)         — 工具调用结束
        - Usage(input_tokens, output_tokens) — token 使用量
        - Finish(reason)                — 结束（reason: "stop" | "tool_use"）
        """

    async def chat_no_stream(self, messages: list[dict],
                             tools: list[dict] | None = None) -> ChatResponse:
        """非流式调用（用于标题生成等辅助任务）"""
```

### PromptBuilder — Prompt 构建

```python
class PromptBuilder:
    """Prompt 构建器"""

    def build_system_prompt(self, context: PromptContext) -> str:
        """
        构建系统提示，结构:
        1. 身份与能力描述
        2. 当前文件信息（schema 摘要）
        3. 可用工具列表
        4. 安全约束
        5. 领域 Skill（按需注入）
        6. 对话历史摘要（压缩后）
        """

    def build_tool_definitions(self, available_tools: list[str]) -> list[dict]:
        """
        构建 function calling 的工具定义（OpenAI 格式）。
        根据 agent_type 和 file_context 过滤可用工具。
        """

    def format_data_context(self, schema: dict, sample: dict) -> str:
        """格式化数据上下文（XML 标签格式，借鉴 pandas-ai）"""

@dataclass
class PromptContext:
    agent_type: str
    file_ids: list[str]
    schemas: dict[str, dict]     # file_id → schema
    samples: dict[str, dict]     # file_id → sample
    available_tools: list[str]
    user_config: dict
    memory_summary: str | None   # 压缩后的对话摘要
```

### ToolRegistry — 工具注册中心

```python
class ToolRegistry:
    """工具注册中心"""

    def register(self, name: str, tool: BaseTool, agent_types: list[str] | None = None):
        """注册工具。agent_types=None 表示所有 agent 可用。"""

    def get_tool(self, name: str) -> BaseTool:
        """获取工具实例"""

    def get_definitions(self, agent_type: str = "main") -> list[dict]:
        """获取指定 agent 类型可用的工具定义（function calling 格式）"""

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        """执行工具"""

    def list_tools(self) -> list[str]:
        """列出所有已注册工具"""
```

### BaseTool — 工具基类

```python
class BaseTool(ABC):
    """所有工具的基类"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def definition(self) -> dict:
        """function calling 格式的工具定义"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            }
        }

    @property
    @abstractmethod
    def parameters_schema(self) -> dict: ...

    @abstractmethod
    async def execute(self, **kwargs) -> Any: ...

    @property
    def safe_level(self) -> str:
        """安全级别: 'read' | 'write' | 'dangerous'"""
        return "read"

    @property
    def requires_confirmation(self) -> bool:
        """是否需要用户确认（write/dangerous 级别默认需要）"""
        return self.safe_level != "read"
```

### AgentEngine — 对话引擎

```python
class AgentEngine:
    """Agent 对话引擎（主循环）"""

    def __init__(self, llm: LLMProvider, tools: ToolRegistry,
                 prompt: PromptBuilder, memory: MemoryManager):
        self.llm = llm
        self.tools = tools
        self.prompt = prompt
        self.memory = memory

    async def chat(self, state: ConversationState,
                   user_message: str,
                   on_event: Callable[[AgentEvent], None]) -> ConversationState:
        """
        执行一次完整对话循环。

        事件类型（通过 on_event 回调）:
        - TextStart()                — 开始生成文本
        - TextDelta(text)            — 文本增量（流式推送到 UI）
        - TextEnd(full_text)         — 文本生成完毕
        - ToolCallStart(id, name)    — 工具调用开始
        - ToolCallProgress(id, msg)  — 工具执行进度
        - ToolCallEnd(id, result)    — 工具执行完毕
        - ToolResultPreview(diff)    — 修改预览（等待用户确认）
        - Error(message)             — 错误
        - Done(state)                — 对话结束

        循环逻辑:
        1. 构建消息列表（system + 历史 + 新消息）
        2. 构建 tools 定义
        3. 调用 LLM（流式）
        4. 如果有 tool_calls:
           a. 遍历每个 tool_call
           b. 执行 pre_hooks
           c. 执行工具
           d. 执行 post_hooks
           e. 如果需要确认 → 等待用户确认
           f. 将 tool_result 追加到消息
           g. 回到步骤 3
        5. 如果无 tool_calls → 结束，返回最终状态
        """

    async def stop(self):
        """中断当前对话"""
```

### Hook 系统

```python
class HookManager:
    """工具执行钩子"""

    def register_before(self, tool_name: str | None,
                        hook: Callable[[ToolCall], ToolCall | None]):
        """
        工具执行前钩子。
        返回修改后的 ToolCall，或 None 取消执行。
        tool_name=None 表示所有工具。
        """

    def register_after(self, tool_name: str | None,
                       hook: Callable[[ToolCall, ToolResult], None]):
        """工具执行后钩子"""

    def register_on_error(self, tool_name: str | None,
                          hook: Callable[[ToolCall, Exception], None]):
        """工具执行失败钩子"""

# 内置 Hook 示例
class ValidationHook:
    """写入前自动验证"""
    def before(self, call: ToolCall) -> ToolCall | None:
        if call.name in ('write_cells', 'add_formula', ...):
            # 校验参数合法性
            validate_write_params(call.arguments)
        return call

class SnapshotHook:
    """写入前自动创建快照"""
    def before(self, call: ToolCall) -> ToolCall | None:
        if call.name in WRITE_TOOLS:
            snapshot_manager.create_snapshot(...)
        return call

class NotificationHook:
    """写入后通知 UI 刷新"""
    def after(self, call: ToolCall, result: ToolResult):
        if result.success:
            emit_event('file_changed', {file_id, changed_cells})
```

## 完整工具列表

| 工具名 | 安全级别 | 说明 | Agent 类型 |
|--------|---------|------|-----------|
| `query_data` | read | DuckDB SQL 查询 | main, explore |
| `read_sheet` | read | 读取工作表数据 | main, explore, formula |
| `sheet_info` | read | 获取工作簿元信息 | all |
| `read_formulas` | read | 读取公式列表 | main, formula |
| `validate_file` | read | 运行验证检查 | main |
| `write_cells` | write | 写入单元格 | main |
| `add_formula` | write | 添加公式 | main, formula |
| `add_column` | write | 添加列 | main |
| `insert_row` | write | 插入行 | main |
| `apply_style` | write | 应用样式 | main |
| `create_chart` | write | 创建图表 | main, chart |
| `create_sheet` | write | 创建工作表 | main |
| `merge_cells` | write | 合并单元格 | main |
| `export_file` | read | 导出文件 | main |

### 工具定义示例（query_data）

```python
class QueryDataTool(BaseTool):
    name = "query_data"
    description = "用 SQL 查询已加载的 Excel 数据。数据已预加载到 DuckDB，每个工作表是一个表。"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL 查询语句（仅支持 SELECT）"
                },
                "max_rows": {
                    "type": "integer",
                    "description": "返回最大行数（默认 100）",
                    "default": 100
                }
            },
            "required": ["sql"]
        }

    async def execute(self, sql: str, max_rows: int = 100) -> dict:
        result = self.duckdb_query.execute(self.db_path, sql)
        return {
            "columns": result.columns.tolist(),
            "data": result.head(max_rows).values.tolist(),
            "total_rows": len(result),
            "truncated": len(result) > max_rows,
        }
```

### 工具定义示例（write_cells）

```python
class WriteCellsTool(BaseTool):
    name = "write_cells"
    description = "写入数据到指定单元格范围。保留原有格式和公式。"
    safe_level = "write"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sheet": {"type": "string", "description": "工作表名"},
                "range": {"type": "string", "description": "Excel 范围，如 'A1:D10'"},
                "values": {
                    "type": "array",
                    "items": {"type": "array"},
                    "description": "二维数组，每行对应一行数据"
                },
                "preserve_format": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否保留原有格式"
                }
            },
            "required": ["sheet", "range", "values"]
        }

    async def execute(self, sheet: str, range: str,
                      values: list, preserve_format: bool = True) -> dict:
        edits = values_to_edits(sheet, range, values)
        result = self.writer.write_cells(self.file_path, edits, preserve_format)
        return {
            "success": result.success,
            "affected_cells": result.affected_cells,
            "affected_formulas": result.affected_formulas,
            "warnings": result.warnings,
        }
```

## Agent 类型

```python
AGENT_TYPES = {
    "main": {
        "description": "全功能 Agent，处理所有 Excel 任务",
        "tools": ["*"],  # 所有工具
        "model_preference": None,  # 使用默认模型
        "system_prompt_extra": "你是一个专业的 Excel 数据分析助手...",
    },
    "explore": {
        "description": "只读探索 Agent，用于数据分析和统计",
        "tools": ["query_data", "read_sheet", "sheet_info", "read_formulas", "validate_file"],
        "model_preference": "fast",  # 可用更快模型
        "system_prompt_extra": "你是一个数据探索专家...",
    },
    "formula": {
        "description": "公式专用 Agent",
        "tools": ["read_formulas", "read_sheet", "sheet_info", "add_formula", "validate_file"],
        "system_prompt_extra": "你是 Excel 公式专家...",
    },
    "chart": {
        "description": "图表专用 Agent",
        "tools": ["query_data", "read_sheet", "sheet_info", "create_chart"],
        "system_prompt_extra": "你是数据可视化专家...",
    },
}
```

## 对话循环流程

```
用户输入 "按地区汇总销售额"
    │
    ▼
① PromptBuilder.build_system_prompt()
   → 注入 schema（Sheet1: 日期/销售额/地区/...）
   → 注入可用工具列表
   → 注入对话历史（最近 10 轮）
    │
    ▼
② LLMProvider.chat(messages, tools, stream=True)
   → 流式接收响应
    │
    ▼
③ LLM 返回 tool_call: query_data(sql="SELECT 地区, SUM(销售额) as 销售额 FROM sheet1 GROUP BY 地区")
    │
    ▼
④ HookManager.before(query_data)
   → ValidationHook: 校验 SQL 安全性
   → SnapshotHook: 无需快照（只读操作）
    │
    ▼
⑤ QueryDataTool.execute(sql=...)
   → DuckDB 执行（已预加载，毫秒级）
   → 返回 {columns: ["地区", "销售额"], data: [["华东", 150000], ...]}
    │
    ▼
⑥ HookManager.after(query_data, result)
   → NotificationHook: 无需通知（只读）
    │
    ▼
⑦ 将 tool_result 追加到消息列表
    │
    ▼
⑧ 再次调用 LLM（带 tool_result）
    │
    ▼
⑨ LLM 返回文本回复 + tool_call: write_cells(sheet="Sheet2", range="A1:C6", values=[...])
    │
    ▼
⑩ HookManager.before(write_cells)
   → ValidationHook: 校验写入参数
   → SnapshotHook: 创建快照 snap_003
    │
    ▼
⑪ WriteCellsTool.execute(...)
   → XML 级精确写入
   → 返回 {success: true, affected_cells: ["Sheet2!A1:C6"]}
    │
    ▼
⑫ HookManager.after(write_cells, result)
   → NotificationHook: 通知 UI 刷新预览
    │
    ▼
⑬ 将 tool_result 追加到消息列表
    │
    ▼
⑭ LLM 生成最终文本回复 "已为您创建汇总表..."
    │
    ▼
⑮ AgentEvent.Done → UI 显示最终回复
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `python/agent/__init__.py` | 模块入口 |
| `python/agent/engine.py` | AgentEngine 对话循环 |
| `python/agent/llm_provider.py` | LLMProvider（LiteLLM 封装） |
| `python/agent/prompt_builder.py` | PromptBuilder |
| `python/agent/tool_registry.py` | ToolRegistry + BaseTool |
| `python/agent/hook_manager.py` | HookManager + 内置 Hooks |
| `python/agent/agent_types.py` | Agent 类型定义 |
| `python/tools/__init__.py` | 工具注册 |
| `python/tools/base.py` | BaseTool 基类 |
| `python/tools/query_data.py` | query_data 工具 |
| `python/tools/read_sheet.py` | read_sheet 工具 |
| `python/tools/write_cells.py` | write_cells 工具 |
| `python/tools/add_formula.py` | add_formula 工具 |
| `python/tools/add_column.py` | add_column 工具 |
| `python/tools/insert_row.py` | insert_row 工具 |
| `python/tools/create_chart.py` | create_chart 工具 |
| `python/tools/apply_style.py` | apply_style 工具 |
| `python/tools/sheet_info.py` | sheet_info 工具 |
| `python/tools/export_file.py` | export_file 工具 |
| `python/tools/validate.py` | validate 工具 |

## 依赖

- 模块 4（Excel Engine）: 工具实现调用 reader/writer/query
- 模块 5（Validation）: 工具执行前校验
- 模块 7（Session Store）: 消息持久化、快照
- `litellm` — LLM 统一接口

## 测试要求

- Mock LLM → 单轮对话（无工具调用）→ 验证消息格式
- Mock LLM → 单工具调用 → 验证工具执行和结果回传
- Mock LLM → 多轮工具调用 → 验证循环正确
- 写入工具 → 验证 Hook 执行（快照创建、验证触发）
- LLM 返回无效工具名 → 验证错误处理
- 工具执行失败 → 验证重试机制
- 流式响应 → 验证事件顺序正确
