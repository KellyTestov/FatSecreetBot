"""
Вся аналитика: расчёт итогов, сводок по периодам, недели похудения,
сравнение периодов, топ продуктов, проверка целей.
"""
from datetime import date, timedelta


def to_float(value) -> float:
    """Безопасное преобразование в float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_entry(entry: dict) -> dict:
    """Нормализует одну запись питания к стандартному виду."""
    return {
        "meal": entry.get("meal", "Other"),
        "name": entry.get("food_entry_name", "Без названия"),
        "description": entry.get("food_entry_description", ""),
        "calories": to_float(entry.get("calories")),
        "protein": to_float(entry.get("protein")),
        "fat": to_float(entry.get("fat")),
        "carbs": to_float(entry.get("carbohydrate")),
        "fiber": to_float(entry.get("fiber") or entry.get("dietary_fiber")),
        "sugar": to_float(entry.get("sugar")),
        "sodium": to_float(entry.get("sodium")),
    }


def day_totals(entries: list) -> dict:
    """Считает суммарные нутриенты за день."""
    totals = {
        "calories": 0.0,
        "protein": 0.0,
        "fat": 0.0,
        "carbs": 0.0,
        "fiber": 0.0,
        "sugar": 0.0,
        "sodium": 0.0,
    }
    for entry in entries:
        parsed = parse_entry(entry)
        for key in totals:
            totals[key] += parsed[key]
    return totals


def period_summary(days_data: dict) -> dict:
    """
    Считает сводку за период.

    Args:
        days_data: {date: [entries]}

    Returns:
        Словарь с итогами, средними, лучшим/худшим днём.
    """
    all_days = sorted(days_data.keys())
    days_with_data = [d for d in all_days if days_data[d]]
    days_without_data = [d for d in all_days if not days_data[d]]

    if not days_with_data:
        return {
            "total_days": len(all_days),
            "days_with_data": 0,
            "days_without_data": len(all_days),
            "days_without_data_list": days_without_data,
            "totals": None,
            "averages": None,
            "daily_totals": {},
            "best_day": None,
            "best_day_calories": None,
            "worst_day": None,
            "worst_day_calories": None,
        }

    daily = {d: day_totals(days_data[d]) for d in days_with_data}

    period_totals = {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0, "sugar": 0.0, "sodium": 0.0}
    for t in daily.values():
        for key in period_totals:
            period_totals[key] += t[key]

    n = len(days_with_data)
    averages = {k: v / n for k, v in period_totals.items()}

    # Лучший день = минимум калорий, худший = максимум
    sorted_by_cal = sorted(days_with_data, key=lambda d: daily[d]["calories"])
    best_day = sorted_by_cal[0]
    worst_day = sorted_by_cal[-1]

    return {
        "total_days": len(all_days),
        "days_with_data": n,
        "days_without_data": len(days_without_data),
        "days_without_data_list": days_without_data,
        "totals": period_totals,
        "averages": averages,
        "daily_totals": daily,
        "best_day": best_day,
        "best_day_calories": daily[best_day]["calories"],
        "worst_day": worst_day,
        "worst_day_calories": daily[worst_day]["calories"],
    }


def week_number(d: date, start_date: date) -> int:
    """
    Возвращает номер недели похудения для даты d.
    Неделя 1 = дни 0-6 от start_date.
    Возвращает 0 если дата раньше старта.
    """
    delta = (d - start_date).days
    if delta < 0:
        return 0
    return delta // 7 + 1


def week_date_range(week_num: int, start_date: date) -> tuple[date, date]:
    """Возвращает (начало, конец) для недели похудения с номером week_num."""
    week_start = start_date + timedelta(days=(week_num - 1) * 7)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def current_week_number(start_date: date) -> int:
    """Номер текущей недели похудения."""
    return week_number(date.today(), start_date)


def goals_check(totals: dict, goals: dict) -> dict:
    """Проверяет выполнение целей за день."""
    result = {}
    if goals.get("calories") is not None:
        result["calories_ok"] = totals["calories"] <= goals["calories"]
        result["calories_diff"] = totals["calories"] - goals["calories"]
    if goals.get("protein") is not None:
        result["protein_ok"] = totals["protein"] >= goals["protein"]
        result["protein_diff"] = totals["protein"] - goals["protein"]
    if goals.get("max_sugar") is not None:
        result["sugar_ok"] = totals["sugar"] <= goals["max_sugar"]
        result["sugar_diff"] = totals["sugar"] - goals["max_sugar"]
    if goals.get("max_sodium") is not None:
        result["sodium_ok"] = totals["sodium"] <= goals["max_sodium"]
        result["sodium_diff"] = totals["sodium"] - goals["max_sodium"]
    return result


def goals_period_stats(daily_totals: dict, goals: dict) -> dict:
    """Считает сколько дней за период выполнена каждая цель."""
    stats = {
        "days_calories_ok": 0,
        "days_protein_ok": 0,
        "days_sugar_ok": 0,
        "days_sodium_ok": 0,
        "total_days": len(daily_totals),
    }
    for totals in daily_totals.values():
        check = goals_check(totals, goals)
        if check.get("calories_ok"):
            stats["days_calories_ok"] += 1
        if check.get("protein_ok"):
            stats["days_protein_ok"] += 1
        if check.get("sugar_ok"):
            stats["days_sugar_ok"] += 1
        if check.get("sodium_ok"):
            stats["days_sodium_ok"] += 1
    return stats


def compare_periods(days1: dict, days2: dict) -> dict:
    """Сравнивает два периода. Возвращает сводки и разницу в средних."""
    s1 = period_summary(days1)
    s2 = period_summary(days2)
    diff = {}
    if s1["averages"] and s2["averages"]:
        for key in s1["averages"]:
            diff[key] = s1["averages"][key] - s2["averages"][key]
    return {"period1": s1, "period2": s2, "diff": diff}


def top_products(days_data: dict, n: int = 10, sort_by: str = "calories") -> list:
    """
    Топ N продуктов за период.
    sort_by: 'calories', 'protein', 'fat', 'carbs', 'sugar', 'sodium', 'count'
    """
    stats: dict[str, dict] = {}
    for entries in days_data.values():
        for entry in entries:
            name = entry.get("food_entry_name", "Без названия")
            if name not in stats:
                stats[name] = {
                    "name": name,
                    "count": 0,
                    "calories": 0.0,
                    "protein": 0.0,
                    "fat": 0.0,
                    "carbs": 0.0,
                    "sugar": 0.0,
                    "sodium": 0.0,
                }
            stats[name]["count"] += 1
            stats[name]["calories"] += to_float(entry.get("calories"))
            stats[name]["protein"] += to_float(entry.get("protein"))
            stats[name]["fat"] += to_float(entry.get("fat"))
            stats[name]["carbs"] += to_float(entry.get("carbohydrate"))
            stats[name]["sugar"] += to_float(entry.get("sugar"))
            stats[name]["sodium"] += to_float(entry.get("sodium"))

    products = list(stats.values())
    products.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return products[:n]
