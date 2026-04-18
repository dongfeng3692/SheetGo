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
    swatches: ["#F2F4F7", "#FBFCFE", "#4A7AB5", "#0F172A"],
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
    swatches: ["#EDF1F6", "#F8FBFF", "#527FFF", "#020406"],
  },
  {
    id: "rosewood",
    label: "檀木书房",
    headline: "Rosewood Study",
    description: "玫瑰木纹桌面、暖色皮革和铜件装饰，像一间收藏家的私人书房。",
    mood: "沉稳温润、书香气息，适合处理重要文档和长时间阅读型工作。",
    swatches: ["#F4F1EF", "#FAF8F6", "#A05050", "#100A0A"],
  },
  {
    id: "inkstone",
    label: "墨石",
    headline: "Inkstone Slate",
    description: "砚台般的墨蓝、宣纸留白和靛青点缀，取意东方水墨。",
    mood: "清雅内敛、文人气质，适合创意型和思考型工作流。",
    swatches: ["#F1F2F6", "#F9F9FC", "#5C5EA0", "#0A0A14"],
  },
  {
    id: "dusk",
    label: "暮霞",
    headline: "Dusk Glow",
    description: "赤陶暖橙、焦糖高光和暮色灰调，像黄昏时分的窗边工位。",
    mood: "温暖有活力但不刺眼，适合白天日常使用，给人踏实的工作节奏感。",
    swatches: ["#F5F2EF", "#FAF8F5", "#C06A3A", "#120E0C"],
  },
  {
    id: "verdigris",
    label: "铜绿",
    headline: "Verdigris",
    description: "巴黎老铜屋顶的氧化绿锈、石板灰和亚麻白，时间沉淀的矿物质感。",
    mood: "沉静而有底蕴，适合长时间审阅和深度分析，有老派工艺品的安心感。",
    swatches: ["#F0F2F1", "#F8FAF9", "#4E8C7F", "#0C100F"],
  },
  {
    id: "hoarfrost",
    label: "霜岩",
    headline: "Hoarfrost",
    description: "北极冻土的黑石上覆着冰晶，极地清晨的锐利冷白与灰蓝。",
    mood: "极致清冷、极度专注，适合需要高度集中注意力的场景，像呼吸到冰空气。",
    swatches: ["#F4F6F8", "#FAFBFC", "#6B9BAE", "#080C10"],
  },
  {
    id: "cinnabar",
    label: "朱砂",
    headline: "Cinnabar",
    description: "宣纸留白、墨色线条和一方朱红印章，取意中国画最精炼的色彩关系。",
    mood: "端庄大气、有仪式感，适合正式场合和对外展示，不媚不俗。",
    swatches: ["#F4F2F0", "#FAF8F6", "#BF3B30", "#120C0A"],
  },
  {
    id: "abyss",
    label: "深渊",
    headline: "Abyss",
    description: "两千米深海的幽蓝黑水里，生物发出的荧光青色——安静、神秘、活着。",
    mood: "幽深但不压抑，像潜水时的专注感，适合夜间深度工作和暗室环境。",
    swatches: ["#EFF2F2", "#F8FAFA", "#2A9D8F", "#060A0C"],
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
