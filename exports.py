"""
Экспорт данных в Excel и PDF.

Excel: полноценный отчёт с несколькими листами.
PDF: отчёт с таблицами, поддержка кириллицы через системный шрифт Arial (Windows).
"""
import os
import platform
from datetime import date
from pathlib import Path

import config
from analytics import period_summary, top_products, parse_entry, to_float
from formatters import fmt_date, fmt_num


def _ensure_exports_dir() -> Path:
    config.EXPORTS_DIR.mkdir(exist_ok=True)
    return config.EXPORTS_DIR


# ============================================================
# Excel экспорт
# ============================================================

def create_excel(days_data: dict, start: date, end: date, goals: dict) -> Path:
    """
    Создаёт Excel файл с тремя листами:
    - Сводка: итоги и средние за период
    - По дням: одна строка на день
    - Все записи: каждый продукт отдельной строкой
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()

    # ---- Лист 1: Сводка ----
    ws_summary = wb.active
    ws_summary.title = "Сводка"

    header_font = Font(bold=True, size=12)
    title_font = Font(bold=True, size=14)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font_white = Font(bold=True, color="FFFFFF")

    summary = period_summary(days_data)
    period_label = f"{fmt_date(start)} — {fmt_date(end)}"

    ws_summary["A1"] = f"Отчёт по питанию: {period_label}"
    ws_summary["A1"].font = title_font
    ws_summary.merge_cells("A1:D1")

    row = 3
    ws_summary[f"A{row}"] = "Показатель"
    ws_summary[f"B{row}"] = "Значение"
    ws_summary[f"A{row}"].font = header_font
    ws_summary[f"B{row}"].font = header_font
    row += 1

    def add_row(label, value):
        nonlocal row
        ws_summary[f"A{row}"] = label
        ws_summary[f"B{row}"] = value
        row += 1

    add_row("Дней в периоде", summary["total_days"])
    add_row("Дней с записями", summary["days_with_data"])
    add_row("Дней без записей", summary["days_without_data"])

    if summary["totals"]:
        add_row("", "")
        add_row("--- Итого за период ---", "")
        add_row("Калории (ккал)", round(summary["totals"]["calories"], 1))
        add_row("Белки (г)", round(summary["totals"]["protein"], 1))
        add_row("Жиры (г)", round(summary["totals"]["fat"], 1))
        add_row("Углеводы (г)", round(summary["totals"]["carbs"], 1))
        add_row("Сахар (г)", round(summary["totals"]["sugar"], 1))
        add_row("Натрий (мг)", round(summary["totals"]["sodium"], 1))

        add_row("", "")
        add_row("--- Средние за день ---", "")
        add_row("Калории (ккал)", round(summary["averages"]["calories"], 1))
        add_row("Белки (г)", round(summary["averages"]["protein"], 1))
        add_row("Жиры (г)", round(summary["averages"]["fat"], 1))
        add_row("Углеводы (г)", round(summary["averages"]["carbs"], 1))

        if summary["best_day"]:
            add_row("", "")
            add_row("Лучший день (мин. ккал)", f"{fmt_date(summary['best_day'])} ({fmt_num(summary['best_day_calories'])} ккал)")
            add_row("Худший день (макс. ккал)", f"{fmt_date(summary['worst_day'])} ({fmt_num(summary['worst_day_calories'])} ккал)")

    if any(v is not None for v in goals.values()):
        add_row("", "")
        add_row("--- Цели ---", "")
        if goals.get("calories") is not None:
            add_row("Цель калории", goals["calories"])
        if goals.get("protein") is not None:
            add_row("Цель белок (мин)", goals["protein"])
        if goals.get("max_sugar") is not None:
            add_row("Максимум сахара", goals["max_sugar"])
        if goals.get("max_sodium") is not None:
            add_row("Максимум натрия", goals["max_sodium"])

    ws_summary.column_dimensions["A"].width = 30
    ws_summary.column_dimensions["B"].width = 20

    # ---- Лист 2: По дням ----
    ws_days = wb.create_sheet("По дням")
    day_headers = ["Дата", "Калории", "Белки (г)", "Жиры (г)", "Углеводы (г)", "Сахар (г)", "Натрий (мг)"]
    ws_days.append(day_headers)

    # Стиль заголовков
    for col_idx, _ in enumerate(day_headers, 1):
        cell = ws_days.cell(row=1, column=col_idx)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    if summary["daily_totals"]:
        for d in sorted(summary["daily_totals"].keys()):
            t = summary["daily_totals"][d]
            ws_days.append([
                fmt_date(d),
                round(t["calories"], 1),
                round(t["protein"], 1),
                round(t["fat"], 1),
                round(t["carbs"], 1),
                round(t["sugar"], 1),
                round(t["sodium"], 1),
            ])

    for col_idx in range(1, len(day_headers) + 1):
        ws_days.column_dimensions[get_column_letter(col_idx)].width = 14

    # ---- Лист 3: Все записи ----
    ws_entries = wb.create_sheet("Все записи")
    entry_headers = ["Дата", "Приём пищи", "Продукт", "Описание", "Калории", "Белки (г)", "Жиры (г)", "Углеводы (г)", "Сахар (г)", "Натрий (мг)"]
    ws_entries.append(entry_headers)

    for col_idx, _ in enumerate(entry_headers, 1):
        cell = ws_entries.cell(row=1, column=col_idx)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    meal_names = {
        "Breakfast": "Завтрак",
        "Lunch": "Обед",
        "Dinner": "Ужин",
        "Snacks": "Перекус",
        "Other": "Другое",
    }

    for d in sorted(days_data.keys()):
        for entry in days_data[d]:
            parsed = parse_entry(entry)
            ws_entries.append([
                fmt_date(d),
                meal_names.get(parsed["meal"], parsed["meal"]),
                parsed["name"],
                parsed["description"],
                round(parsed["calories"], 1),
                round(parsed["protein"], 1),
                round(parsed["fat"], 1),
                round(parsed["carbs"], 1),
                round(parsed["sugar"], 1),
                round(parsed["sodium"], 1),
            ])

    col_widths = [12, 12, 35, 25, 10, 10, 10, 12, 10, 12]
    for col_idx, width in enumerate(col_widths, 1):
        ws_entries.column_dimensions[get_column_letter(col_idx)].width = width

    # Сохраняем файл
    exports_dir = _ensure_exports_dir()
    filename = f"nutrition_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.xlsx"
    filepath = exports_dir / filename
    wb.save(filepath)
    return filepath


# ============================================================
# PDF экспорт
# ============================================================

def _register_cyrillic_font():
    """
    Регистрирует шрифт с поддержкой кириллицы для reportlab.
    На Windows использует системный Arial.
    Возвращает (обычный_шрифт, жирный_шрифт).
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if platform.system() == "Windows":
        font_paths = [
            ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
            ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
        ]
        for regular, bold in font_paths:
            if os.path.exists(regular) and os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("CyrRegular", regular))
                pdfmetrics.registerFont(TTFont("CyrBold", bold))
                return "CyrRegular", "CyrBold"

    # Fallback: Helvetica (кириллица не отобразится, но PDF создастся)
    return "Helvetica", "Helvetica-Bold"


def create_pdf(days_data: dict, start: date, end: date, goals: dict) -> Path:
    """
    Создаёт PDF отчёт с:
    - заголовком периода
    - сводной таблицей
    - таблицей по дням
    - топ продуктов
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle,
        Paragraph, Spacer
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    font_regular, font_bold = _register_cyrillic_font()

    exports_dir = _ensure_exports_dir()
    filename = f"nutrition_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.pdf"
    filepath = exports_dir / filename

    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    style_title = ParagraphStyle("title", fontName=font_bold, fontSize=16, alignment=TA_CENTER, spaceAfter=12)
    style_h2 = ParagraphStyle("h2", fontName=font_bold, fontSize=12, spaceBefore=12, spaceAfter=6)
    style_normal = ParagraphStyle("normal", fontName=font_regular, fontSize=10, spaceAfter=4)

    header_bg = colors.HexColor("#4472C4")
    row_alt = colors.HexColor("#EEF2FF")

    def make_table(data, col_widths=None):
        t = Table(data, colWidths=col_widths)
        style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), font_bold),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 1), (-1, -1), font_regular),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, row_alt]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
        t.setStyle(style)
        return t

    summary = period_summary(days_data)
    period_label = f"{fmt_date(start)} — {fmt_date(end)}"

    story = []

    # Заголовок
    story.append(Paragraph(f"Отчёт по питанию", style_title))
    story.append(Paragraph(period_label, style_title))
    story.append(Spacer(1, 0.5 * cm))

    # Сводная таблица
    story.append(Paragraph("Сводка за период", style_h2))
    summary_data = [["Показатель", "Значение"]]
    summary_data.append(["Дней в периоде", str(summary["total_days"])])
    summary_data.append(["Дней с записями", str(summary["days_with_data"])])
    summary_data.append(["Дней без записей", str(summary["days_without_data"])])

    if summary["totals"]:
        summary_data.append(["Калории итого (ккал)", fmt_num(summary["totals"]["calories"])])
        summary_data.append(["Белки итого (г)", fmt_num(summary["totals"]["protein"])])
        summary_data.append(["Жиры итого (г)", fmt_num(summary["totals"]["fat"])])
        summary_data.append(["Углеводы итого (г)", fmt_num(summary["totals"]["carbs"])])
        summary_data.append(["Калории средние (ккал)", fmt_num(summary["averages"]["calories"])])
        summary_data.append(["Белки средние (г)", fmt_num(summary["averages"]["protein"])])
        summary_data.append(["Жиры средние (г)", fmt_num(summary["averages"]["fat"])])
        summary_data.append(["Углеводы средние (г)", fmt_num(summary["averages"]["carbs"])])
        if summary["best_day"]:
            summary_data.append(["Лучший день (мин. ккал)", f"{fmt_date(summary['best_day'])} ({fmt_num(summary['best_day_calories'])}ккал)"])
            summary_data.append(["Худший день (макс. ккал)", f"{fmt_date(summary['worst_day'])} ({fmt_num(summary['worst_day_calories'])}ккал)"])

    story.append(make_table(summary_data, col_widths=[10 * cm, 6 * cm]))
    story.append(Spacer(1, 0.5 * cm))

    # По дням
    if summary["daily_totals"]:
        story.append(Paragraph("По дням", style_h2))
        days_table_data = [["Дата", "Калории", "Белки г", "Жиры г", "Углеводы г"]]
        for d in sorted(summary["daily_totals"].keys()):
            t = summary["daily_totals"][d]
            days_table_data.append([
                fmt_date(d),
                fmt_num(t["calories"]),
                fmt_num(t["protein"]),
                fmt_num(t["fat"]),
                fmt_num(t["carbs"]),
            ])
        story.append(make_table(days_table_data, col_widths=[4 * cm, 3.5 * cm, 3 * cm, 3 * cm, 3.5 * cm]))
        story.append(Spacer(1, 0.5 * cm))

    # Топ продуктов
    products = top_products(days_data, n=10, sort_by="calories")
    if products:
        story.append(Paragraph("Топ продуктов по калориям", style_h2))
        prod_data = [["Продукт", "Раз", "Калории", "Белки г"]]
        for p in products:
            prod_data.append([
                p["name"][:45],
                str(p["count"]),
                fmt_num(p["calories"]),
                fmt_num(p["protein"]),
            ])
        story.append(make_table(prod_data, col_widths=[9 * cm, 2 * cm, 3 * cm, 3 * cm]))

    doc.build(story)
    return filepath
