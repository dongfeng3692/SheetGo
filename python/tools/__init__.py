"""工具注册 — 创建并注册所有工具"""

from __future__ import annotations

from .base import BaseTool
from .list_files import ListFilesTool
from .read_sheet import ReadSheetTool
from .sheet_info import SheetInfoTool
from .validate import ValidateTool
from .write_cells import (
    AddColumnTool,
    AddFormulaTool,
    ApplyStyleTool,
    CreateChartTool,
    ExportFileTool,
    InsertRowTool,
    QueryDataTool,
    ReadFormulasTool,
    WriteCellsTool,
)
from .write_query import WriteQueryTool

# 所有工具类
ALL_TOOLS: list[type[BaseTool]] = [
    # 读取类
    ListFilesTool,
    QueryDataTool,
    ReadSheetTool,
    SheetInfoTool,
    ReadFormulasTool,
    ValidateTool,
    # 写入类
    WriteCellsTool,
    WriteQueryTool,
    AddFormulaTool,
    AddColumnTool,
    InsertRowTool,
    CreateChartTool,
    ApplyStyleTool,
    ExportFileTool,
]


def create_default_tools() -> list[BaseTool]:
    """创建所有工具实例"""
    return [cls() for cls in ALL_TOOLS]
