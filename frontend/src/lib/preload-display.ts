const preloadStageLabels: Record<string, string> = {
  copying: "复制文件中",
  reading: "读取表格中",
  duckdb: "载入数据中",
  schema: "识别字段中",
  sampling: "抽取样本中",
  stats: "统计特征中",
  formula: "检查公式中",
  formulas: "检查公式中",
  validation: "校验内容中",
  styles: "提取样式中",
  structure: "分析表结构中",
  error: "处理失败",
  done: "处理完成",
};

const preloadMessageLabels: Record<string, string> = {
  "Copying file...": "复制文件中",
  "Reading workbook": "读取表格中",
  "Reading data...": "读取表格中",
  "Loading to DuckDB...": "载入数据中",
  "Extracting schema": "识别字段中",
  "Extracting schema...": "识别字段中",
  "Extracting samples...": "抽取样本中",
  "Computing statistics": "统计特征中",
  "Computing statistics...": "统计特征中",
  "Scanning formulas": "检查公式中",
  "Scanning formulas...": "检查公式中",
  "Running validation...": "校验内容中",
  "Extracting styles...": "提取样式中",
  "Analyzing file structure...": "分析表结构中",
  "Writing cache": "写入缓存中",
  "Writing cache...": "写入缓存中",
  "Processing workbook metadata...": "整理文件信息中",
};

export function formatPreloadLabel(stage?: string, message?: string): string {
  if (message) {
    if (preloadMessageLabels[message]) {
      return preloadMessageLabels[message];
    }

    const doneMatch = message.match(/^Done \((\d+)ms\)$/);
    if (doneMatch) {
      return `即将完成（${doneMatch[1]}ms）`;
    }

    const errorMatch = message.match(/^Error:\s*(.+)$/);
    if (errorMatch) {
      return `处理失败：${errorMatch[1]}`;
    }

    return message;
  }

  if (stage) {
    return preloadStageLabels[stage] ?? stage;
  }

  return "整理文件信息中";
}
