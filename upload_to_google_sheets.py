#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upload Novel Bridge scraper outputs to Google Sheets.

Phase 1 behavior:
- Append raw_discussions.csv rows into Raw_Discussions.
- If reddit_demand_data.csv exists, refresh Latest and append to History.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import gspread
from google.oauth2.service_account import Credentials


RAW_CSV_FILENAME = "raw_discussions.csv"
AGGREGATE_CSV_FILENAME = "reddit_demand_data.csv"
RAW_TAB_NAME = "Raw_Discussions"
LATEST_TAB_NAME = "Latest"
HISTORY_TAB_NAME = "History"
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def utc_run_date() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_csv_path(filename: str) -> Path:
    return Path(__file__).resolve().with_name(filename)


def load_csv_rows_if_present(csv_path: Path) -> Optional[List[List[str]]]:
    if not csv_path.exists():
        return None

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    if not rows:
        return None

    return rows


def load_required_csv_rows(csv_path: Path) -> List[List[str]]:
    rows = load_csv_rows_if_present(csv_path)
    if rows is None:
        raise FileNotFoundError(f"CSV file not found or empty: {csv_path}")
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


def ensure_sheet_header(sheet: gspread.Worksheet, expected_header: List[str], label: str) -> None:
    existing_header = sheet.row_values(1)

    if not existing_header:
        sheet.update(range_name="A1", values=[expected_header])
    elif existing_header != expected_header:
        print(f"[GOOGLE SHEETS] Warning: {label} header differs from expected CSV header. Existing header was left unchanged.")


def append_csv_rows(sheet: gspread.Worksheet, rows: List[List[str]]) -> int:
    header = rows[0]
    data_rows = rows[1:]

    ensure_sheet_header(sheet, header, sheet.title)

    if not data_rows:
        return 0

    sheet.append_rows(data_rows, value_input_option="RAW")
    return len(data_rows)


def ensure_history_header(history_sheet: gspread.Worksheet, csv_headers: List[str]) -> None:
    ensure_sheet_header(history_sheet, ["run_date"] + csv_headers, "History")


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
    raw_rows = load_required_csv_rows(get_csv_path(RAW_CSV_FILENAME))
    aggregate_rows = load_csv_rows_if_present(get_csv_path(AGGREGATE_CSV_FILENAME))
    upload_run_date = utc_run_date()

    client = get_spreadsheet_client()
    spreadsheet = client.open_by_key(get_spreadsheet_id())

    raw_sheet = spreadsheet.worksheet(RAW_TAB_NAME)
    raw_appended_count = append_csv_rows(raw_sheet, raw_rows)

    print(f"[GOOGLE SHEETS] Spreadsheet: {spreadsheet.title}")
    print(f"[GOOGLE SHEETS] Raw_Discussions rows appended: {raw_appended_count}")

    if aggregate_rows is not None:
        latest_sheet = spreadsheet.worksheet(LATEST_TAB_NAME)
        history_sheet = spreadsheet.worksheet(HISTORY_TAB_NAME)

        update_latest_sheet(latest_sheet, aggregate_rows)
        history_appended_count = append_history_rows(history_sheet, aggregate_rows, upload_run_date)

        print(f"[GOOGLE SHEETS] Aggregate CSV produced: yes")
        print(f"[GOOGLE SHEETS] Latest rows written: {len(aggregate_rows)}")
        print(f"[GOOGLE SHEETS] History rows appended: {history_appended_count}")
    else:
        print(f"[GOOGLE SHEETS] Aggregate CSV produced: no")

    print(f"[GOOGLE SHEETS] upload_run_date: {upload_run_date}")


if __name__ == "__main__":
    main()
