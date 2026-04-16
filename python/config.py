"""Exceler 统一配置 — 所有模块的配置项集中管理

使用方式:
    from config import paths, llm, agent, validation, preload, db, memory, benchmark

优先级: .env 文件 > 环境变量 > 代码默认值
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ============================================================================
# .env 加载 — 零依赖，不覆盖已存在的环境变量
# ============================================================================

def _load_dotenv() -> None:
    """加载 .env 文件到 os.environ（不覆盖已有值）"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # 去掉引号
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            # 不覆盖已有环境变量
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


# ============================================================================
# 通用读取辅助
# ============================================================================

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key, "").lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default


# ============================================================================
# 路径
# ============================================================================


@dataclass(frozen=True)
class PathsConfig:
    home: str = os.environ.get(
        "EXCELER_HOME",
        os.path.join(os.path.expanduser("~"), ".exceler"),
    )
    database: str = ""
    benchmark_data: str = ""

    def __post_init__(self):
        if not self.database:
            object.__setattr__(self, "database", os.path.join(self.home, "exceler.db"))
        if not self.benchmark_data:
            object.__setattr__(
                self, "benchmark_data",
                os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "spreadsheetbench")),
            )


# ============================================================================
# LLM
# ============================================================================


@dataclass
class LLMConfig:
    provider: str = _env("LLM_PROVIDER", "openai")
    model: str = _env("LLM_MODEL", "gpt-4o")
    api_key: str = _env("LLM_API_KEY", "")
    base_url: str | None = os.environ.get("LLM_BASE_URL") or None
    temperature: float = _env_float("LLM_TEMPERATURE", 0.0)
    max_tokens: int = _env_int("LLM_MAX_TOKENS", 4096)


# ============================================================================
# Agent
# ============================================================================


@dataclass(frozen=True)
class AgentConfig:
    doom_loop_threshold: int = _env_int("DOOM_LOOP_THRESHOLD", 3)
    default_max_steps: int = 50
    main_max_steps: int = _env_int("AGENT_MAIN_MAX_STEPS", 50)
    explore_max_steps: int = _env_int("AGENT_EXPLORE_MAX_STEPS", 30)
    formula_max_steps: int = _env_int("AGENT_FORMULA_MAX_STEPS", 30)
    chart_max_steps: int = _env_int("AGENT_CHART_MAX_STEPS", 20)


# ============================================================================
# Validation
# ============================================================================


@dataclass(frozen=True)
class ValidationConfig:
    null_rate_threshold: float = _env_float("NULL_RATE_THRESHOLD", 0.3)
    iqr_multiplier: float = _env_float("IQR_MULTIPLIER", 1.5)
    formula_consistency_ratio: float = 0.3


# ============================================================================
# Preload
# ============================================================================


@dataclass(frozen=True)
class PreloadConfig:
    sample_rows: int = _env_int("PRELOAD_SAMPLE_ROWS", 20)
    max_stats_rows: int = _env_int("PRELOAD_MAX_STATS_ROWS", 100_000)
    max_style_scan_rows: int = _env_int("PRELOAD_MAX_STYLE_SCAN_ROWS", 100)
    run_validation: bool = _env_bool("PRELOAD_RUN_VALIDATION", False)


# ============================================================================
# Database
# ============================================================================


@dataclass(frozen=True)
class DatabaseConfig:
    session_list_limit: int = _env_int("DB_SESSION_LIST_LIMIT", 50)
    message_list_limit: int = _env_int("DB_MESSAGE_LIST_LIMIT", 50)
    recent_messages_count: int = _env_int("DB_RECENT_MESSAGES_COUNT", 10)
    keep_recent_messages: int = _env_int("DB_KEEP_RECENT_MESSAGES", 100)


# ============================================================================
# Memory
# ============================================================================


@dataclass(frozen=True)
class MemoryConfig:
    context_max_messages: int = _env_int("MEMORY_CONTEXT_MAX_MESSAGES", 10)
    compact_keep_recent: int = _env_int("MEMORY_COMPACT_KEEP_RECENT", 4)


# ============================================================================
# FileManager
# ============================================================================


@dataclass(frozen=True)
class FileManagerConfig:
    max_file_size: int = _env_int("FILE_MAX_SIZE_MB", 100) * 1024 * 1024


# ============================================================================
# Benchmark
# ============================================================================


@dataclass(frozen=True)
class BenchmarkConfig:
    exec_timeout: int = _env_int("BENCHMARK_EXEC_TIMEOUT", 120)
    preview_rows: int = _env_int("BENCHMARK_PREVIEW_ROWS", 5)
    num_test_cases: int = 3

    datasets: dict = field(default_factory=lambda: {
        "spreadsheetbench_912": {
            "url": "https://raw.githubusercontent.com/RUCKBReasoning/SpreadsheetBench/main/data/spreadsheetbench_912_v0.1.tar.gz",
            "filename": "spreadsheetbench_912_v0.1.tar.gz",
        },
        "verified_400": {
            "url": "https://raw.githubusercontent.com/RUCKBReasoning/SpreadsheetBench/main/data/spreadsheetbench_verified_400.tar.gz",
            "filename": "spreadsheetbench_verified_400.tar.gz",
        },
    })


# ============================================================================
# 全局单例
# ============================================================================

paths = PathsConfig()
llm = LLMConfig()
agent = AgentConfig()
validation = ValidationConfig()
preload = PreloadConfig()
db = DatabaseConfig()
memory = MemoryConfig()
file_manager = FileManagerConfig()
benchmark = BenchmarkConfig()
