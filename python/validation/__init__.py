"""Validation Engine — Excel 文件多层次验证引擎"""

from __future__ import annotations

from . import compat_check as _compat_check
from . import data_quality as _data_quality
from . import formula_check as _formula_check
from . import openxml_validate as _openxml_validate
from . import reference_check as _reference_check
from .result import ValidationError, ValidationResult


class ValidationEngine:
    """Excel 验证引擎

    提供三种验证时机:
    - full_check: 上传后全量验证
    - quick_check: 修改后增量验证（只检查变更 sheet）
    - final_check: 导出前强制验证（结构 + 公式）
    """

    def full_check(self, file_path: str, file_id: str) -> ValidationResult:
        """全量验证（上传时运行）"""
        errors: list[ValidationError] = []
        errors.extend(_formula_check.check_formulas(file_path))
        errors.extend(_reference_check.check_references(file_path))
        errors.extend(_compat_check.check_compatibility(file_path))
        errors.extend(_data_quality.check_data_quality(file_path))
        errors.extend(_openxml_validate.check_structure(file_path))
        return self._build_result(file_id, errors)

    def quick_check(
        self,
        file_path: str,
        file_id: str,
        changed_sheets: list[str],
    ) -> ValidationResult:
        """增量验证（修改后运行，只检查变更 sheet）"""
        errors: list[ValidationError] = []
        errors.extend(_formula_check.check_formulas(file_path, sheets=changed_sheets))
        errors.extend(_reference_check.check_references(file_path, sheets=changed_sheets))
        errors.extend(_compat_check.check_compatibility(file_path, sheets=changed_sheets))
        errors.extend(_data_quality.check_data_quality(file_path, sheets=changed_sheets))
        return self._build_result(file_id, errors)

    def final_check(self, file_path: str, file_id: str) -> ValidationResult:
        """导出前强制验证（结构 + 公式）"""
        errors: list[ValidationError] = []
        errors.extend(_openxml_validate.check_structure(file_path))
        errors.extend(_formula_check.check_formulas(file_path))
        errors.extend(_reference_check.check_references(file_path))
        return self._build_result(file_id, errors)

    # --- 各子检查器 ---

    def check_formulas(
        self, file_path: str, sheets: list[str] | None = None
    ) -> list[ValidationError]:
        """公式错误检测"""
        return _formula_check.check_formulas(file_path, sheets=sheets)

    def check_references(
        self, file_path: str, sheets: list[str] | None = None
    ) -> list[ValidationError]:
        """引用范围校验"""
        return _reference_check.check_references(file_path, sheets=sheets)

    def check_compatibility(
        self, file_path: str, sheets: list[str] | None = None
    ) -> list[ValidationError]:
        """函数兼容性检查"""
        return _compat_check.check_compatibility(file_path, sheets=sheets)

    def check_data_quality(
        self, file_path: str, sheets: list[str] | None = None
    ) -> list[ValidationError]:
        """数据质量评估"""
        return _data_quality.check_data_quality(file_path, sheets=sheets)

    def check_structure(self, file_path: str) -> list[ValidationError]:
        """OpenXML 结构验证"""
        return _openxml_validate.check_structure(file_path)

    # --- 内部方法 ---

    @staticmethod
    def _build_result(
        file_id: str,
        errors: list[ValidationError],
    ) -> ValidationResult:
        summary = {
            "formula_errors": len([e for e in errors if e.category == "formula" and e.severity == "error"]),
            "formula_warnings": len([e for e in errors if e.category == "formula" and e.severity == "warning"]),
            "ref_warnings": len([e for e in errors if e.category == "reference"]),
            "compat_errors": len([e for e in errors if e.category == "compat"]),
            "quality_warnings": len([e for e in errors if e.category == "quality" and e.severity == "warning"]),
            "quality_info": len([e for e in errors if e.category == "quality" and e.severity == "info"]),
            "structure_errors": len([e for e in errors if e.category == "structure"]),
        }
        return ValidationResult(
            file_id=file_id,
            timestamp=ValidationResult.make_timestamp(),
            errors=errors,
            summary=summary,
        )


__all__ = ["ValidationEngine", "ValidationError", "ValidationResult"]
