import sys

import google_sheets


def main():
    try:
        result = google_sheets.verify_connection(
            create_if_missing_id=True,
            actor="local-script",
        )
    except Exception as exc:
        print(f"Google Sheets check failed: {exc}")
        raise SystemExit(1) from exc

    print("Google Sheets check passed.")
    print(f"Spreadsheet: {result['spreadsheet_title']}")
    print(f"Spreadsheet ID: {result['spreadsheet_id']}")
    print(f"Worksheet: {result['worksheet_title']}")
    print(f"Updated range: {result['updated_range']}")
    print(f"Spreadsheet URL: {result['spreadsheet_url']}")

    if result["created_spreadsheet"]:
        print("A new test spreadsheet was created because GOOGLE_SHEETS_SPREADSHEET_ID is not set.")


if __name__ == "__main__":
    main()
