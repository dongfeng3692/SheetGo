"""Validation Engine — 验证引擎核心数据结构"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


class ErrorCode:
    """错误码常量"""

    # 公式错误
    FORMULA_REF_ERROR = "FORMULA_REF_ERROR"              # #REF!
    FORMULA_DIV_ZERO = "FORMULA_DIV_ZERO"                # #DIV/0!
    FORMULA_VALUE_ERROR = "FORMULA_VALUE_ERROR"          # #VALUE!
    FORMULA_NAME_ERROR = "FORMULA_NAME_ERROR"            # #NAME?
    FORMULA_NULL_ERROR = "FORMULA_NULL_ERROR"            # #NULL!
    FORMULA_NUM_ERROR = "FORMULA_NUM_ERROR"              # #NUM!
    FORMULA_NA_ERROR = "FORMULA_NA_ERROR"                # #N/A
    FORMULA_ZERO_VALUE = "FORMULA_ZERO_VALUE"            # 公式结果为 0
    FORMULA_IMPLICIT_ARRAY = "FORMULA_IMPLICIT_ARRAY"    # 隐式数组公式

    # 引用错误
    REF_OUT_OF_RANGE = "REF_OUT_OF_RANGE"                # 引用范围远超实际数据行
    REF_HEADER_INCLUDED = "REF_HEADER_INCLUDED"          # 公式包含表头行
    REF_INSUFFICIENT_RANGE = "REF_INSUFFICIENT_RANGE"    # SUM/AVERAGE 范围太小
    REF_INCONSISTENT_PATTERN = "REF_INCONSISTENT_PATTERN"  # 同列公式模式不一致

    # 兼容性
    COMPAT_FORBIDDEN_FUNCTION = "COMPAT_FORBIDDEN_FUNCTION"  # FILTER/XLOOKUP 等

    # 数据质量
    QUALITY_HIGH_NULL_RATE = "QUALITY_HIGH_NULL_RATE"         # 空值率 > 30%
    QUALITY_DUPLICATE_ROWS = "QUALITY_DUPLICATE_ROWS"         # 重复行
    QUALITY_MIXED_TYPES = "QUALITY_MIXED_TYPES"               # 同列混合类型
    QUALITY_OUTLIERS = "QUALITY_OUTLIERS"                      # 异常值

    # 结构
    STRUCTURE_INVALID_ZIP = "STRUCTURE_INVALID_ZIP"           # 不是有效 ZIP
    STRUCTURE_MISSING_FILE = "STRUCTURE_MISSING_FILE"         # 缺少必需文件
    STRUCTURE_BROKEN_RELS = "STRUCTURE_BROKEN_RELS"           # .rels 引用不存在的文件
    STRUCTURE_MISSING_CONTENT_TYPE = "STRUCTURE_MISSING_CONTENT_TYPE"  # 文件未在 Content_Types 声明


# Excel 错误值 → 错误码映射
_ERROR_VALUE_MAP: dict[str, str] = {
    "#REF!": ErrorCode.FORMULA_REF_ERROR,
    "#DIV/0!": ErrorCode.FORMULA_DIV_ZERO,
    "#VALUE!": ErrorCode.FORMULA_VALUE_ERROR,
    "#NAME?": ErrorCode.FORMULA_NAME_ERROR,
    "#NULL!": ErrorCode.FORMULA_NULL_ERROR,
    "#NUM!": ErrorCode.FORMULA_NUM_ERROR,
    "#N/A": ErrorCode.FORMULA_NA_ERROR,
}


def map_error_code(error_value: str) -> str:
    """将 Excel 错误值（如 '#REF!'）映射到错误码"""
    return _ERROR_VALUE_MAP.get(error_value, "FORMULA_UNKNOWN")


def safe_formula_str(value: object) -> str:
    """Extract formula string from cell value, handling openpyxl ArrayFormula objects."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # openpyxl ArrayFormula has .text attribute
    if hasattr(value, "text"):
        return value.text or ""
    return str(value)


@dataclass
class ValidationError:
    severity: str          # "error" | "warning" | "info"
    category: str          # "formula" | "reference" | "compat" | "quality" | "structure"
    sheet: str
    cell: str              # "B5" 或 ""（工作表级别）
    code: str              # 错误码
    message: str           # 人可读的描述
    detail: dict = field(default_factory=dict)  # 额外信息


@dataclass
class ValidationResult:
    file_id: str
    timestamp: str
    errors: list[ValidationError]
    summary: dict = field(default_factory=dict)
    passed: bool = True

    def __post_init__(self):
        if not self.errors:
            self.passed = True
        else:
            self.passed = all(e.severity != "error" for e in self.errors)

    @property
    def error_count(self) -> int:
        return len([e for e in self.errors if e.severity == "error"])

    @property
    def warning_count(self) -> int:
        return len([e for e in self.errors if e.severity == "warning"])

    @staticmethod
    def make_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()
