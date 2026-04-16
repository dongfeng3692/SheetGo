import * as XLSX from "xlsx";
import type { IWorkbookData, ICellData, IWorksheetData } from "@univerjs/presets";

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
