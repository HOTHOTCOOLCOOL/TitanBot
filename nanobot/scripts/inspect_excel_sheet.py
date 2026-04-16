"""Standalone diagnostic script: inspect an Excel sheet's structure.

Usage (run from nanobot project root):
    python nanobot/scripts/inspect_excel_sheet.py \
        --file "D:\\OneDrive - VR Management (Shanghai) Co., Ltd\\Projects\\European Data Validation\\EURO DATA CUBE CONNECTION Sales & FF.xlsm" \
        --sheet "Occupancy Details" \
        --rows 15 --cols 12

Purpose:
    Before configuring the ExcelActuatorTool cron job, this script lets you
    peek at the raw structure of the target sheet (without triggering a refresh)
    to confirm column positions, date formats, and Pivot Table layout.

    This script reads via win32com (same as ExcelActuatorTool) so it reflects
    exactly the data that the tool will see.

Requires: pywin32 (pip install pywin32)
Platform: Windows only
"""

import argparse
import sys

def main():
    parser = argparse.ArgumentParser(
        description="Inspect Excel sheet structure via win32com (no refresh triggered)."
    )
    parser.add_argument("--file",  required=True, help="Absolute path to the .xlsm file")
    parser.add_argument("--sheet", default="Occupancy Details", help="Sheet name to inspect")
    parser.add_argument("--rows",  type=int, default=15, help="Max rows to display")
    parser.add_argument("--cols",  type=int, default=12, help="Max columns to display")
    parser.add_argument("--list-sheets", action="store_true", help="Only list all sheet names")
    args = parser.parse_args()

    try:
        import pythoncom
        import win32com.client
    except ImportError:
        print("ERROR: pywin32 not installed. Run: pip install pywin32", file=sys.stderr)
        sys.exit(1)

    pythoncom.CoInitialize()
    xl = win32com.client.Dispatch("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AskToUpdateLinks = False

    print(f"Opening: {args.file}")
    try:
        wb = xl.Workbooks.Open(args.file, UpdateLinks=False, ReadOnly=True)
    except Exception as e:
        print(f"ERROR: Could not open file — {e}", file=sys.stderr)
        xl.Quit()
        pythoncom.CoUninitialize()
        sys.exit(1)

    # List sheets
    sheet_names = [wb.Sheets(i + 1).Name for i in range(wb.Sheets.Count)]
    print(f"\nAvailable sheets ({len(sheet_names)}):")
    for i, name in enumerate(sheet_names, 1):
        marker = " ← target" if name == args.sheet else ""
        print(f"  {i:2d}. {name}{marker}")

    if args.list_sheets:
        wb.Close(False)
        xl.Quit()
        pythoncom.CoUninitialize()
        return

    # Inspect target sheet
    if args.sheet not in sheet_names:
        print(f"\nERROR: Sheet '{args.sheet}' not found.")
        wb.Close(False)
        xl.Quit()
        pythoncom.CoUninitialize()
        sys.exit(1)

    ws = wb.Sheets(args.sheet)
    used_range = ws.UsedRange
    total_rows = used_range.Rows.Count
    total_cols = used_range.Columns.Count

    print(f"\nSheet: '{args.sheet}'")
    print(f"Used range: {total_rows} rows × {total_cols} cols")
    print(f"Displaying first {min(args.rows, total_rows)} rows × {min(args.cols, total_cols)} cols:\n")

    # Build header row
    col_indices = list(range(1, min(args.cols, total_cols) + 1))
    col_labels  = [f"Col{c}" for c in col_indices]
    header = " | ".join(f"{lbl:>20}" for lbl in col_labels)
    print(f"{'Row':>4} | {header}")
    print("-" * (4 + 3 + len(header)))

    for r in range(1, min(args.rows, total_rows) + 1):
        row_vals = []
        for c in col_indices:
            v = ws.Cells(r, c).Value
            if v is None:
                row_vals.append("")
            else:
                s = str(v)
                # Truncate long values for display
                row_vals.append(s[:20] if len(s) <= 20 else s[:17] + "...")
        row_str = " | ".join(f"{v:>20}" for v in row_vals)
        print(f"{r:>4} | {row_str}")

    # Look for "Gross Sales" in the sheet
    print(f"\nSearching for 'Gross Sales' in first {total_rows} rows...")
    found = False
    for r in range(1, total_rows + 1):
        for c in range(1, min(total_cols + 1, 5)):  # Check first 4 cols for labels
            v = ws.Cells(r, c).Value
            if v and "gross" in str(v).lower() and "sales" in str(v).lower():
                print(f"  ✅ Found 'Gross Sales' at Row {r}, Col {c}: '{v}'")
                found = True
    if not found:
        print("  ⚠️  'Gross Sales' string not found in first 4 columns.")
        print("  Tip: It may be in a different column, or use a different label.")

    wb.Close(False)
    xl.Quit()
    pythoncom.CoUninitialize()
    print("\nDone.")


if __name__ == "__main__":
    main()
