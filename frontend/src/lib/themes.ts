import type { AppConfig } from "./tauri";

export type ThemeMode = AppConfig["ui"]["theme"];
export type ThemePresetId = AppConfig["ui"]["themePreset"];

export interface ThemeModeOption {
  id: ThemeMode;
  label: string;
  description: string;
}

export interface ThemePresetDefinition {
  id: ThemePresetId;
  label: string;
  headline: string;
  description: string;
  mood: string;
  swatches: [string, string, string, string];
}

export const themeModeOptions: ThemeModeOption[] = [
  {
    id: "light",
    label: "浅色",
    description: "保持明亮画布，适合白天长时间处理表格。",
  },
  {
    id: "dark",
    label: "深色",
    description: "降低环境反光，适合夜间或高对比工作流。",
  },
  {
    id: "system",
    label: "跟随系统",
    description: "自动沿用系统配色模式，减少手动切换。",
  },
];

export const themePresets: ThemePresetDefinition[] = [
  {
    id: "default",
    label: "纸本台账",
    headline: "Editorial Ledger",
    description: "报刊式衬线标题、账页横线和黄铜点缀，像一本被认真装帧的工作手册。",
    mood: "最偏文档与审阅，白天使用最安静，适合分析、校对和长时间专注。",
    swatches: ["#F5F2EC", "#FCFBF8", "#C6922B", "#111215"],
  },
  {
    id: "graphite",
    label: "指挥矩阵",
    headline: "Executive Grid",
    description: "冷白网格、分区信息条和利落直角，更像一块管理驾驶舱面板。",
    mood: "最理性、最执行导向，适合桌面主工作台和强信息密度场景。",
    swatches: ["#F2F4F7", "#FBFCFE", "#CA8A04", "#0F172A"],
  },
  {
    id: "spruce",
    label: "森野工坊",
    headline: "Atelier Grove",
    description: "有机圆角、柔雾玻璃和松林绿影，像一间带自然气息的精致工作室。",
    mood: "最柔和、最有陪伴感，适合长时间挂着用，也最不像传统企业软件。",
    swatches: ["#EEF1EA", "#F8F7F1", "#2E7D5B", "#0F1714"],
  },
  {
    id: "oled",
    label: "夜航终端",
    headline: "OLED Command",
    description: "黑场、等宽标签、冷光描边和扫描线，更像夜间控制终端。",
    mood: "最强科技控制感，夜里最有氛围，和前三套属于完全不同的世界观。",
    swatches: ["#EDF1F6", "#F8FBFF", "#D4A24A", "#020406"],
  },
];

export function resolveThemeMode(value: string | undefined | null): ThemeMode {
  return value === "light" || value === "dark" || value === "system" ? value : "light";
}

export function resolveThemePreset(value: string | undefined | null): ThemePresetId {
  return themePresets.some((preset) => preset.id === value)
    ? (value as ThemePresetId)
    : "default";
}

export function applyUiTheme(
  ui: Partial<Pick<AppConfig["ui"], "theme" | "themePreset">> | undefined | null
) {
  if (typeof document === "undefined") {
    return;
  }

  const root = document.documentElement;
  const themeMode = resolveThemeMode(ui?.theme);
  const themePreset = resolveThemePreset(ui?.themePreset);
  const prefersDark =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const shouldUseDark =
    themeMode === "dark" || (themeMode === "system" && prefersDark);

  root.classList.toggle("dark", shouldUseDark);
  root.dataset.themePreset = themePreset;
  root.style.colorScheme = shouldUseDark ? "dark" : "light";
}
