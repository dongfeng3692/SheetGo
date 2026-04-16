const preloadStageLabels: Record<string, string> = {
  reading: "正在读取文件",
  schema: "正在解析结构",
  stats: "正在计算统计信息",
  formula: "正在扫描公式",
  formulas: "正在扫描公式",
  done: "处理完成",
};

const preloadMessageLabels: Record<string, string> = {
  "Reading workbook": "正在读取文件",
  "Extracting schema": "正在解析结构",
  "Computing statistics": "正在计算统计信息",
  "Scanning formulas": "正在扫描公式",
  "Writing cache": "正在写入缓存",
  "Processing workbook metadata...": "正在处理工作簿元数据...",
};

export function formatPreloadLabel(stage?: string, message?: string): string {
  if (message) {
    if (preloadMessageLabels[message]) {
      return preloadMessageLabels[message];
    }

    const doneMatch = message.match(/^Done \((\d+)ms\)$/);
    if (doneMatch) {
      return `处理完成（${doneMatch[1]}ms）`;
    }

    return message;
  }

  if (stage) {
    return preloadStageLabels[stage] ?? stage;
  }

  return "正在处理工作簿元数据...";
}
