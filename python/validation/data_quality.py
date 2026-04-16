"""数据质量评估 — 空值率/重复行/混合类型/异常值"""

from __future__ import annotations

import pandas as pd

from .result import ErrorCode, ValidationError

# 空值率告警阈值
_NULL_RATE_THRESHOLD = 0.3

# 异常值 IQR 倍数
_IQR_MULTIPLIER = 1.5


def has_mixed_types(series: pd.Series) -> bool:
    """检测列内是否包含混合数据类型（排除 NaN）"""
    non_null = series.dropna()
    if len(non_null) < 2:
        return False

    # 获取每个值的 Python 类型
    # 注意: bool 是 int 的子类，必须先检查 bool
    types = set()
    for val in non_null:
        if isinstance(val, bool):
            types.add("bool")
        elif isinstance(val, (int, float)):
            types.add("number")
        elif isinstance(val, str):
            types.add("text")
        else:
            types.add(type(val).__name__)

    return len(types) > 1


def detect_outliers(series: pd.Series) -> list[int]:
    """使用 IQR 方法检测数值列的异常值，返回异常值索引"""
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if len(numeric) < 4:
        return []

    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1

    if iqr == 0:
        return []

    lower = q1 - _IQR_MULTIPLIER * iqr
    upper = q3 + _IQR_MULTIPLIER * iqr

    outlier_mask = (numeric < lower) | (numeric > upper)
    return list(outlier_mask[outlier_mask].index)


def check_data_quality(
    file_path: str,
    sheets: list[str] | None = None,
) -> list[ValidationError]:
    """通过 pandas 快速评估数据质量"""
    errors: list[ValidationError] = []

    # 用 pandas 获取 sheet 列表，避免 openpyxl 冗余加载
    try:
        xls = pd.ExcelFile(file_path, engine="openpyxl")
    except Exception:
        return errors

    target_sheets = sheets if sheets else xls.sheet_names

    for sheet_name in target_sheets:
        if sheet_name not in xls.sheet_names:
            continue

        # 使用 pandas 读取 sheet 数据
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name)
        except Exception:
            continue

        total = len(df)
        if total == 0:
            continue

        for col in df.columns:
            series = df[col]

            # 空值率检查
            null_count = series.isnull().sum()
            null_rate = null_count / total
            if null_rate > _NULL_RATE_THRESHOLD:
                errors.append(ValidationError(
                    severity="warning",
                    category="quality",
                    sheet=sheet_name,
                    cell=str(col),
                    code=ErrorCode.QUALITY_HIGH_NULL_RATE,
                    message=f"列 '{col}' 空值率 {null_rate:.1%}（{null_count}/{total}）",
                    detail={
                        "column": str(col),
                        "null_rate": round(null_rate, 4),
                        "null_count": int(null_count),
                        "total_rows": total,
                    },
                ))

            # 混合类型检查
            if has_mixed_types(series):
                errors.append(ValidationError(
                    severity="info",
                    category="quality",
                    sheet=sheet_name,
                    cell=str(col),
                    code=ErrorCode.QUALITY_MIXED_TYPES,
                    message=f"列 '{col}' 包含混合数据类型",
                    detail={"column": str(col)},
                ))

            # 异常值检测（仅数值列）
            numeric_series = pd.to_numeric(series, errors="coerce")
            if numeric_series.notna().sum() >= 4:
                outlier_indices = detect_outliers(series)
                if outlier_indices:
                    errors.append(ValidationError(
                        severity="info",
                        category="quality",
                        sheet=sheet_name,
                        cell=str(col),
                        code=ErrorCode.QUALITY_OUTLIERS,
                        message=f"列 '{col}' 发现 {len(outlier_indices)} 个异常值（IQR 方法）",
                        detail={
                            "column": str(col),
                            "outlier_count": len(outlier_indices),
                        },
                    ))

        # 重复行检查
        dup_count = int(df.duplicated().sum())
        if dup_count > 0:
            errors.append(ValidationError(
                severity="info",
                category="quality",
                sheet=sheet_name,
                cell="",
                code=ErrorCode.QUALITY_DUPLICATE_ROWS,
                message=f"发现 {dup_count} 行完全重复数据",
                detail={
                    "duplicate_count": dup_count,
                    "total_rows": total,
                },
            ))

    xls.close()
    return errors
