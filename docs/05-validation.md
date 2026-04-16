# 模块 5: Validation Engine — 验证引擎

## 概述

负责 Excel 文件的多层次验证：公式错误检测、引用范围校验、函数兼容性检查、数据质量评估、OpenXML 结构验证。上传时全量运行，修改后增量运行，导出前强制运行。

设计借鉴 kimi-xlsx 的 per-sheet 验证循环和 minimax-xlsx 的两级验证架构（静态 + 动态）。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 公式错误检测（7 种错误类型） | Excel 读写操作（模块 4） |
| 引用范围校验 | 自动修复（只检测，修复由 Agent 决策） |
| 函数兼容性检查（禁用函数） | |
| 数据质量评估（空值/重复/异常） | |
| OpenXML 结构验证 | |
| 验证结果格式化输出 | |
| 验证结果缓存 | |

## 数据结构

```python
@dataclass
class ValidationError:
    severity: str          # "error" | "warning" | "info"
    category: str          # "formula" | "reference" | "compat" | "quality" | "structure"
    sheet: str
    cell: str              # "B5" 或 ""（工作表级别）
    code: str              # "FORMULA_REF_ERROR" | "FORBIDDEN_FUNCTION" | ...
    message: str           # 人可读的描述
    detail: dict           # 额外信息（如公式内容、建议修复方案）

@dataclass
class ValidationResult:
    file_id: str
    timestamp: str
    errors: list[ValidationError]
    summary: dict          # {"formula_errors": 3, "ref_warnings": 2, ...}
    passed: bool           # 所有 error 级别问题为 0

    @property
    def error_count(self) -> int:
        return len([e for e in self.errors if e.severity == "error"])

    @property
    def warning_count(self) -> int:
        return len([e for e in self.errors if e.severity == "warning"])
```

### 错误码定义

```python
class ErrorCode:
    # 公式错误
    FORMULA_REF_ERROR = "FORMULA_REF_ERROR"          # #REF!
    FORMULA_DIV_ZERO = "FORMULA_DIV_ZERO"            # #DIV/0!
    FORMULA_VALUE_ERROR = "FORMULA_VALUE_ERROR"      # #VALUE!
    FORMULA_NAME_ERROR = "FORMULA_NAME_ERROR"        # #NAME?
    FORMULA_NULL_ERROR = "FORMULA_NULL_ERROR"        # #NULL!
    FORMULA_NUM_ERROR = "FORMULA_NUM_ERROR"          # #NUM!
    FORMULA_NA_ERROR = "FORMULA_NA_ERROR"            # #N/A
    FORMULA_ZERO_VALUE = "FORMULA_ZERO_VALUE"        # 公式结果为 0（可能引用错误）

    # 引用错误
    REF_OUT_OF_RANGE = "REF_OUT_OF_RANGE"            # 引用范围远超实际数据行
    REF_HEADER_INCLUDED = "REF_HEADER_INCLUDED"      # 公式包含表头行
    REF_INSUFFICIENT_RANGE = "REF_INSUFFICIENT_RANGE" # SUM/AVERAGE 范围太小
    REF_INCONSISTENT_PATTERN = "REF_INCONSISTENT_PATTERN" # 同列公式模式不一致

    # 兼容性
    COMPAT_FORBIDDEN_FUNCTION = "COMPAT_FORBIDDEN_FUNCTION"  # FILTER/XLOOKUP 等

    # 数据质量
    QUALITY_HIGH_NULL_RATE = "QUALITY_HIGH_NULL_RATE"       # 空值率 > 30%
    QUALITY_DUPLICATE_ROWS = "QUALITY_DUPLICATE_ROWS"       # 重复行
    QUALITY_MIXED_TYPES = "QUALITY_MIXED_TYPES"             # 同列混合类型
    QUALITY_OUTLIERS = "QUALITY_OUTLIERS"                    # 异常值

    # 结构
    STRUCTURE_INVALID_XML = "STRUCTURE_INVALID_XML"         # XML 不合法
    STRUCTURE_BROKEN_RELS = "STRUCTURE_BROKEN_RELS"         # .rels 引用不存在的文件
    STRUCTURE_MISSING_CONTENT_TYPE = "STRUCTURE_MISSING_CONTENT_TYPE"
```

## 接口定义

```python
class ValidationEngine:
    """Excel 验证引擎"""

    def full_check(self, file_path: str, file_id: str) -> ValidationResult:
        """全量验证（上传时运行）"""
        errors = []
        errors.extend(self.check_formulas(file_path))
        errors.extend(self.check_references(file_path))
        errors.extend(self.check_compatibility(file_path))
        errors.extend(self.check_data_quality(file_path))
        return ValidationResult(file_id=file_id, errors=errors, ...)

    def quick_check(self, file_path: str, file_id: str,
                    changed_sheets: list[str]) -> ValidationResult:
        """增量验证（修改后运行，只检查变更 sheet）"""

    def final_check(self, file_path: str, file_id: str) -> ValidationResult:
        """导出前强制验证（结构 + 公式）"""

    # --- 各子检查器 ---

    def check_formulas(self, file_path: str,
                       sheets: list[str] | None = None) -> list[ValidationError]:
        """公式错误检测"""

    def check_references(self, file_path: str,
                         sheets: list[str] | None = None) -> list[ValidationError]:
        """引用范围校验"""

    def check_compatibility(self, file_path: str,
                            sheets: list[str] | None = None) -> list[ValidationError]:
        """函数兼容性检查"""

    def check_data_quality(self, file_path: str,
                           sheets: list[str] | None = None) -> list[ValidationError]:
        """数据质量评估"""

    def check_structure(self, file_path: str) -> list[ValidationError]:
        """OpenXML 结构验证"""
```

## 实现要点

### 1. 公式错误检测（借鉴 kimi-xlsx recheck）

```python
def check_formulas(self, file_path: str) -> list[ValidationError]:
    """
    检测所有公式单元格的错误值。
    使用 openpyxl (data_only=True) 读取缓存的计算结果。
    """
    wb = load_workbook(file_path, data_only=True)
    errors = []
    error_types = {
        '#REF!', '#DIV/0!', '#VALUE!', '#NAME?', '#NULL!', '#NUM!', '#N/A'
    }

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == 'e':  # error type
                    errors.append(ValidationError(
                        severity="error",
                        category="formula",
                        sheet=ws.title,
                        cell=cell.coordinate,
                        code=map_error_code(cell.value),
                        message=f"公式错误 {cell.value} 在 {ws.title}!{cell.coordinate}",
                    ))

                # 隐式数组公式检测（LibreOffice 兼容但 Excel 不兼容）
                elif cell.data_type == 'f':
                    formula = cell.value
                    if is_implicit_array_formula(formula):
                        errors.append(ValidationError(
                            severity="warning",
                            category="formula",
                            ...
                            message=f"隐式数组公式，需 CSE 确认: {formula}",
                            detail={"suggestion": rewrite_without_array(formula)}
                        ))

    return errors
```

### 2. 引用范围校验（借鉴 kimi-xlsx reference-check）

```python
def check_references(self, file_path: str) -> list[ValidationError]:
    """
    4 种引用问题检测:
    1. 引用范围远超实际数据行
    2. 公式包含表头行
    3. 聚合函数范围太小（≤2 单元格）
    4. 同列公式模式不一致
    """
    wb = load_workbook(file_path)
    errors = []

    for ws in wb.worksheets:
        data_range = ws.dimensions  # 如 "A1:F1000"
        max_row = ws.max_row

        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type != 'f':
                    continue

                refs = extract_cell_references(cell.value)

                for ref in refs:
                    # 检查 1: 引用范围远超实际行数
                    if ref.max_row > max_row * 2:
                        errors.append(ValidationError(
                            severity="warning", category="reference",
                            code="REF_OUT_OF_RANGE", ...))

                    # 检查 2: 是否包含表头行（第 1 行）
                    if ref.min_row == 1 and has_header(ws):
                        errors.append(ValidationError(
                            severity="warning", category="reference",
                            code="REF_HEADER_INCLUDED", ...))

                    # 检查 3: SUM/AVERAGE 范围太小
                    if is_aggregate_function(cell.value) and ref.row_count <= 2:
                        errors.append(ValidationError(
                            severity="warning", category="reference",
                            code="REF_INSUFFICIENT_RANGE", ...))

    # 检查 4: 同列公式模式一致性
    errors.extend(check_formula_consistency(wb))

    return errors
```

### 3. 函数兼容性检查

```python
# Excel 2019 及更早版本不支持的函数
FORBIDDEN_FUNCTIONS = {
    'FILTER': {'alt': 'SUMIF/COUNTIF + AutoFilter', 'version': '2021+'},
    'UNIQUE': {'alt': 'Remove Duplicates + COUNTIF', 'version': '2021+'},
    'SORT': {'alt': 'Data → Sort', 'version': '2021+'},
    'SORTBY': {'alt': 'Data → Sort', 'version': '2021+'},
    'XLOOKUP': {'alt': 'INDEX + MATCH', 'version': '2021+'},
    'XMATCH': {'alt': 'MATCH', 'version': '2021+'},
    'SEQUENCE': {'alt': 'ROW() or manual fill', 'version': '2021+'},
    'LET': {'alt': 'Helper cells', 'version': '2021+'},
    'LAMBDA': {'alt': 'Named ranges or VBA', 'version': '2021+'},
    'RANDARRAY': {'alt': 'RAND() with fill', 'version': '2021+'},
    'ARRAYFORMULA': {'alt': 'CSE (Ctrl+Shift+Enter)', 'note': 'Google Sheets only'},
    'QUERY': {'alt': 'SUMIF/COUNTIF/PivotTable', 'note': 'Google Sheets only'},
}

def check_compatibility(self, file_path: str) -> list[ValidationError]:
    """检测不兼容函数"""
    wb = load_workbook(file_path)
    errors = []

    for ws in wb.worksheets:
        for cell in ws.iter_rows():
            if cell.data_type == 'f':
                func_name = extract_function_name(cell.value)
                if func_name in FORBIDDEN_FUNCTIONS:
                    info = FORBIDDEN_FUNCTIONS[func_name]
                    errors.append(ValidationError(
                        severity="error",
                        category="compat",
                        code="COMPAT_FORBIDDEN_FUNCTION",
                        sheet=ws.title,
                        cell=cell.coordinate,
                        message=f"不兼容函数 {func_name}（需要 Excel {info['version']}）",
                        detail={
                            "function": func_name,
                            "alternative": info['alt'],
                            "formula": cell.value,
                        }
                    ))

    return errors
```

### 4. 数据质量评估

```python
def check_data_quality(self, file_path: str) -> list[ValidationError]:
    """通过 DuckDB 快速评估数据质量"""
    errors = []

    for sheet_name, df in read_all_sheets(file_path).items():
        total = len(df)
        if total == 0:
            continue

        for col in df.columns:
            series = df[col]

            # 空值率检查
            null_rate = series.isnull().sum() / total
            if null_rate > 0.3:
                errors.append(ValidationError(
                    severity="warning", category="quality",
                    code="QUALITY_HIGH_NULL_RATE",
                    sheet=sheet_name, cell=col,
                    message=f"列 '{col}' 空值率 {null_rate:.1%}",
                ))

            # 混合类型检查
            if has_mixed_types(series):
                errors.append(ValidationError(
                    severity="info", category="quality",
                    code="QUALITY_MIXED_TYPES",
                    sheet=sheet_name, cell=col,
                    message=f"列 '{col}' 包含混合数据类型",
                ))

        # 重复行检查
        dup_count = df.duplicated().sum()
        if dup_count > 0:
            errors.append(ValidationError(
                severity="info", category="quality",
                code="QUALITY_DUPLICATE_ROWS",
                sheet=sheet_name, cell="",
                message=f"发现 {dup_count} 行完全重复数据",
            ))

    return errors
```

### 5. OpenXML 结构验证

```python
def check_structure(self, file_path: str) -> list[ValidationError]:
    """
    验证 xlsx 的 ZIP 结构完整性:
    1. [Content_Types].xml 存在且合法
    2. _rels/.rels 存在
    3. xl/workbook.xml 存在
    4. 所有 .rels 引用的文件都存在
    5. 所有文件在 [Content_Types].xml 中声明
    """
    errors = []
    try:
        with zipfile.ZipFile(file_path) as zf:
            names = set(zf.namelist())

            # 检查必需文件
            required = ['[Content_Types].xml', '_rels/.rels', 'xl/workbook.xml']
            for req in required:
                if req not in names:
                    errors.append(ValidationError(
                        severity="error", category="structure",
                        code="STRUCTURE_MISSING_FILE",
                        message=f"缺少必需文件: {req}",
                    ))

            # 检查 .rels 引用
            if '_rels/.rels' in names:
                rels = parse_rels(zf.read('_rels/.rels'))
                for target in rels.values():
                    if target not in names:
                        errors.append(ValidationError(
                            severity="error", category="structure",
                            code="STRUCTURE_BROKEN_RELS",
                            message=f".rels 引用不存在的文件: {target}",
                        ))

    except zipfile.BadZipFile:
        errors.append(ValidationError(
            severity="error", category="structure",
            code="STRUCTURE_INVALID_ZIP",
            message="文件不是有效的 ZIP/XLSX 格式",
        ))

    return errors
```

## 验证时机

| 时机 | 运行内容 | 失败策略 |
|------|---------|---------|
| **上传后** | full_check | 警告展示给用户，不阻止使用 |
| **每次修改后** | quick_check（只检查变更 sheet） | 错误展示给用户，提示 Agent 修复 |
| **导出前** | final_check（结构 + 公式） | 有 error 级别问题则阻止导出 |

## 文件清单

| 文件 | 说明 |
|------|------|
| `python/validation/__init__.py` | 模块入口，导出 ValidationEngine |
| `python/validation/formula_check.py` | 公式错误检测 |
| `python/validation/reference_check.py` | 引用范围校验 |
| `python/validation/compat_check.py` | 函数兼容性检查 |
| `python/validation/data_quality.py` | 数据质量评估 |
| `python/validation/openxml_validate.py` | OpenXML 结构验证 |
| `python/validation/result.py` | ValidationResult, ValidationError 定义 |

## 依赖

- 模块 4（Excel Engine）: reader 用于读取数据
- `openpyxl` — 公式读取
- `lxml` — XML 结构验证（可选）

## 测试要求

- 含 `#REF!` 等错误的文件 → 检测到所有 7 种错误类型
- 含 FILTER/XLOOKUP 的文件 → 检测到并给出替代方案
- 引用范围异常的文件 → 检测到越界/表头/范围过小
- 数据质量差的文件 → 检测到高空值率/重复行
- 结构损坏的 xlsx → 检测到缺失文件/断链
- 干净文件 → 0 error, 0 warning
