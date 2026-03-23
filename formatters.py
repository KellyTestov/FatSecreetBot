"""
Форматирование сообщений для Telegram.
Используется HTML parse_mode.
"""
from datetime import date

from analytics import goals_check, goals_period_stats, parse_entry

MEAL_NAMES = {
    "Breakfast": "Завтрак",
    "Lunch": "Обед",
    "Dinner": "Ужин",
    "Snacks": "Перекус",
    "Other": "Другое",
}


def meal_name(meal: str) -> str:
    return MEAL_NAMES.get(meal, meal)


def fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def fmt_num(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}"


def sign(value: float) -> str:
    return "+" if value >= 0 else ""


def split_long_message(text: str, max_length: int = 4000) -> list[str]:
    """Делит длинное сообщение на части, не разрывая строки."""
    if len(text) <= max_length:
        return [text]
    lines = text.split("\n")
    parts = []
    current_lines: list[str] = []
    current_len = 0
    for line in lines:
        if current_len + len(line) + 1 > max_length and current_lines:
            parts.append("\n".join(current_lines))
            current_lines = [line]
            current_len = len(line)
        else:
            current_lines.append(line)
            current_len += len(line) + 1
    if current_lines:
        parts.append("\n".join(current_lines))
    return parts


def format_day_report(d: date, entries: list, goals: dict) -> str:
    """Форматирует отчёт за один день с приёмами пищи, итогами и целями."""
    if not entries:
        return f"<b>{fmt_date(d)}</b>\n\nЗа этот день записей нет."

    lines = [f"<b>Отчёт за {fmt_date(d)}</b>\n"]

    # Группируем по приёмам пищи
    meals: dict[str, list] = {}
    for entry in entries:
        parsed = parse_entry(entry)
        meal = parsed["meal"]
        meals.setdefault(meal, []).append(parsed)

    total = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0, "sugar": 0.0, "sodium": 0.0}

    for meal, meal_entries in meals.items():
        lines.append(f"<b>{meal_name(meal)}</b>")
        for e in meal_entries:
            desc = f" ({e['description']})" if e["description"] else ""
            lines.append(f"  {e['name']}{desc}")
            lines.append(
                f"  {fmt_num(e['calories'])} ккал  |  "
                f"Б: {fmt_num(e['protein'])}  "
                f"Ж: {fmt_num(e['fat'])}  "
                f"У: {fmt_num(e['carbs'])}"
            )
            for key in total:
                total[key] += e[key]
        lines.append("")

    lines.append("<b>Итого за день:</b>")
    lines.append(f"  Калории:  {fmt_num(total['calories'])} ккал")
    lines.append(f"  Белки:    {fmt_num(total['protein'])} г")
    lines.append(f"  Жиры:     {fmt_num(total['fat'])} г")
    lines.append(f"  Углеводы: {fmt_num(total['carbs'])} г")
    if total["sugar"] > 0:
        lines.append(f"  Сахар:    {fmt_num(total['sugar'])} г")
    if total["sodium"] > 0:
        lines.append(f"  Натрий:   {fmt_num(total['sodium'])} мг")

    # Проверка целей
    if any(v is not None for v in goals.values()):
        check = goals_check(total, goals)
        lines.append("")
        lines.append("<b>Цели:</b>")
        if "calories_ok" in check:
            ok = "✓" if check["calories_ok"] else "✗"
            diff = check["calories_diff"]
            lines.append(f"  {ok} Калории: {fmt_num(total['calories'])} / {goals['calories']}  ({sign(diff)}{fmt_num(diff)})")
        if "protein_ok" in check:
            ok = "✓" if check["protein_ok"] else "✗"
            diff = check["protein_diff"]
            lines.append(f"  {ok} Белок: {fmt_num(total['protein'])} / {goals['protein']} г  ({sign(diff)}{fmt_num(diff)})")
        if "sugar_ok" in check:
            ok = "✓" if check["sugar_ok"] else "✗"
            diff = check["sugar_diff"]
            lines.append(f"  {ok} Сахар: {fmt_num(total['sugar'])} / {goals['max_sugar']} г  ({sign(diff)}{fmt_num(diff)})")
        if "sodium_ok" in check:
            ok = "✓" if check["sodium_ok"] else "✗"
            diff = check["sodium_diff"]
            lines.append(f"  {ok} Натрий: {fmt_num(total['sodium'])} / {goals['max_sodium']} мг  ({sign(diff)}{fmt_num(diff)})")

    return "\n".join(lines)


def format_period_summary(start: date, end: date, summary: dict, goals: dict, title: str = None) -> str:
    """Форматирует сводку за период."""
    if title is None:
        title = f"{fmt_date(start)} — {fmt_date(end)}"

    lines = [f"<b>{title}</b>\n"]

    if summary["days_with_data"] == 0:
        lines.append("За этот период нет данных.")
        return "\n".join(lines)

    n = summary["days_with_data"]
    totals = summary["totals"]
    averages = summary["averages"]

    lines.append(f"Дней в периоде: {summary['total_days']}")
    lines.append(f"Дней с записями: {n}")
    if summary["days_without_data"] > 0:
        missing = [fmt_date(d) for d in summary["days_without_data_list"]]
        lines.append(f"Без записей: {', '.join(missing)}")

    lines.append("")
    lines.append("<b>Итого за период:</b>")
    lines.append(f"  Калории:  {fmt_num(totals['calories'])} ккал")
    lines.append(f"  Белки:    {fmt_num(totals['protein'])} г")
    lines.append(f"  Жиры:     {fmt_num(totals['fat'])} г")
    lines.append(f"  Углеводы: {fmt_num(totals['carbs'])} г")

    lines.append("")
    lines.append("<b>Средние за день:</b>")
    lines.append(f"  Калории:  {fmt_num(averages['calories'])} ккал")
    lines.append(f"  Белки:    {fmt_num(averages['protein'])} г")
    lines.append(f"  Жиры:     {fmt_num(averages['fat'])} г")
    lines.append(f"  Углеводы: {fmt_num(averages['carbs'])} г")

    if summary["best_day"]:
        lines.append("")
        lines.append(f"Лучший день: {fmt_date(summary['best_day'])} ({fmt_num(summary['best_day_calories'])} ккал)")
        lines.append(f"Худший день: {fmt_date(summary['worst_day'])} ({fmt_num(summary['worst_day_calories'])} ккал)")

    # По дням
    if summary["daily_totals"]:
        lines.append("")
        lines.append("<b>По дням:</b>")
        for d in sorted(summary["daily_totals"].keys()):
            t = summary["daily_totals"][d]
            lines.append(
                f"  {fmt_date(d)}: {fmt_num(t['calories'])} ккал  "
                f"Б:{fmt_num(t['protein'])}  "
                f"Ж:{fmt_num(t['fat'])}  "
                f"У:{fmt_num(t['carbs'])}"
            )

    # Цели за период
    if any(v is not None for v in goals.values()):
        gstats = goals_period_stats(summary["daily_totals"], goals)
        lines.append("")
        lines.append("<b>Цели (дней выполнено):</b>")
        if goals.get("calories") is not None:
            lines.append(f"  Калории ≤ {goals['calories']}: {gstats['days_calories_ok']} из {n}")
        if goals.get("protein") is not None:
            lines.append(f"  Белок ≥ {goals['protein']}: {gstats['days_protein_ok']} из {n}")
        if goals.get("max_sugar") is not None:
            lines.append(f"  Сахар ≤ {goals['max_sugar']}: {gstats['days_sugar_ok']} из {n}")
        if goals.get("max_sodium") is not None:
            lines.append(f"  Натрий ≤ {goals['max_sodium']}: {gstats['days_sodium_ok']} из {n}")

    return "\n".join(lines)


def format_comparison(start1: date, end1: date, start2: date, end2: date, comparison: dict) -> str:
    """Форматирует сравнение двух периодов."""
    s1 = comparison["period1"]
    s2 = comparison["period2"]
    diff = comparison["diff"]

    lines = [
        "<b>Сравнение периодов</b>\n",
        f"Период 1: {fmt_date(start1)} — {fmt_date(end1)} ({s1['days_with_data']} дн.)",
        f"Период 2: {fmt_date(start2)} — {fmt_date(end2)} ({s2['days_with_data']} дн.)",
        "",
    ]

    if not s1["averages"] or not s2["averages"]:
        lines.append("Недостаточно данных для сравнения.")
        return "\n".join(lines)

    a1 = s1["averages"]
    a2 = s2["averages"]

    lines.append("<b>Средние в день:</b>")
    lines.append("<pre>")

    rows = [
        ("Калории", "calories", "ккал"),
        ("Белки", "protein", "г"),
        ("Жиры", "fat", "г"),
        ("Углеводы", "carbs", "г"),
    ]

    lines.append(f"{'':12} {'Период 1':>10} {'Период 2':>10} {'Разница':>10}")
    lines.append("-" * 44)

    for label, key, unit in rows:
        v1 = a1[key]
        v2 = a2[key]
        d = diff.get(key, 0)
        arrow = "↑" if d > 0.5 else ("↓" if d < -0.5 else "=")
        lines.append(f"{label:<12} {fmt_num(v1):>8} {unit}  {fmt_num(v2):>8} {unit}  {sign(d)}{fmt_num(d)} {arrow}")

    lines.append("</pre>")
    return "\n".join(lines)


def format_top_products(products: list, sort_by: str = "calories", period_label: str = "") -> str:
    """Форматирует топ продуктов."""
    sort_labels = {
        "calories": "калориям",
        "protein": "белку",
        "fat": "жирам",
        "carbs": "углеводам",
        "sugar": "сахару",
        "sodium": "натрию",
        "count": "частоте",
    }
    label = sort_labels.get(sort_by, sort_by)

    header = f"<b>Топ продуктов по {label}</b>"
    if period_label:
        header += f"\n{period_label}"
    lines = [header, ""]

    if not products:
        lines.append("Нет данных.")
        return "\n".join(lines)

    for i, p in enumerate(products, 1):
        lines.append(f"<b>{i}. {p['name']}</b>")
        lines.append(
            f"   {fmt_num(p['calories'])} ккал  |  "
            f"Б: {fmt_num(p['protein'])} г  |  "
            f"{p['count']} раз"
        )

    return "\n".join(lines)


def format_settings(settings: dict) -> str:
    """Форматирует текущие настройки пользователя."""
    lines = ["<b>Настройки</b>\n"]

    start_date = settings.get("start_date")
    lines.append(f"Дата старта похудения: {start_date if start_date else 'не задана'}")

    goals = settings.get("goals", {})
    lines.append("\n<b>Цели:</b>")

    def g(label, key):
        val = goals.get(key)
        return f"  {label}: {val if val is not None else 'не задана'}"

    lines.append(g("Калории (цель)", "calories"))
    lines.append(g("Белок (минимум, г)", "protein"))
    lines.append(g("Сахар (максимум, г)", "max_sugar"))
    lines.append(g("Натрий (максимум, мг)", "max_sodium"))

    lines.append("\n<b>Изменить:</b>")
    lines.append("  /set_start_date YYYY-MM-DD")
    lines.append("  /set_goals")

    return "\n".join(lines)
