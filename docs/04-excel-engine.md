# 模块 4: Excel Engine — Excel 读写引擎

## 概述

提供所有 Excel 底层操作能力：读取、写入、公式操作、XML 辅助脚本、DuckDB 查询。是 Agent 工具集的基础设施层。

核心设计原则：**用 DuckDB 处理数据查询，用 XML 辅助脚本处理结构修改，避免 openpyxl round-trip 丢失格式。**

## 职责边界

| 负责 | 不负责 |
|------|--------|
| calamine 快速读取 | 预加载编排（模块 3） |
| openpyxl 格式感知读取 | 验证逻辑（模块 5） |
| DuckDB SQL 查询执行 | Agent 工具注册（模块 6） |
| XML pack/unpack 辅助 | UI 渲染（模块 8） |
| 单元格精确写入（XML 级） | |
| 公式写入与依赖分析 | |
| 列/行增删（XML shift） | |
| 图表创建（openpyxl.chart） | |
| 样式系统（金融格式模板） | |
| 文件导出（xlsx/csv） | |
| 新建文件模板系统 | |

## 数据结构

```python
# 统一的数据范围描述
@dataclass
class CellRange:
    sheet: str
    start_col: str       # "A"
    start_row: int       # 1
    end_col: str         # "F"
    end_row: int         # 100

    def to_excel_ref(self) -> str:
        """'Sheet1'!A1:F100"""
        return f"'{self.sheet}'!{self.start_col}{self.start_row}:{self.end_col}{self.end_row}"

# 单元格修改描述
@dataclass
class CellEdit:
    sheet: str
    cell: str            # "B2"
    value: Any           # 值或公式（以 = 开头）
    style: dict | None   # 可选样式覆盖

# 修改结果
@dataclass
class EditResult:
    success: bool
    affected_cells: list[str]       # ["B2", "B3", ...]
    affected_formulas: list[str]    # 被影响的公式单元格
    warnings: list[str]
```

## 接口定义

### ExcelReader — 读取

```python
class ExcelReader:
    """Excel 文件读取器（calamine 快读 + openpyxl 格式信息）"""

    def read_sheet_data(self, file_path: str, sheet: str,
                        range: CellRange | None = None) -> pd.DataFrame:
        """读取工作表数据为 DataFrame（calamine，极速）"""

    def read_cell(self, file_path: str, sheet: str, cell: str) -> Any:
        """读取单个单元格值"""

    def read_formulas(self, file_path: str, sheet: str | None = None) -> list[FormulaInfo]:
        """读取所有公式（openpyxl）"""

    def read_merged_cells(self, file_path: str, sheet: str) -> list[str]:
        """读取合并单元格范围"""

    def read_styles(self, file_path: str, sheet: str,
                    range: CellRange | None = None) -> dict[str, dict]:
        """读取样式信息"""

    def read_sheet_names(self, file_path: str) -> list[str]:
        """读取所有工作表名"""

    def read_dimensions(self, file_path: str, sheet: str) -> CellRange:
        """读取工作表数据范围"""
```

### ExcelWriter — 写入

```python
class ExcelWriter:
    """Excel 文件写入器（XML 级精确写入，保留格式）"""

    def write_cells(self, file_path: str, edits: list[CellEdit],
                    preserve_format: bool = True) -> EditResult:
        """批量写入单元格（XML 级精确修改）"""

    def add_formula(self, file_path: str, sheet: str, cell: str,
                    formula: str) -> EditResult:
        """写入公式（自动检测兼容性）"""

    def add_column(self, file_path: str, sheet: str, col_letter: str,
                   header: str, data: list[Any] | None = None,
                   formula: str | None = None,
                   formula_rows: tuple[int, int] | None = None,
                   numfmt: str | None = None) -> EditResult:
        """在指定位置添加列"""

    def insert_row(self, file_path: str, sheet: str, at_row: int,
                   values: dict[str, Any] | None = None,
                   formula: dict[str, str] | None = None,
                   copy_style_from: int | None = None) -> EditResult:
        """在指定位置插入行（自动 shift）"""

    def delete_rows(self, file_path: str, sheet: str,
                    start: int, count: int = 1) -> EditResult:
        """删除行"""

    def apply_style(self, file_path: str, sheet: str, range: CellRange,
                    style: StyleConfig) -> EditResult:
        """应用样式到范围"""

    def create_sheet(self, file_path: str, name: str) -> EditResult:
        """创建新工作表"""
```

### ChartEngine — 图表

```python
class ChartEngine:
    """图表创建引擎"""

    def create_chart(self, file_path: str, config: ChartConfig) -> EditResult:
        """创建图表并插入到工作表"""

    def list_charts(self, file_path: str, sheet: str | None = None) -> list[ChartInfo]:
        """列出所有图表"""

    def remove_chart(self, file_path: str, sheet: str, chart_index: int) -> EditResult:
        """删除图表"""

@dataclass
class ChartConfig:
    chart_type: str          # "bar" | "line" | "pie" | "area" | "scatter"
    source_range: CellRange  # 数据源范围
    target_cell: str         # 插入位置，如 "F1"
    target_sheet: str
    title: str = ""
    x_axis_title: str = ""
    y_axis_title: str = ""
    style: str = "monochrome"  # "monochrome" | "finance"
    show_labels: bool = True
    width: float = 15.0      # cm
    height: float = 10.0     # cm
```

### DuckDBQuery — SQL 查询

```python
class DuckDBQuery:
    """DuckDB SQL 查询（操作预加载后的数据）"""

    def execute(self, db_path: str, sql: str) -> pd.DataFrame:
        """执行 SQL 查询，返回 DataFrame"""

    def list_tables(self, db_path: str) -> list[str]:
        """列出所有已注册表"""

    def describe_table(self, db_path: str, table: str) -> list[ColumnDesc]:
        """描述表结构"""

    def validate_sql(self, sql: str) -> tuple[bool, str]:
        """验证 SQL 安全性（只允许 SELECT）"""
```

### XMLHelpers — XML 辅助脚本

```python
class XMLHelpers:
    """OOXML 底层 XML 操作（借鉴 minimax-xlsx）"""

    def unpack(self, xlsx_path: str, work_dir: str) -> None:
        """解压 xlsx 为 XML 目录结构"""

    def pack(self, work_dir: str, output_path: str) -> None:
        """将 XML 目录打包回 xlsx"""

    def shift_rows(self, work_dir: str, sheet: str,
                   insert_at: int, count: int) -> None:
        """Shift row references in XML（跨 worksheets/charts/tables/pivot）"""

    def get_sheet_xml_path(self, work_dir: str, sheet: str) -> str:
        """获取工作表 XML 文件路径"""

    def get_shared_strings(self, work_dir: str) -> dict[int, str]:
        """读取 sharedStrings.xml"""

    def update_shared_strings(self, work_dir: str, strings: dict[int, str]) -> None:
        """更新 sharedStrings.xml"""
```

### TemplateEngine — 新建文件模板

```python
class TemplateEngine:
    """Excel 文件创建模板系统"""

    def create_minimal(self, output_path: str, sheets: list[str]) -> None:
        """从 XML 模板创建最小 xlsx 文件"""

    def get_style_slot(self, slot_name: str) -> int:
        """获取预定义样式 slot 的索引"""
        # "blue_input" -> 1
        # "black_formula" -> 2
        # "green_cross_sheet" -> 3
        # "header" -> 4
```

模板目录结构（借鉴 minimax-xlsx 的 `templates/minimal_xlsx/`）：

```
python/excel/templates/minimal_xlsx/
├── [Content_Types].xml
├── _rels/.rels
├── xl/
│   ├── workbook.xml
│   ├── _rels/workbook.xml.rels
│   ├── styles.xml           # 预定义 13 个样式 slot
│   ├── sharedStrings.xml
│   └── worksheets/
│       └── sheet1.xml
```

### StyleEngine — 样式系统

```python
class StyleEngine:
    """样式系统（金融格式标准）"""

    # 预定义颜色
    COLORS = {
        'input_blue': '0000FF',       # 硬编码输入
        'formula_black': '000000',    # 公式/计算
        'cross_sheet_green': '00B050', # 跨表引用
        'external_red': 'FF0000',     # 外部链接
        'attention_yellow': 'FFFF00', # 注意事项（背景）
    }

    # 预定义数字格式
    NUM_FORMATS = {
        'currency': '$#,##0',
        'currency_negative': '$#,##0;($#,##0);-',
        'percentage': '0.0%',
        'multiple': '0.0x',
        'year': '0',                  # 避免千分位
        'integer_comma': '#,##0',
    }

    def get_financial_style(self, role: str) -> dict:
        """获取金融格式样式配置"""
        # role: "input" | "formula" | "cross_sheet" | "header" | "total"

    def apply_financial_format(self, file_path: str, sheet: str,
                               range: CellRange, role: str) -> EditResult:
        """应用金融格式到指定范围"""
```

## 实现要点

### 1. XML 级精确写入（避免 openpyxl round-trip 丢失格式）

```python
def write_cells(self, file_path: str, edits: list[CellEdit]) -> EditResult:
    """
    核心写入流程：
    1. unpack xlsx → XML 目录
    2. 解析目标 sheet XML
    3. 精确修改目标单元格（保留其他所有内容不变）
    4. pack XML 目录 → xlsx
    """
    work_dir = tempfile.mkdtemp()
    self.xml_helpers.unpack(file_path, work_dir)

    sheet_path = self.xml_helpers.get_sheet_xml_path(work_dir, sheet)
    tree = ET.parse(sheet_path)
    root = tree.getroot()

    for edit in edits:
        cell_elem = find_or_create_cell(root, edit.cell)
        if edit.value and str(edit.value).startswith('='):
            # 公式
            set_formula(cell_elem, edit.value)
        else:
            # 值
            set_value(cell_elem, edit.value)

    tree.write(sheet_path, xml_declaration=True, encoding='UTF-8')
    self.xml_helpers.pack(work_dir, file_path)
```

### 2. 行插入的 shift 策略（借鉴 minimax-xlsx）

```python
def insert_row(self, file_path: str, sheet: str, at_row: int, ...) -> EditResult:
    """
    1. unpack
    2. shift_rows: 将 at_row 及以下的行号全部 +1
       - 更新 worksheet XML 中的 row 引用
       - 更新 chart XML 中的数据范围引用
       - 更新 table XML 中的范围引用
       - 更新 mergedCells
       - 更新 conditionalFormatting
    3. 在 at_row 位置插入新行
    4. 复制样式（如果 copy_style_from 指定）
    5. pack
    """
```

### 3. DuckDB 查询安全

```python
SQL_DANGEROUS_KEYWORDS = {
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
    'EXEC', 'EXECUTE', 'GRANT', 'REVOKE', 'TRUNCATE', 'REPLACE'
}

def validate_sql(self, sql: str) -> tuple[bool, str]:
    """验证 SQL 只允许 SELECT"""
    parsed = sqlglot.parse(sql)
    for stmt in parsed:
        if not isinstance(stmt, sqlglot.exp.Select):
            return False, f"Only SELECT allowed, got {type(stmt).__name__}"
    return True, "OK"
```

### 4. 图表创建

```python
from openpyxl.chart import BarChart, LineChart, PieChart, Reference

def create_chart(self, file_path: str, config: ChartConfig) -> EditResult:
    """使用 openpyxl.chart 创建图表"""
    wb = load_workbook(file_path)
    ws = wb[config.target_sheet]
    source_ws = wb[config.source_range.sheet]

    chart = create_chart_by_type(config.chart_type)
    data = Reference(source_ws, ...)
    chart.add_data(data, titles_from_data=True)

    # 应用样式
    apply_chart_style(chart, config.style)

    ws.add_chart(chart, config.target_cell)
    wb.save(file_path)
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `python/excel/__init__.py` | 模块入口，导出 Reader/Writer/Query 等 |
| `python/excel/reader.py` | ExcelReader 类 |
| `python/excel/writer.py` | ExcelWriter 类（XML 级写入） |
| `python/excel/xml_helpers.py` | XMLHelpers 类（pack/unpack/shift） |
| `python/excel/formula_parser.py` | 公式解析和依赖分析 |
| `python/excel/style_engine.py` | StyleEngine 类 |
| `python/excel/chart_engine.py` | ChartEngine 类 |
| `python/excel/template_engine.py` | TemplateEngine 类 |
| `python/excel/duckdb_query.py` | DuckDBQuery 类 |
| `python/excel/templates/minimal_xlsx/` | XML 模板骨架 |
| `python/tools/*.py` | Agent 工具封装（调用 excel/ 层） |

## 依赖

- `python-calamine` — 快速 Excel 读取
- `openpyxl` — 格式读取、图表、样式
- `duckdb` — SQL 查询引擎
- `sqlglot` — SQL 解析和验证
- `lxml` — XML 操作

## 测试要求

- 读取各种 xlsx 文件（含公式/图表/合并单元格/多 sheet）
- 写入单元格 → 用 Excel 打开验证格式保留
- 插入行 → 验证公式引用自动调整
- 添加列 → 验证样式复制
- DuckDB 查询 → 验证结果与 openpyxl 一致
- 图表创建 → 验证可在 Excel 中正确渲染
- SQL 注入 → 验证非 SELECT 语句被拒绝
- 大文件（10万行）写入性能
