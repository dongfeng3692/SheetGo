# 模块 3: Preload Pipeline — 预加载管线

## 概述

用户上传 Excel 文件后，立即执行预加载管线，将文件数据加载到 DuckDB、提取 schema/样本/统计信息并缓存。预加载完成后，后续的查询和分析操作可以毫秒级响应。

这是**解决延迟问题的核心模块**。没有预加载，每次用户提问都需要重新读取文件（2-5s）；预加载后降至 <100ms。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 从 working/ 文件加载数据到 DuckDB | 文件上传和存储（模块 2） |
| 提取 schema（列名/类型/约束） | 执行 SQL 查询（模块 4 的 query_data 工具） |
| 提取样本数据（前 N 行） | 验证检查（模块 5） |
| 计算统计摘要（行数/分布/空值率） | |
| 扫描公式和依赖关系图 | |
| 提取样式索引 | |
| 管理缓存文件的生命周期 | |
| 报告预加载进度 | |

## 数据结构

### Schema 缓存 (`cache/{file_id}_schema.json`)

```json
{
  "fileId": "xxx",
  "sheets": [
    {
      "name": "Sheet1",
      "tableName": "sheet1",
      "dataRange": "A1:F1000",
      "rowCount": 1000,
      "colCount": 6,
      "hasHeaders": true,
      "columns": [
        {
          "name": "日期",
          "index": 0,
          "colLetter": "A",
          "dtype": "datetime64",
          "nullable": false,
          "nullCount": 0,
          "uniqueCount": 365,
          "sample": ["2024-01-01", "2024-01-02", "2024-01-03"],
          "stats": {
            "min": "2024-01-01",
            "max": "2024-12-31"
          }
        },
        {
          "name": "销售额",
          "index": 1,
          "colLetter": "B",
          "dtype": "float64",
          "nullable": false,
          "nullCount": 2,
          "uniqueCount": 800,
          "sample": [15000.0, 23000.0, 8500.0],
          "stats": {
            "min": 0.0,
            "max": 999999.0,
            "mean": 45230.5,
            "median": 38000.0,
            "std": 28500.3
          }
        },
        {
          "name": "地区",
          "index": 2,
          "colLetter": "C",
          "dtype": "object",
          "nullable": false,
          "nullCount": 0,
          "uniqueCount": 5,
          "sample": ["华东", "华南", "华北"],
          "stats": {
            "topValues": [
              {"value": "华东", "count": 250},
              {"value": "华南", "count": 200},
              {"value": "华北", "count": 180},
              {"value": "华中", "count": 170},
              {"value": "西部", "count": 200}
            ]
          }
        }
      ],
      "mergedCells": [
        {"range": "A1:F1", "value": "2024年销售数据"}
      ],
      "formulas": [
        {
          "cell": "F2",
          "formula": "=SUM(B2:E2)",
          "dependsOn": ["B2", "C2", "D2", "E2"]
        }
      ]
    }
  ]
}
```

### 统计缓存 (`cache/{file_id}_stats.json`)

```json
{
  "fileId": "xxx",
  "totalSheets": 3,
  "totalRows": 5000,
  "totalCols": 18,
  "totalFormulas": 150,
  "dataQuality": {
    "nullRate": 0.02,
    "duplicateRows": 0,
    "mixedTypeColumns": ["D"],
    "outlierColumns": {}
  },
  "formulaSummary": {
    "totalCount": 150,
    "errors": 2,
    "crossSheetRefs": 10,
    "compatWarnings": ["F5: uses FILTER()"]
  }
}
```

### 预加载进度

```typescript
interface PreloadProgress {
  fileId: string;
  stage: 'copying' | 'reading' | 'duckdb' | 'schema' | 'sampling' |
         'stats' | 'formulas' | 'styles' | 'done' | 'error';
  progress: number;     // 0-100
  message: string;      // "正在加载 DuckDB (45%)..."
  elapsed: number;      // 已用毫秒
}
```

## 接口定义

### Python JSON-RPC

```json
// 触发预加载
{
  "method": "preload.start",
  "params": {
    "file_id": "xxx",
    "file_path": "~/.sheetgo/workspace/{session}/working/xxx.xlsx",
    "options": {
      "sample_rows": 20,
      "max_stats_rows": 100000
    }
  }
}

// 响应（最终结果）
{
  "result": {
    "status": "ok",
    "file_id": "xxx",
    "schema_path": "cache/xxx_schema.json",
    "stats_path": "cache/xxx_stats.json",
    "duration_ms": 3200
  }
}

// 流式进度（通过 stderr 或 Tauri Event）
{
  "method": "preload.progress",
  "params": { "file_id": "xxx", "stage": "duckdb", "progress": 45, "message": "正在加载到 DuckDB..." }
}
```

### Python 内部接口

```python
# python/preload/pipeline.py

class PreloadPipeline:
    def __init__(self, workspace: SessionWorkspace):
        self.workspace = workspace

    async def run(self, file_id: str, file_path: str, on_progress: Callable) -> PreloadResult:
        """执行完整预加载管线"""
        ...

    def _step_read_data(self, file_path: str) -> dict[str, pd.DataFrame]:
        """Step 1-2: calamine 快速读取所有 sheet"""

    def _step_register_duckdb(self, file_id: str, data: dict[str, pd.DataFrame]) -> str:
        """Step 3: 注册到 DuckDB，返回 .duckdb 路径"""

    def _step_extract_schema(self, file_path: str, data: dict) -> list[SheetSchema]:
        """Step 4: 提取 schema"""

    def _step_extract_sample(self, data: dict, n_rows: int) -> dict:
        """Step 5: 提取前 N 行样本"""

    def _step_compute_stats(self, data: dict) -> FileStats:
        """Step 6: 计算统计摘要"""

    def _step_scan_formulas(self, file_path: str) -> FormulaGraph:
        """Step 7: 扫描公式和依赖关系"""

    def _step_extract_styles(self, file_path: str) -> StyleIndex:
        """Step 9: 提取样式索引"""

    def get_schema(self, file_id: str) -> dict | None:
        """获取已缓存的 schema"""

    def get_stats(self, file_id: str) -> dict | None:
        """获取已缓存的统计信息"""
```

## 实现要点

### 1. calamine 快速读取

使用 Python 绑定 `python-calamine`（Rust calamine 的 Python wrapper）：

```python
from python_calamine import CalamineWorkbook

def read_all_sheets(file_path: str) -> dict[str, list[list]]:
    """极快的 Excel 读取（纯数据，不读格式）"""
    wb = CalamineWorkbook.from_path(file_path)
    result = {}
    for sheet_name in wb.sheet_names:
        result[sheet_name] = wb.get_sheet_by_name(sheet_name).to_python()
    return result
    # 10 万行文件 ~500ms，比 openpyxl 快 10-50 倍
```

### 2. DuckDB 注册

```python
import duckdb

def register_to_duckdb(file_id: str, sheets: dict[str, pd.DataFrame], db_path: str):
    """将所有 sheet 注册为 DuckDB 表"""
    con = duckdb.connect(db_path)

    for sheet_name, df in sheets.items():
        table_name = sanitize_table_name(sheet_name)
        # 注册为持久表
        con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df")

        # 同时注册一个带文件前缀的表名（支持多文件场景）
        con.execute(f"CREATE OR REPLACE VIEW {file_id}_{table_name} AS SELECT * FROM {table_name}")

    con.close()
```

### 3. Schema 提取

```python
def extract_column_stats(df: pd.DataFrame, col: str) -> ColumnSchema:
    series = df[col]
    return ColumnSchema(
        name=col,
        dtype=str(series.dtype),
        nullable=series.isnull().any(),
        nullCount=int(series.isnull().sum()),
        uniqueCount=int(series.nunique()),
        sample=series.dropna().head(3).tolist(),
        stats=compute_stats(series),  # 数值型: min/max/mean/std; 分类型: top values
    )
```

### 4. 公式扫描

```python
from openpyxl import load_workbook

def scan_formulas(file_path: str) -> list[FormulaInfo]:
    """扫描所有公式单元格，构建引用关系图"""
    wb = load_workbook(file_path)
    formulas = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == 'f':  # 公式类型
                    deps = extract_references(cell.value, ws.title, wb.sheetnames)
                    formulas.append(FormulaInfo(
                        sheet=ws.title,
                        cell=cell.coordinate,
                        formula=cell.value,
                        dependsOn=deps
                    ))
    return formulas
```

### 5. 样式索引

```python
def extract_style_index(file_path: str) -> StyleIndex:
    """提取样式信息（用于修改时格式保留）"""
    wb = load_workbook(file_path)
    styles = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows(max_row=100):  # 只扫描前100行
            for cell in row:
                if cell.has_style:
                    styles[cell.coordinate] = {
                        'font': serialize_font(cell.font),
                        'fill': serialize_fill(cell.fill),
                        'border': serialize_border(cell.border),
                        'number_format': cell.number_format,
                    }
    return styles
```

## 预加载耗时目标

| 文件大小 | 行数 | 目标耗时 | 瓶颈 |
|---------|------|---------|------|
| < 1MB | < 1万行 | < 2s | 公式扫描 |
| 1-10MB | 1-10万行 | < 5s | DuckDB 注册 |
| 10-50MB | 10-50万行 | < 15s | calamine 读取 |
| > 50MB | > 50万行 | < 30s | 全流程 |

**优化手段**:
- 大文件只读取前 N 行做 schema/sample（stats 用 DuckDB 计算）
- 公式扫描用 calamine 检测是否有公式，无公式则跳过
- 样式索引限制扫描范围（前 100 行 + 表头）
- DuckDB 注册时可选择 only_schema 模式（不复制数据）

## 文件清单

| 文件 | 说明 |
|------|------|
| `python/preload/__init__.py` | 模块入口 |
| `python/preload/pipeline.py` | 预加载主流程编排 |
| `python/preload/schema_extractor.py` | Schema 提取 |
| `python/preload/stats_calculator.py` | 统计信息计算 |
| `python/preload/formula_scanner.py` | 公式扫描和依赖图 |
| `python/preload/style_extractor.py` | 样式索引提取 |

## 依赖

- 模块 2（File Manager）: 提供文件路径（working/ 目录）
- 模块 4（Excel Engine）: reader.py 提供读取能力

## 测试要求

- 预加载 1MB xlsx 文件 → 验证 schema/stats 缓存生成
- 预加载含多 sheet 文件 → 验证所有 sheet 都注册到 DuckDB
- 预加载含公式文件 → 验证公式依赖图正确
- 预加载 CSV 文件 → 验证类型推断
- 大文件预加载 → 验证进度上报和耗时目标
- 重复预加载 → 验证缓存命中（跳过已加载文件）
