import sqlite3
from pathlib import Path

from openpyxl import load_workbook

from analysis.database_manager import DatabaseManager
from results.excel_exporter import ExcelExporter


def _prepare_results_db(tmp_path: Path) -> str:
    db_path = tmp_path / "analysis.db"
    manager = DatabaseManager(str(db_path))
    conn = manager.get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(results_data)")
    columns_info = cursor.fetchall()

    values = {}
    for _cid, name, col_type, *_rest in columns_info:
        if name == "id":
            continue
        upper_type = (col_type or "").upper()
        if name == "ticker":
            values[name] = "AAA"
        elif name == "date":
            values[name] = "2024-01-02"
        elif name == "candle_pattern":
            values[name] = 1
        elif name == "signal_strength":
            values[name] = 0.8
        elif name == "weekday":
            values[name] = 2
        elif "TEXT" in upper_type:
            values[name] = "0"
        elif "INTEGER" in upper_type:
            values[name] = 1
        else:  # REAL tai muu numeerinen
            values[name] = 1.0

    columns = ", ".join(values.keys())
    placeholders = ", ".join(["?"] * len(values))
    cursor.execute(
        f"INSERT INTO results_data ({columns}) VALUES ({placeholders})",
        list(values.values()),
    )
    conn.commit()
    return str(db_path)


def test_excel_exporter_writes_rows(tmp_path):
    db_path = _prepare_results_db(Path(tmp_path))
    exporter = ExcelExporter(db_path)

    output_file = Path(tmp_path) / "results.xlsx"
    success, message = exporter.export_to_excel(str(output_file))

    assert success, message
    assert output_file.exists()

    wb = load_workbook(output_file)
    ws = wb.active
    assert ws["A2"].value == "AAA"
    assert ws["C2"].value == 1
