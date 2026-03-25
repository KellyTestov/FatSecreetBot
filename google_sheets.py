import logging
import json
import threading
from datetime import date, datetime, timezone

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_STATUS_WRITE_LOCK = threading.Lock()


class GoogleSheetsConfigError(RuntimeError):
    """Raised when Google Sheets is not configured correctly."""


def _raise_friendly_http_error(exc: HttpError):
    details = getattr(exc, "error_details", None) or []
    status = getattr(exc.resp, "status", None)

    for item in details:
        if item.get("reason") == "SERVICE_DISABLED":
            activation_url = item.get("metadata", {}).get("activationUrl")
            raise RuntimeError(
                "Google Sheets API выключен в проекте Google Cloud. "
                f"Включи его здесь: {activation_url}"
            ) from exc

    if status == 404:
        raise RuntimeError(
            "Таблица не найдена. Проверь GOOGLE_SHEETS_SPREADSHEET_ID."
        ) from exc
    if status == 403:
        raise RuntimeError(
            "Нет доступа к таблице. Расшарь её на service account."
        ) from exc
    raise exc


def _service():
    if config.GOOGLE_SERVICE_ACCOUNT_JSON:
        creds = Credentials.from_service_account_info(
            json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON),
            scopes=SCOPES,
        )
        return build("sheets", "v4", credentials=creds, cache_discovery=False)

    key_file = config.GOOGLE_SERVICE_ACCOUNT_FILE
    if not key_file.exists():
        raise GoogleSheetsConfigError(
            f"Не найден JSON-ключ service account: {key_file}"
        )

    creds = Credentials.from_service_account_file(str(key_file), scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _sheet_range(sheet_title: str, a1_range: str) -> str:
    return f"'{sheet_title}'!{a1_range}"


def get_spreadsheet(spreadsheet_id: str) -> dict:
    try:
        return (
            _service()
            .spreadsheets()
            .get(spreadsheetId=spreadsheet_id)
            .execute()
        )
    except HttpError as exc:
        _raise_friendly_http_error(exc)


def create_spreadsheet(title: str) -> dict:
    body = {
        "properties": {"title": title},
        "sheets": [{"properties": {"title": config.GOOGLE_SHEETS_WORKSHEET}}],
    }
    try:
        return _service().spreadsheets().create(body=body).execute()
    except HttpError as exc:
        _raise_friendly_http_error(exc)


def ensure_worksheet(spreadsheet_id: str, sheet_title: str) -> str:
    spreadsheet = get_spreadsheet(spreadsheet_id)
    for sheet in spreadsheet.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == sheet_title:
            return sheet_title

    body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": sheet_title,
                    }
                }
            }
        ]
    }
    try:
        _service().spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body,
        ).execute()
    except HttpError as exc:
        _raise_friendly_http_error(exc)
    return sheet_title


def ensure_header(spreadsheet_id: str, sheet_title: str):
    service = _service()
    try:
        existing = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range=_sheet_range(sheet_title, "A1:D1"),
            )
            .execute()
        )
    except HttpError as exc:
        _raise_friendly_http_error(exc)
    values = existing.get("values", [])
    if values:
        return

    try:
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=_sheet_range(sheet_title, "A1"),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [["timestamp_utc", "source", "actor", "status"]]},
        ).execute()
    except HttpError as exc:
        _raise_friendly_http_error(exc)


def append_test_row(spreadsheet_id: str, sheet_title: str, actor: str) -> dict:
    ensure_worksheet(spreadsheet_id, sheet_title)
    ensure_header(spreadsheet_id, sheet_title)

    row = [
        datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "fatsecret-bot",
        actor,
        "ok",
    ]

    try:
        return (
            _service()
            .spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=_sheet_range(sheet_title, "A1"),
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            )
            .execute()
        )
    except HttpError as exc:
        _raise_friendly_http_error(exc)


def verify_connection(create_if_missing_id: bool = False, actor: str = "manual") -> dict:
    logger.info(f"Google Sheets: проверка подключения, инициатор {actor}")
    spreadsheet_id = config.GOOGLE_SHEETS_SPREADSHEET_ID
    created_spreadsheet = False

    if not spreadsheet_id:
        if not create_if_missing_id:
            raise GoogleSheetsConfigError(
                "Не задан GOOGLE_SHEETS_SPREADSHEET_ID."
            )
        created = create_spreadsheet("FatSecret Bot Test")
        spreadsheet_id = created["spreadsheetId"]
        created_spreadsheet = True

    spreadsheet = get_spreadsheet(spreadsheet_id)
    spreadsheet_title = spreadsheet.get("properties", {}).get("title", "Untitled")
    worksheet_title = ensure_worksheet(spreadsheet_id, config.GOOGLE_SHEETS_WORKSHEET)
    append_result = append_test_row(spreadsheet_id, worksheet_title, actor)
    logger.info(
        "Google Sheets: подключение проверено успешно (%s / %s, диапазон %s)",
        spreadsheet_title,
        worksheet_title,
        append_result.get("updates", {}).get("updatedRange"),
    )

    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_title": spreadsheet_title,
        "worksheet_title": worksheet_title,
        "created_spreadsheet": created_spreadsheet,
        "updated_range": append_result.get("updates", {}).get("updatedRange"),
        "updated_rows": append_result.get("updates", {}).get("updatedRows"),
        "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
    }


STATUS_HEADERS = [
    "Дата",
    "Вес (кг)",
    "Калории",
    "Белок (г)",
    "Углеводы (г)",
    "Клетчатка (г)",
    "Жиры (г)",
    "Аппетит / ощущения",
    "Тирзетта",
    "Зал",
    "Бассейн",
    "Кардио",
]

ZONE_GREEN = {"red": 0.82, "green": 0.93, "blue": 0.84}
ZONE_YELLOW = {"red": 0.99, "green": 0.93, "blue": 0.67}
ZONE_RED = {"red": 0.96, "green": 0.80, "blue": 0.80}


def _status_spreadsheet_id() -> str:
    if not config.GOOGLE_SHEETS_SPREADSHEET_ID:
        raise GoogleSheetsConfigError("Не задан GOOGLE_SHEETS_SPREADSHEET_ID.")
    return config.GOOGLE_SHEETS_SPREADSHEET_ID


def _status_date_formats(target_date: date) -> list[str]:
    return [
        target_date.strftime("%d.%m"),
        target_date.strftime("%d.%m.%Y"),
        target_date.isoformat(),
    ]


def _status_default_row(target_date: date) -> list[str]:
    return [
        target_date.strftime("%d.%m"),
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ]


def _status_values():
    try:
        return (
            _service()
            .spreadsheets()
            .values()
            .get(
                spreadsheetId=_status_spreadsheet_id(),
                range=_sheet_range(config.STATUS_WORKSHEET, "A1:L1000"),
            )
            .execute()
            .get("values", [])
        )
    except HttpError as exc:
        _raise_friendly_http_error(exc)


def _status_sheet_id() -> int:
    spreadsheet = get_spreadsheet(_status_spreadsheet_id())
    for sheet in spreadsheet.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == config.STATUS_WORKSHEET:
            return props["sheetId"]
    raise RuntimeError(f"Лист {config.STATUS_WORKSHEET} не найден")


def _status_row_height(row_index: int) -> int | None:
    try:
        spreadsheet = (
            _service()
            .spreadsheets()
            .get(
                spreadsheetId=_status_spreadsheet_id(),
                ranges=[_sheet_range(config.STATUS_WORKSHEET, f"A{row_index}:A{row_index}")],
                includeGridData=False,
                fields="sheets(properties.sheetId,data.rowMetadata.pixelSize)",
            )
            .execute()
        )
    except HttpError as exc:
        _raise_friendly_http_error(exc)

    for sheet in spreadsheet.get("sheets", []):
        for data in sheet.get("data", []):
            row_metadata = data.get("rowMetadata", [])
            if row_metadata:
                return row_metadata[0].get("pixelSize")
    return None


def ensure_status_sheet():
    spreadsheet_id = _status_spreadsheet_id()
    ensure_worksheet(spreadsheet_id, config.STATUS_WORKSHEET)
    values = _status_values()
    if values:
        return
    logger.info(f"Google Sheets: создаю заголовок листа Status в таблице {spreadsheet_id}")

    try:
        _service().spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=_sheet_range(config.STATUS_WORKSHEET, "A1:L1"),
            valueInputOption="RAW",
            body={"values": [STATUS_HEADERS]},
        ).execute()
    except HttpError as exc:
        _raise_friendly_http_error(exc)


def _status_row_index(target_date: date) -> int:
    ensure_status_sheet()
    values = _status_values()
    wanted = set(_status_date_formats(target_date))

    for index, row in enumerate(values[1:], start=2):
        cell = row[0].strip() if row and row[0] else ""
        if cell in wanted:
            return index
    return 0


def _status_row_values(row_index: int, target_date: date) -> list[str]:
    values = _status_values()
    if row_index <= len(values):
        row = list(values[row_index - 1])
    else:
        row = []

    target_len = len(STATUS_HEADERS)
    if len(row) < target_len:
        row.extend([""] * (target_len - len(row)))
    if not row[0]:
        row[0] = target_date.strftime("%d.%m")

    return row[:target_len]


def _header_index_map() -> dict[str, int]:
    ensure_status_sheet()
    values = _status_values()
    header = values[0] if values else STATUS_HEADERS
    mapping: dict[str, int] = {}
    for index, name in enumerate(header):
        mapping[name] = index
    return mapping


def _status_metric_value(target_date: date, header: str) -> float | None:
    row_index = _status_row_index(target_date)
    if row_index == 0:
        return None

    row_values = _status_row_values(row_index, target_date)
    header_map = _header_index_map()
    raw_value = row_values[header_map[header]].strip()
    if not raw_value:
        return None

    try:
        return float(raw_value.replace(",", "."))
    except ValueError:
        return None


def _metric_zone(metric: str, value: float) -> str:
    if metric == "protein":
        if value < 100:
            return "red"
        if value < 120:
            return "yellow"
        return "green"

    if metric == "carbs":
        if value < 90 or value > 210:
            return "red"
        if value <= 160:
            return "green"
        return "yellow"

    if metric == "fiber":
        if value < 10:
            return "red"
        if value < 18:
            return "yellow"
        return "green"

    if metric == "fat":
        if value < 40 or value > 80:
            return "red"
        if value <= 65:
            return "green"
        return "yellow"

    raise RuntimeError(f"Неизвестная метрика для зоны: {metric}")


def _zone_color(metric: str, value: float) -> dict[str, float] | None:
    zone = _metric_zone(metric, value)
    if zone == "red":
        return ZONE_RED
    if zone == "yellow":
        return ZONE_YELLOW
    # Зеленую зону не красим: оставляем текущий фон ячейки без изменений.
    return None


def _zone_label(metric: str, value: float) -> str:
    zone = _metric_zone(metric, value)
    if zone == "green":
        return "зелёная"
    if zone == "yellow":
        return "жёлтая"
    return "красная"


def _parse_float_or_none(raw_value: str) -> float | None:
    cleaned = (raw_value or "").strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_status_date_cell(cell: str, start: date, end: date) -> date | None:
    raw = (cell or "").strip()
    if not raw:
        return None

    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            if start <= parsed <= end:
                return parsed
            return None
        except ValueError:
            pass

    # Формат без года (например "24.03"): подбираем год, чтобы дата попала в диапазон.
    try:
        day = int(raw.split(".")[0])
        month = int(raw.split(".")[1])
    except (ValueError, IndexError):
        return None

    for year in {start.year - 1, start.year, end.year, end.year + 1}:
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if start <= candidate <= end:
            return candidate
    return None


def _format_status_row(row_index: int):
    sheet_id = _status_sheet_id()
    source_row_index = max(1, row_index - 1)
    source_row_height = _status_row_height(source_row_index)
    requests = []

    if row_index > 2:
        requests.append(
            {
                "copyPaste": {
                    "source": {
                        "sheetId": sheet_id,
                        "startRowIndex": source_row_index - 1,
                        "endRowIndex": source_row_index,
                        "startColumnIndex": 0,
                        "endColumnIndex": 12,
                    },
                    "destination": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_index - 1,
                        "endRowIndex": row_index,
                        "startColumnIndex": 0,
                        "endColumnIndex": 12,
                    },
                    "pasteType": "PASTE_NORMAL",
                    "pasteOrientation": "NORMAL",
                }
            }
        )

    if source_row_height:
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_index - 1,
                        "endIndex": row_index,
                    },
                    "properties": {
                        "pixelSize": source_row_height,
                    },
                    "fields": "pixelSize",
                }
            }
        )

    border_style = {
        "style": "SOLID",
        "colorStyle": {"rgbColor": {"red": 0, "green": 0, "blue": 0}},
    }
    requests.append(
        {
            "updateBorders": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row_index - 1,
                    "endRowIndex": row_index,
                    "startColumnIndex": 0,
                    "endColumnIndex": 12,
                },
                "top": border_style,
                "bottom": border_style,
                "left": border_style,
                "right": border_style,
                "innerHorizontal": border_style,
                "innerVertical": border_style,
            }
        }
    )

    try:
        if requests:
            logger.info(f"Google Sheets: копирую оформление на строку Status #{row_index}")
            _service().spreadsheets().batchUpdate(
                spreadsheetId=_status_spreadsheet_id(),
                body={"requests": requests},
            ).execute()
    except HttpError as exc:
        _raise_friendly_http_error(exc)


def upsert_status_row(target_date: date, updates: dict[str, str]) -> dict:
    with _STATUS_WRITE_LOCK:
        spreadsheet_id = _status_spreadsheet_id()
        ensure_status_sheet()
        row_index = _status_row_index(target_date)
        is_new_row = row_index == 0

        if is_new_row:
            row_index = len(_status_values()) + 1
            row_values = _status_default_row(target_date)
            _format_status_row(row_index)
        else:
            row_values = _status_row_values(row_index, target_date)

        logger.info(
            "Google Sheets: обновляю лист Status за %s (строка %s, новая=%s, поля=%s)",
            target_date.strftime("%d.%m.%Y"),
            row_index,
            "да" if is_new_row else "нет",
            ", ".join(updates.keys()),
        )

        header_map = _header_index_map()
        for header, value in updates.items():
            if header not in header_map:
                raise RuntimeError(f"Неизвестная колонка Status: {header}")
            row_values[header_map[header]] = value

        try:
            result = (
                _service()
                .spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=_sheet_range(config.STATUS_WORKSHEET, f"A{row_index}:L{row_index}"),
                    valueInputOption="RAW",
                    body={"values": [row_values]},
                )
                .execute()
            )
            logger.info(
                "Google Sheets: строка Status за %s сохранена (%s)",
                target_date.strftime("%d.%m.%Y"),
                result.get("updatedRange"),
            )
            return result
        except HttpError as exc:
            _raise_friendly_http_error(exc)


def record_daily_status(target_date: date, totals: dict) -> dict:
    result = upsert_status_row(
        target_date,
        {
            "Дата": target_date.strftime("%d.%m"),
            "Калории": f"{totals.get('calories', 0):.0f}",
            "Белок (г)": f"{totals.get('protein', 0):.2f}",
            "Углеводы (г)": f"{totals.get('carbs', 0):.2f}",
            "Клетчатка (г)": f"{totals.get('fiber', 0):.2f}",
            "Жиры (г)": f"{totals.get('fat', 0):.2f}",
        },
    )
    # Валидация после записи: иногда UI-таблица может "съесть" часть обновления.
    # Если числовые поля не появились, делаем точечный повтор по C:G.
    row = get_status_rows_between(target_date, target_date)
    row = row[0] if row else {}
    nutrition_headers = ["Калории", "Белок (г)", "Углеводы (г)", "Клетчатка (г)", "Жиры (г)"]
    missing = [h for h in nutrition_headers if not str(row.get(h, "")).strip()]
    if missing:
        logger.warning(
            "Google Sheets: после sync за %s не заполнены поля: %s. Повторяю точечную запись C:G.",
            target_date.strftime("%d.%m.%Y"),
            ", ".join(missing),
        )
        _force_update_daily_nutrition_cells(target_date, totals)
    return result


def _force_update_daily_nutrition_cells(target_date: date, totals: dict) -> dict:
    row_index = _status_row_index(target_date)
    if row_index == 0:
        raise RuntimeError(f"Строка Status за {target_date.strftime('%d.%m.%Y')} не найдена для повторной записи")

    payload = [[
        f"{totals.get('calories', 0):.0f}",
        f"{totals.get('protein', 0):.2f}",
        f"{totals.get('carbs', 0):.2f}",
        f"{totals.get('fiber', 0):.2f}",
        f"{totals.get('fat', 0):.2f}",
    ]]
    try:
        result = (
            _service()
            .spreadsheets()
            .values()
            .update(
                spreadsheetId=_status_spreadsheet_id(),
                range=_sheet_range(config.STATUS_WORKSHEET, f"C{row_index}:G{row_index}"),
                valueInputOption="RAW",
                body={"values": payload},
            )
            .execute()
        )
        logger.info(
            "Google Sheets: точечная запись C:G выполнена за %s (%s)",
            target_date.strftime("%d.%m.%Y"),
            result.get("updatedRange"),
        )
        return result
    except HttpError as exc:
        _raise_friendly_http_error(exc)


def record_appetite(target_date: date, text: str) -> dict:
    return upsert_status_row(target_date, {"Аппетит / ощущения": text})


def record_weight(target_date: date, weight: float) -> dict:
    return upsert_status_row(target_date, {"Вес (кг)": f"{weight:.1f}"})


def record_tirz(target_date: date, value: str) -> dict:
    return upsert_status_row(target_date, {"Тирзетта": value})


def record_activity(target_date: date, *, gym: str | None = None, pool: str | None = None, cardio: str | None = None) -> dict:
    updates: dict[str, str] = {}
    if gym is not None:
        updates["Зал"] = gym
    if pool is not None:
        updates["Бассейн"] = pool
    if cardio is not None:
        updates["Кардио"] = cardio
    return upsert_status_row(target_date, updates)


def color_status_metric_zones(target_date: date) -> dict[str, str]:
    row_index = _status_row_index(target_date)
    if row_index == 0:
        raise RuntimeError(f"Строка Status за {target_date.strftime('%d.%m.%Y')} не найдена")

    sheet_id = _status_sheet_id()
    header_map = _header_index_map()
    metrics = [
        ("Белок (г)", "protein"),
        ("Углеводы (г)", "carbs"),
        ("Клетчатка (г)", "fiber"),
        ("Жиры (г)", "fat"),
    ]

    requests = []
    applied: dict[str, str] = {}

    for header, metric_key in metrics:
        value = _status_metric_value(target_date, header)
        if value is None:
            continue

        color = _zone_color(metric_key, value)
        if color is None:
            continue

        applied[header] = _zone_label(metric_key, value)
        column_index = header_map[header]
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_index - 1,
                        "endRowIndex": row_index,
                        "startColumnIndex": column_index,
                        "endColumnIndex": column_index + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color,
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor",
                }
            }
        )

    if not requests:
        logger.info(f"Google Sheets: для строки Status за {target_date.strftime('%d.%m.%Y')} нет числовых значений для окраски")
        return {}

    try:
        _service().spreadsheets().batchUpdate(
            spreadsheetId=_status_spreadsheet_id(),
            body={"requests": requests},
        ).execute()
    except HttpError as exc:
        _raise_friendly_http_error(exc)

    logger.info(
        "Google Sheets: цветовые зоны для %s применены (%s)",
        target_date.strftime("%d.%m.%Y"),
        ", ".join(f"{header}={zone}" for header, zone in applied.items()),
    )
    return applied


def color_status_metric_zones_all() -> dict[str, int]:
    ensure_status_sheet()
    values = _status_values()
    if len(values) <= 1:
        logger.info("Google Sheets: лист Status пуст, окрашивать нечего")
        return {"rows_colored": 0, "cells_colored": 0}

    header_map = _header_index_map()
    required_headers = [
        ("Белок (г)", "protein"),
        ("Углеводы (г)", "carbs"),
        ("Клетчатка (г)", "fiber"),
        ("Жиры (г)", "fat"),
    ]
    missing = [header for header, _ in required_headers if header not in header_map]
    if missing:
        raise RuntimeError(f"В листе Status нет колонок: {', '.join(missing)}")

    sheet_id = _status_sheet_id()
    requests = []
    rows_colored: set[int] = set()

    for row_index, row in enumerate(values[1:], start=2):
        row_has_color = False
        for header, metric_key in required_headers:
            col_idx = header_map[header]
            raw_value = row[col_idx] if col_idx < len(row) else ""
            metric_value = _parse_float_or_none(raw_value)
            if metric_value is None:
                continue

            color = _zone_color(metric_key, metric_value)
            if color is None:
                continue

            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_index - 1,
                            "endRowIndex": row_index,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": color,
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColor",
                    }
                }
            )
            row_has_color = True

        if row_has_color:
            rows_colored.add(row_index)

    if not requests:
        logger.info("Google Sheets: не найдено числовых значений для массовой окраски зон")
        return {"rows_colored": 0, "cells_colored": 0}

    try:
        _service().spreadsheets().batchUpdate(
            spreadsheetId=_status_spreadsheet_id(),
            body={"requests": requests},
        ).execute()
    except HttpError as exc:
        _raise_friendly_http_error(exc)

    result = {"rows_colored": len(rows_colored), "cells_colored": len(requests)}
    logger.info(
        "Google Sheets: массовая окраска зон завершена (строк=%s, ячеек=%s)",
        result["rows_colored"],
        result["cells_colored"],
    )
    return result


def get_status_rows_between(start: date, end: date) -> list[dict]:
    ensure_status_sheet()
    values = _status_values()
    if not values:
        return []

    header = values[0]
    rows: list[dict] = []
    for row in values[1:]:
        date_cell = row[0] if row else ""
        parsed_date = _parse_status_date_cell(date_cell, start, end)
        if not parsed_date:
            continue

        row_dict: dict[str, str] = {"_date": parsed_date.isoformat()}
        for idx, col_name in enumerate(header):
            row_dict[col_name] = row[idx] if idx < len(row) else ""
        rows.append(row_dict)

    rows.sort(key=lambda item: item["_date"])
    return rows
