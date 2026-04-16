"""JSON-RPC entry point for Python sidecar.

Reads JSON-RPC requests from stdin (one per line), dispatches to handlers,
writes responses to stdout. Progress events are sent as notifications (no id).

Usage: echo '{"jsonrpc":"2.0","id":1,"method":"file.import","params":{...}}' | python -m python.main
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from typing import Any

# Fix Windows Chinese encoding: ensure UTF-8 for all std streams
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Load .env before anything else (config._load_dotenv runs on import)
from . import config as _config  # noqa: F401

from .file_manager.manager import FileError, FileManager
from .preload.pipeline import PreloadConfig, PreloadPipeline
from .session.database import Database
from .session.models import new_id

# ---------------------------------------------------------------------------
# Global state — initialised on first request
# ---------------------------------------------------------------------------

_db: Database | None = None
_file_manager: FileManager | None = None

# Agent state
_engine: Any | None = None  # AgentEngine
_conversation_states: dict[str, Any] = {}  # session_id → ConversationState


def _ensure_db(db_path: str | None = None) -> Database:
    global _db
    if _db is None:
        path = db_path or os.path.join(
            os.path.expanduser("~"), ".exceler", "exceler.db"
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _db = Database(path)
    return _db


def _ensure_fm(db_path: str | None = None) -> FileManager:
    global _file_manager
    if _file_manager is None:
        db = _ensure_db(db_path)
        _file_manager = FileManager(db)
    return _file_manager


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

def _ok(result: Any, req_id: int | str | None) -> dict:
    resp = {"jsonrpc": "2.0", "result": result}
    if req_id is not None:
        resp["id"] = req_id
    return resp


def _err(code: int, message: str, req_id: int | str | None) -> dict:
    resp = {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
    }
    if req_id is not None:
        resp["id"] = req_id
    return resp


def _notify(method: str, params: dict) -> dict:
    """Progress notification — no id field."""
    return {"jsonrpc": "2.0", "method": method, "params": params}


def _write(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_file_import(params: dict, req_id: int | str | None) -> dict:
    fm = _ensure_fm(params.get("dbPath"))
    session_id = params["sessionId"]
    # Ensure session exists in DB (Rust creates filesystem dirs, not DB records)
    db = _ensure_db(params.get("dbPath"))
    db.conn.execute(
        "INSERT OR IGNORE INTO sessions (id, name, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        (session_id, session_id[:8]),
    )
    db.conn.commit()
    try:
        result = fm.import_file(
            session_id=session_id,
            file_id=params.get("fileId") or new_id(),
            file_name=params["fileName"],
            source_path=params["sourcePath"],
            working_path=params["workingPath"],
        )
        return _ok(result.to_dict(), req_id)
    except FileError as e:
        return _err(-32001, str(e), req_id)


def _handle_file_list(params: dict, req_id: int | str | None) -> dict:
    fm = _ensure_fm(params.get("dbPath"))
    files = fm.list_files(params["sessionId"])
    return _ok([f.to_dict() for f in files], req_id)


def _handle_file_remove(params: dict, req_id: int | str | None) -> dict:
    fm = _ensure_fm(params.get("dbPath"))
    try:
        fm.remove_file(params["fileId"], params["sessionId"])
        return _ok({"deleted": True}, req_id)
    except FileError as e:
        return _err(-32001, str(e), req_id)


def _handle_file_export(params: dict, req_id: int | str | None) -> dict:
    fm = _ensure_fm(params.get("dbPath"))
    try:
        fm.export_file(params["fileId"], params["destPath"])
        return _ok({"exported": True}, req_id)
    except FileError as e:
        return _err(-32001, str(e), req_id)


def _handle_file_info(params: dict, req_id: int | str | None) -> dict:
    fm = _ensure_fm(params.get("dbPath"))
    info = fm.get_file_info(params["fileId"])
    if info is None:
        return _err(-32001, "File not found", req_id)
    return _ok(info.to_dict(), req_id)


def _handle_preload_start(params: dict, req_id: int | str | None) -> dict:
    cfg = PreloadConfig(
        file_id=params["fileId"],
        source_path=params["sourcePath"],
        working_path=params["workingPath"],
        duckdb_path=params["duckdbPath"],
        schema_path=params["schemaPath"],
        stats_path=params["statsPath"],
    )
    pipeline = PreloadPipeline(cfg)

    def on_progress(stage: str, pct: int, msg: str, elapsed_ms: int) -> None:
        _write(_notify("preload.progress", {
            "fileId": params["fileId"],
            "stage": stage,
            "progress": pct,
            "message": msg,
            "elapsedMs": elapsed_ms,
        }))

    result = pipeline.run(on_progress=on_progress)

    # Update preload status in DB
    fm = _ensure_fm()
    if result.status == "ok":
        fm.update_preload_status(params["fileId"], "ready")
    else:
        fm.update_preload_status(params["fileId"], "error")

    return _ok({
        "fileId": result.file_id,
        "status": result.status,
        "durationMs": result.duration_ms,
        "errorMessage": result.error_message,
    }, req_id)


def _handle_preload_status(params: dict, req_id: int | str | None) -> dict:
    fm = _ensure_fm(params.get("dbPath"))
    info = fm.get_file_info(params["fileId"])
    if info is None:
        return _err(-32001, "File not found", req_id)
    return _ok({"fileId": info.file_id, "preloadStatus": info.preload_status}, req_id)


# ---------------------------------------------------------------------------
# Agent helpers
# ---------------------------------------------------------------------------


def _ensure_engine() -> Any:
    """Lazy-init the AgentEngine with all components."""
    global _engine
    if _engine is not None:
        return _engine

    from .agent.engine import AgentEngine
    from .agent.hook_manager import HookManager
    from .agent.llm_provider import LLMConfig, LLMProvider
    from .agent.prompt_builder import PromptBuilder
    from .agent.tool_registry import ToolRegistry
    from .tools import create_default_tools

    config = LLMConfig(
        model=os.environ.get("LLM_MODEL", "gpt-4o"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        base_url=os.environ.get("LLM_BASE_URL") or None,
    )
    if not config.api_key:
        raise RuntimeError("未配置 LLM API Key，请在设置中配置 API Key 后重试")
    llm = LLMProvider(config)

    tools = ToolRegistry()
    for tool in create_default_tools():
        tools.register(tool)

    prompt = PromptBuilder()
    hooks = HookManager()
    _engine = AgentEngine(llm, tools, prompt, hooks)
    return _engine


def _resolve_file_paths(file_ids: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve file_ids → (file_paths, db_paths) from the database."""
    fm = _ensure_fm()
    file_paths: dict[str, str] = {}
    db_paths: dict[str, str] = {}
    for fid in file_ids:
        info = fm.get_file_info(fid)
        if info is None:
            continue
        file_paths[fid] = info.working_path
        # Derive DuckDB path from working_path convention
        base_dir = os.path.dirname(os.path.dirname(info.working_path))
        duckdb_path = os.path.join(base_dir, "cache", f"{fid}.duckdb")
        if os.path.isfile(duckdb_path):
            db_paths[fid] = duckdb_path
    return file_paths, db_paths


def _serialize_agent_event(event: Any) -> dict:
    """Convert an AgentEvent to a JSON-serializable dict."""
    from .agent.models import (
        EvDone,
        EvError,
        EvTextDelta,
        EvTextEnd,
        EvTextStart,
        EvToolCallEnd,
        EvToolCallProgress,
        EvToolCallStart,
    )

    if isinstance(event, EvTextStart):
        return {"type": "text_start"}
    if isinstance(event, EvTextDelta):
        return {"type": "text_delta", "text": event.text}
    if isinstance(event, EvTextEnd):
        return {"type": "text_end", "full_text": event.full_text}
    if isinstance(event, EvToolCallStart):
        return {"type": "tool_call_start", "id": event.id, "name": event.name}
    if isinstance(event, EvToolCallProgress):
        return {"type": "tool_call_progress", "id": event.id, "message": event.message}
    if isinstance(event, EvToolCallEnd):
        d: dict[str, Any] = {"type": "tool_call_end", "id": event.id, "name": event.name}
        if event.error:
            d["error"] = event.error
        else:
            d["result"] = str(event.result) if event.result is not None else None
        return d
    if isinstance(event, EvError):
        return {"type": "error", "message": event.message}
    if isinstance(event, EvDone):
        return {"type": "done"}
    return {"type": "unknown"}


# ---------------------------------------------------------------------------
# Agent handlers
# ---------------------------------------------------------------------------


def _handle_chat(params: dict, req_id: int | str | None) -> dict:
    """Non-streaming chat: run agent, return final text."""
    from .agent.models import ConversationState

    engine = _ensure_engine()
    session_id = params["session_id"]
    file_id = params.get("file_id", "")
    message = params["message"]

    # Get or create conversation state
    if session_id not in _conversation_states:
        workspace_dir = os.path.join(
            os.path.expanduser("~"), ".exceler", "workspace", session_id
        )
        _conversation_states[session_id] = ConversationState(
            session_id=session_id,
            file_ids=[file_id] if file_id else [],
            workspace_dir=workspace_dir,
        )
    state = _conversation_states[session_id]
    state.file_ids = [file_id] if file_id else []

    # Resolve file paths
    file_paths, db_paths = _resolve_file_paths(state.file_ids)
    state.file_paths = file_paths
    state.db_paths = db_paths

    # Run agent (blocking)
    result_state = asyncio.run(engine.chat(state, message))
    _conversation_states[session_id] = result_state

    # Extract last assistant message
    last_text = ""
    last_id = new_id()
    for msg in reversed(result_state.messages):
        if msg.role == "assistant" and msg.content:
            last_text = msg.content
            last_id = msg.id
            break

    return _ok({"message_id": last_id, "text": last_text}, req_id)


def _handle_chat_stream(params: dict, req_id: int | str | None) -> dict | None:
    """Streaming chat: emit events as notifications, then final response."""
    from .agent.models import ConversationState

    engine = _ensure_engine()
    session_id = params["session_id"]
    file_id = params.get("file_id", "")
    message = params["message"]

    # Get or create conversation state
    if session_id not in _conversation_states:
        workspace_dir = os.path.join(
            os.path.expanduser("~"), ".exceler", "workspace", session_id
        )
        _conversation_states[session_id] = ConversationState(
            session_id=session_id,
            file_ids=[file_id] if file_id else [],
            workspace_dir=workspace_dir,
        )
    state = _conversation_states[session_id]
    state.file_ids = [file_id] if file_id else []

    # Resolve file paths
    file_paths, db_paths = _resolve_file_paths(state.file_ids)
    state.file_paths = file_paths
    state.db_paths = db_paths

    # Streaming callback — write notification events to stdout
    def on_event(event: Any) -> None:
        serialized = _serialize_agent_event(event)
        eprintln_msg = json.dumps(serialized, ensure_ascii=False)
        print(f"[chat event] {eprintln_msg}", file=sys.stderr, flush=True)
        _write(_notify("chat.event", serialized))

    # Run agent with streaming
    result_state = asyncio.run(engine.chat(state, message, on_event=on_event))
    _conversation_states[session_id] = result_state

    # Extract last assistant message for the final response
    last_text = ""
    last_id = new_id()
    for msg in reversed(result_state.messages):
        if msg.role == "assistant" and msg.content:
            last_text = msg.content
            last_id = msg.id
            break

    # Final response (has id + result → Rust call_stream terminates)
    return _ok({"message_id": last_id, "text": last_text}, req_id)


def _handle_stop(params: dict, req_id: int | str | None) -> dict:
    """Cancel the running agent loop."""
    if _engine is not None:
        _engine.cancel()
    return _ok({"cancelled": True}, req_id)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    "file.import": _handle_file_import,
    "file.list": _handle_file_list,
    "file.remove": _handle_file_remove,
    "file.export": _handle_file_export,
    "file.info": _handle_file_info,
    "preload.start": _handle_preload_start,
    "preload.status": _handle_preload_status,
    "chat": _handle_chat,
    "chat_stream": _handle_chat_stream,
    "stop": _handle_stop,
}


def _dispatch(request: dict) -> dict | None:
    """Dispatch a single JSON-RPC request. Returns response dict or None."""
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")

    if method not in _HANDLERS:
        return _err(-32601, f"Method not found: {method}", req_id)

    handler = _HANDLERS[method]
    try:
        return handler(params, req_id)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return _err(-32603, f"Internal error: {e}", req_id)


def main() -> None:
    """Main loop: read JSON-RPC from stdin, write responses to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            _write(_err(-32700, f"Parse error: {e}", None))
            continue

        response = _dispatch(request)
        if response is not None:
            _write(response)


if __name__ == "__main__":
    main()
