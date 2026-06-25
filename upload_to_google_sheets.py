#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upload the latest Reddit demand CSV export to Google Sheets.

Behavior:
- Replace all values in the Latest tab with the current CSV contents.
- Append each data row to the History tab with a UTC run_date column.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import gspread
from google.oauth2.service_account import Credentials


CSV_FILENAME = "reddit_demand_data.csv"
LATEST_TAB_NAME = "Latest"
HISTORY_TAB_NAME = "History"
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def utc_run_date() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_csv_path() -> Path:
    return Path(__file__).resolve().with_name(CSV_FILENAME)


def load_csv_rows(csv_path: Path) -> List[List[str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    if not rows:
        raise ValueError(f"CSV file is empty: {csv_path}")

    return rows


def get_spreadsheet_client() -> gspread.Client:
    service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        raise EnvironmentError("Missing GOOGLE_SERVICE_ACCOUNT_JSON environment variable.")

    service_account_info = json.loads(service_account_json)
    credentials = Credentials.from_service_account_info(service_account_info, scopes=SHEETS_SCOPES)
    return gspread.authorize(credentials)


def get_spreadsheet_id() -> str:
    spreadsheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not spreadsheet_id:
        raise EnvironmentError("Missing GOOGLE_SHEET_ID environment variable.")
    return spreadsheet_id


def ensure_history_header(history_sheet: gspread.Worksheet, csv_headers: List[str]) -> None:
    expected_header = ["run_date"] + csv_headers
    existing_header = history_sheet.row_values(1)

    if not existing_header:
        history_sheet.update(range_name="A1", values=[expected_header])
    elif existing_header != expected_header:
        print("[GOOGLE SHEETS] Warning: History header differs from expected CSV header. Existing header was left unchanged.")


def update_latest_sheet(latest_sheet: gspread.Worksheet, rows: List[List[str]]) -> None:
    latest_sheet.clear()
    latest_sheet.update(range_name="A1", values=rows)


def append_history_rows(history_sheet: gspread.Worksheet, rows: List[List[str]], run_date: str) -> int:
    csv_headers = rows[0]
    data_rows = rows[1:]

    ensure_history_header(history_sheet, csv_headers)

    if not data_rows:
        return 0

    history_rows = [[run_date] + row for row in data_rows]
    history_sheet.append_rows(history_rows, value_input_option="RAW")
    return len(history_rows)


def main() -> None:
    csv_path = get_csv_path()
    rows = load_csv_rows(csv_path)
    run_date = utc_run_date()

    client = get_spreadsheet_client()
    spreadsheet = client.open_by_key(get_spreadsheet_id())
    latest_sheet = spreadsheet.worksheet(LATEST_TAB_NAME)
    history_sheet = spreadsheet.worksheet(HISTORY_TAB_NAME)

    update_latest_sheet(latest_sheet, rows)
    appended_count = append_history_rows(history_sheet, rows, run_date)

    print(f"[GOOGLE SHEETS] Spreadsheet: {spreadsheet.title}")
    print(f"[GOOGLE SHEETS] Latest rows written: {len(rows)}")
    print(f"[GOOGLE SHEETS] History rows appended: {appended_count}")
    print(f"[GOOGLE SHEETS] run_date: {run_date}")


if __name__ == "__main__":
    main()
