import type { Component } from "solid-js";

interface Props {
  before: (string | number | null)[][];
  after: (string | number | null)[][];
  highlightCells?: { row: number; col: number; type: "added" | "removed" | "modified" }[];
  onClose?: () => void;
}

const DiffView: Component<Props> = (props) => {
  const maxRows = () => Math.max(props.before.length, props.after.length);
  const maxCols = () => {
    let cols = 0;
    for (let i = 0; i < maxRows(); i++) {
      const b = Array.isArray(props.before[i]) ? props.before[i].length : 0;
      const a = Array.isArray(props.after[i]) ? props.after[i].length : 0;
      cols = Math.max(cols, b, a);
    }
    return cols;
  };

  const getCellType = (row: number, col: number, isAfter: boolean) => {
    const hl = props.highlightCells?.find((c) => c.row === row && c.col === col);
    if (hl) {
      if (isAfter && hl.type === "added") return "bg-green-100 dark:bg-green-900/40";
      if (!isAfter && hl.type === "removed") return "bg-red-100 dark:bg-red-900/40";
      return "bg-yellow-100 dark:bg-yellow-900/40";
    }
    const b = props.before[row]?.[col] ?? "";
    const a = props.after[row]?.[col] ?? "";
    if (b !== a) {
      if (isAfter) return "bg-green-50 dark:bg-green-900/20";
      return "bg-red-50 dark:bg-red-900/20";
    }
    return "";
  };

  return (
    <div class="absolute inset-0 bg-[var(--bg-primary)]/95 backdrop-blur-sm z-20 flex flex-col border rounded shadow-lg">
      <div class="px-4 py-2 border-b flex items-center justify-between bg-[var(--bg-secondary)]">
        <span class="text-sm font-medium text-[var(--text-primary)]">差异对比</span>
        {props.onClose && (
          <button
            class="text-xs px-2 py-1 rounded border hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)]"
            onClick={props.onClose}
          >
            关闭
          </button>
        )}
      </div>
      <div class="flex-1 overflow-auto p-4">
        <div class="grid grid-cols-2 gap-4 h-full">
          <div class="overflow-auto border rounded">
            <div class="text-xs font-medium px-3 py-1 border-b bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
              修改前
            </div>
            <table class="w-full text-xs">
              <tbody>
                {Array.from({ length: maxRows() }).map((_, r) => (
                  <tr>
                    {Array.from({ length: maxCols() }).map((__, c) => (
                      <td
                        class={`excel-cell min-w-[60px] max-w-[200px] ${getCellType(r, c, false)}`}
                        title={String(props.before[r]?.[c] ?? "")}
                      >
                        {String(props.before[r]?.[c] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div class="overflow-auto border rounded">
            <div class="text-xs font-medium px-3 py-1 border-b bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
              修改后
            </div>
            <table class="w-full text-xs">
              <tbody>
                {Array.from({ length: maxRows() }).map((_, r) => (
                  <tr>
                    {Array.from({ length: maxCols() }).map((__, c) => (
                      <td
                        class={`excel-cell min-w-[60px] max-w-[200px] ${getCellType(r, c, true)}`}
                        title={String(props.after[r]?.[c] ?? "")}
                      >
                        {String(props.after[r]?.[c] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DiffView;
