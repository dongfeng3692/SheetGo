"""validate — 运行验证检查"""

from __future__ import annotations

from typing import Any

from .base import BaseTool


class ValidateTool(BaseTool):

    @property
    def name(self) -> str:
        return "validate_file"

    @property
    def description(self) -> str:
        return (
            "验证 Excel 文件的完整性和质量。检查公式错误、引用问题、"
            "函数兼容性、数据质量和 OpenXML 结构。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Excel 文件路径",
                },
                "mode": {
                    "type": "string",
                    "enum": ["full", "quick", "final"],
                    "description": "验证模式: full=全量, quick=增量, final=导出前",
                    "default": "full",
                },
                "changed_sheets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "增量验证时指定变更的 sheet（mode=quick 时使用）",
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self,
        file_path: str,
        mode: str = "full",
        changed_sheets: list[str] | None = None,
        **kwargs,
    ) -> dict:
        # 延迟导入避免循环依赖
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from validation import ValidationEngine

        engine = ValidationEngine()

        if mode == "full":
            result = engine.full_check(file_path, file_id="validate")
        elif mode == "quick" and changed_sheets:
            result = engine.quick_check(file_path, file_id="validate", changed_sheets=changed_sheets)
        else:
            result = engine.final_check(file_path, file_id="validate")

        return {
            "passed": result.passed,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "summary": result.summary,
            "errors": [
                {
                    "severity": e.severity,
                    "category": e.category,
                    "sheet": e.sheet,
                    "cell": e.cell,
                    "code": e.code,
                    "message": e.message,
                }
                for e in result.errors
            ],
        }
