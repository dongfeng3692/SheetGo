import * as XLSX from "xlsx";
import type { IWorkbookData, ICellData, IWorksheetData } from "@univerjs/presets";

export type WorkbookEditValue = string | number | boolean | null;

export interface WorkbookCellEdit {
  sheet: string;
  cell: string;
  value: WorkbookEditValue;
}

function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

/**
 * Convert xlsx bytes (base64) into Univer's IWorkbookData format.
 * No row limit — Univer's canvas engine handles large datasets.
 */
export function parseExcelToUniver(b64: string): IWorkbookData {
  const bytes = base64ToBytes(b64);
  const workbook = XLSX.read(bytes, { type: "array" });

  const sheets: Record<string, Partial<IWorksheetData>> = {};
  const sheetOrder: string[] = [];

  for (const name of workbook.SheetNames) {
    const ws = workbook.Sheets[name];
    const ref = ws["!ref"];
    let rowCount = 0;
    let colCount = 0;

    if (ref) {
      const range = XLSX.utils.decode_range(ref);
      rowCount = range.e.r + 1;
      colCount = range.e.c + 1;
    }

    // Build cellData in Univer's sparse matrix format: { [row]: { [col]: ICellData } }
    const cellData: Record<number, Record<number, ICellData>> = {};

    if (ref) {
      const range = XLSX.utils.decode_range(ref);
      for (let r = range.s.r; r <= range.e.r; r++) {
        for (let c = range.s.c; c <= range.e.c; c++) {
          const addr = XLSX.utils.encode_cell({ r, c });
          const cell = ws[addr];
          if (cell == null) continue;

          let value: string | number | boolean | null = null;
          if (cell.v !== undefined && cell.v !== null) {
            value = cell.v as string | number | boolean;
          }

          if (value === null) continue;

          const cellObj: ICellData = { v: value };

          // Preserve formula if present
          if (cell.f) {
            cellObj.f = `=${cell.f}`;
          }

          if (!cellData[r]) cellData[r] = {};
          cellData[r][c] = cellObj;
        }
      }
    }

    const sheetId = `sheet-${name}`;
    sheets[sheetId] = {
      id: sheetId,
      name,
      rowCount: Math.max(rowCount, 1),
      columnCount: Math.max(colCount, 1),
      cellData,
      // Defaults
      tabColor: "",
      hidden: 0,
      freeze: { xSplit: 0, ySplit: 0, startRow: 0, startColumn: 0 },
      zoomRatio: 1,
      scrollTop: 0,
      scrollLeft: 0,
      defaultColumnWidth: 93,
      defaultRowHeight: 27,
      mergeData: [],
      rowData: {},
      columnData: {},
      rowHeader: { width: 46 },
      columnHeader: { height: 20 },
      showGridlines: 1,
      rightToLeft: 0,
    };
    sheetOrder.push(sheetId);
  }

  return {
    id: "wb",
    name: "Workbook",
    appVersion: "0.20.1",
    locale: "zhCN" as any,
    styles: {},
    sheetOrder,
    sheets,
  };
}

/** Extract sheet names from the workbook data */
export function getSheetNames(data: IWorkbookData): string[] {
  return data.sheetOrder.map((id) => (data.sheets[id] as IWorksheetData).name);
}

function getSheetsByName(data: IWorkbookData): Map<string, IWorksheetData> {
  const map = new Map<string, IWorksheetData>();
  for (const sheetId of data.sheetOrder) {
    const sheet = data.sheets[sheetId] as IWorksheetData | undefined;
    if (sheet?.name) {
      map.set(sheet.name, sheet);
    }
  }
  return map;
}

function normalizeCellValue(cell: ICellData | null | undefined): WorkbookEditValue {
  if (!cell) {
    return null;
  }

  const formula = typeof cell.f === "string" ? cell.f.trim() : "";
  if (formula) {
    return formula.startsWith("=") ? formula : `=${formula}`;
  }

  if (cell.v === undefined || cell.v === null) {
    return null;
  }

  if (
    typeof cell.v === "string" ||
    typeof cell.v === "number" ||
    typeof cell.v === "boolean"
  ) {
    return cell.v;
  }

  return String(cell.v);
}

function cellValuesEqual(left: WorkbookEditValue, right: WorkbookEditValue): boolean {
  return left === right;
}

export function buildWorkbookCellEdits(
  original: IWorkbookData,
  current: IWorkbookData
): WorkbookCellEdit[] {
  const originalSheets = getSheetsByName(original);
  const currentSheets = getSheetsByName(current);

  if (originalSheets.size !== currentSheets.size) {
    throw new Error("暂不支持新增或删除工作表，请只修改现有单元格内容。");
  }

  for (const sheetName of originalSheets.keys()) {
    if (!currentSheets.has(sheetName)) {
      throw new Error("暂不支持重命名工作表，请只修改现有单元格内容。");
    }
  }

  const edits: WorkbookCellEdit[] = [];

  for (const [sheetName, originalSheet] of originalSheets.entries()) {
    const currentSheet = currentSheets.get(sheetName);
    if (!currentSheet) {
      continue;
    }

    const originalRows = (originalSheet.cellData ?? {}) as Record<number, Record<number, ICellData>>;
    const currentRows = (currentSheet.cellData ?? {}) as Record<number, Record<number, ICellData>>;

    const rowIndexes = new Set<number>([
      ...Object.keys(originalRows).map((value) => Number(value)),
      ...Object.keys(currentRows).map((value) => Number(value)),
    ]);

    for (const rowIndex of [...rowIndexes].sort((left, right) => left - right)) {
      const originalCols = originalRows[rowIndex] ?? {};
      const currentCols = currentRows[rowIndex] ?? {};
      const colIndexes = new Set<number>([
        ...Object.keys(originalCols).map((value) => Number(value)),
        ...Object.keys(currentCols).map((value) => Number(value)),
      ]);

      for (const colIndex of [...colIndexes].sort((left, right) => left - right)) {
        const previousValue = normalizeCellValue(originalCols[colIndex]);
        const nextValue = normalizeCellValue(currentCols[colIndex]);

        if (cellValuesEqual(previousValue, nextValue)) {
          continue;
        }

        edits.push({
          sheet: sheetName,
          cell: XLSX.utils.encode_cell({ r: rowIndex, c: colIndex }),
          value: nextValue,
        });
      }
    }
  }

  return edits;
}
