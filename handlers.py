"""
Все обработчики команд Telegram-бота.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import analytics
import config
import exports
import fatsecret
import formatters
import google_sheets

logger = logging.getLogger(__name__)


def _who(update: Update) -> str:
    """Возвращает имя пользователя для лога."""
    user = update.effective_user
    if user.username:
        return f"@{user.username}"
    return user.full_name or f"ID:{user.id}"


# --- Состояния для диалогов ---
AUTH_VERIFIER = 0
GOALS_CALORIES, GOALS_PROTEIN, GOALS_SUGAR, GOALS_SODIUM = range(4)


# ============================================================
# Вспомогательные функции
# ============================================================

def parse_date(s: str) -> date:
    """Парсит дату из YYYY-MM-DD или DD.MM.YYYY."""
    for fmt in ["%Y-%m-%d", "%d.%m.%Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты: {s}\nИспользуй YYYY-MM-DD или DD.MM.YYYY")


async def send_long(update: Update, text: str):
    """Отправляет сообщение, разбивая его на части если оно длинное."""
    parts = formatters.split_long_message(text)
    for part in parts:
        await update.message.reply_text(part, parse_mode=ParseMode.HTML)


def check_access(update: Update) -> bool:
    """Проверяет, разрешён ли доступ этому пользователю."""
    if config.ALLOWED_USER_ID is None:
        return True
    return update.effective_user.id == config.ALLOWED_USER_ID


async def get_tokens(update: Update) -> tuple[str | None, str | None]:
    """Загружает токены или отправляет сообщение об ошибке. Возвращает (token, secret) или (None, None)."""
    token, secret = fatsecret.load_tokens()
    if not token:
        await update.message.reply_text(
            "Токены FatSecret не найдены.\n"
            "Используй /auth для авторизации.",
            parse_mode=ParseMode.HTML,
        )
        return None, None
    return token, secret


async def fetch_day(update: Update, token: str, secret: str, d: date) -> list | None:
    """Загружает записи за один день. При ошибке — отправляет сообщение и возвращает None."""
    try:
        return await asyncio.to_thread(fatsecret.get_entries_for_date, token, secret, d)
    except fatsecret.TokenExpiredError:
        await update.message.reply_text(
            "Токен FatSecret истёк.\n"
            "Используй /auth для повторной авторизации."
        )
        return None
    except Exception as e:
        logger.error(f"Ошибка загрузки за {d}: {e}")
        await update.message.reply_text(f"Ошибка при получении данных: {e}")
        return None


async def fetch_range(update: Update, token: str, secret: str, start: date, end: date) -> dict | None:
    """Загружает записи за диапазон дат. Возвращает {date: entries} или None при ошибке."""
    delta = (end - start).days + 1
    if delta > 90:
        await update.message.reply_text("Максимальный период — 90 дней.")
        return None
    try:
        await update.message.reply_text(f"Загружаю данные за {delta} дн....")
        return await asyncio.to_thread(fatsecret.get_entries_for_range, token, secret, start, end)
    except fatsecret.TokenExpiredError:
        await update.message.reply_text(
            "Токен FatSecret истёк.\n"
            "Используй /auth для повторной авторизации."
        )
        return None
    except Exception as e:
        logger.error(f"Ошибка загрузки диапазона {start}-{end}: {e}")
        await update.message.reply_text(f"Ошибка при получении данных: {e}")
        return None


# ============================================================
# Авторизация FatSecret
# ============================================================

async def cmd_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает OAuth авторизацию FatSecret через Telegram."""
    if not check_access(update):
        return ConversationHandler.END
    logger.info(f"/auth — {_who(update)}: начало авторизации FatSecret")
    try:
        req_token, req_secret, auth_url = await asyncio.to_thread(fatsecret.get_request_token)
        context.user_data["auth_request_token"] = req_token
        context.user_data["auth_request_secret"] = req_secret
        await update.message.reply_text(
            "<b>Авторизация FatSecret</b>\n\n"
            f"Шаг 1. Перейди по ссылке:\n{auth_url}\n\n"
            "Шаг 2. Войди в FatSecret и разреши доступ.\n\n"
            "Шаг 3. Скопируй код (verifier) и отправь его сюда.\n\n"
            "Для отмены: /cancel",
            parse_mode=ParseMode.HTML,
        )
        return AUTH_VERIFIER
    except Exception as e:
        await update.message.reply_text(f"Ошибка при запросе авторизации: {e}")
        return ConversationHandler.END


async def auth_verifier_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает verifier код и завершает авторизацию."""
    verifier = update.message.text.strip()
    req_token = context.user_data.get("auth_request_token")
    req_secret = context.user_data.get("auth_request_secret")

    if not req_token or not req_secret:
        await update.message.reply_text("Сессия устарела. Начни заново: /auth")
        return ConversationHandler.END

    try:
        access_token, access_secret = await asyncio.to_thread(
            fatsecret.get_access_token, req_token, req_secret, verifier
        )
        fatsecret.save_tokens(access_token, access_secret)
        logger.info(f"Авторизация FatSecret успешна для {_who(update)}")
        await update.message.reply_text(
            "Авторизация успешна. Токены сохранены.\n\n"
            "Попробуй /today"
        )
    except Exception as e:
        logger.error(f"Ошибка авторизации FatSecret для {_who(update)}: {e}")
        await update.message.reply_text(f"Ошибка авторизации: {e}\n\nПопробуй /auth снова.")

    return ConversationHandler.END


async def auth_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Авторизация отменена.")
    return ConversationHandler.END


# ============================================================
# Основные команды
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    token, _ = fatsecret.load_tokens()
    status = "Токены FatSecret: найдены" if token else "Токены FatSecret: не найдены — используй /auth"
    sheets_status = (
        "Google Sheets: настроен"
        if config.GOOGLE_SHEETS_SPREADSHEET_ID
        else "Google Sheets: не настроен — добавь GOOGLE_SHEETS_SPREADSHEET_ID"
    )
    automation_status = (
        "Автоматизация Status: активна"
        if config.ALLOWED_USER_ID and config.GOOGLE_SHEETS_SPREADSHEET_ID
        else "Автоматизация Status: проверь TELEGRAM_ALLOWED_USER_ID и GOOGLE_SHEETS_SPREADSHEET_ID"
    )
    await update.message.reply_text(
        "<b>FatSecret Analytics Bot</b>\n\n"
        "Личный бот для аналитики питания на основе FatSecret.\n\n"
        f"{status}\n"
        f"{sheets_status}\n"
        f"{automation_status}\n\n"
        "/help — список всех команд",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    text = (
        "<b>Команды бота</b>\n\n"
        "<b>Авторизация:</b>\n"
        "  /auth — авторизация в FatSecret\n\n"
        "<b>Google Sheets:</b>\n"
        "  /sheets_test — проверить доступ к Google Sheets\n\n"
        "<b>Status Automation:</b>\n"
        "  /test_status_sync [дата] — записать питание в лист Status\n"
        "  /test_appetite_prompt [дата] — тест вопроса про аппетит\n"
        "  /test_weight_prompt [дата] — тест вопроса про вес\n"
        "  /test_tirz_prompt [дата] — тест вопроса про Тирзетту\n"
        "  /test_training_prompt [дата] — тест зала и кардио\n"
        "  /test_pool_prompt [дата] — тест бассейна\n\n"
        "<b>День:</b>\n"
        "  /today — сегодня\n"
        "  /yesterday — вчера\n"
        "  /day 2026-03-20 — конкретный день\n\n"
        "<b>Периоды:</b>\n"
        "  /period 2026-03-01 2026-03-20\n"
        "  /last7 — последние 7 дней\n"
        "  /last14 — последние 14 дней\n"
        "  /last30 — последние 30 дней\n\n"
        "<b>Недели похудения:</b>\n"
        "  /week 1 — неделя 1 от даты старта\n"
        "  /week 3 — неделя 3\n"
        "  /current_week — текущая неделя\n\n"
        "<b>Сравнение:</b>\n"
        "  /compare 2026-03-01 2026-03-07 2026-03-08 2026-03-14\n\n"
        "<b>Продукты:</b>\n"
        "  /top_products — топ за 30 дней\n"
        "  /top_products 2026-03-01 2026-03-20\n"
        "  /top_products 2026-03-01 2026-03-20 protein\n\n"
        "<b>Настройки:</b>\n"
        "  /settings — текущие настройки\n"
        "  /set_start_date 2026-02-26\n"
        "  /set_goals — задать цели\n\n"
        "<b>Экспорт:</b>\n"
        "  /export_excel 2026-03-01 2026-03-20\n"
        "  /export_pdf 2026-03-01 2026-03-20"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ============================================================
# Команды за день
# ============================================================

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/today — {_who(update)}")
    token, secret = await get_tokens(update)
    if not token:
        return
    entries = await fetch_day(update, token, secret, date.today())
    if entries is None:
        return
    if not entries:
        logger.info(f"Нет записей за сегодня ({formatters.fmt_date(date.today())})")
        await update.message.reply_text(
            f"<b>{formatters.fmt_date(date.today())}</b>\n\n"
            "За сегодня записей нет.\n\n"
            "Занеси еду в FatSecret и попробуй снова.",
            parse_mode=ParseMode.HTML,
        )
        return
    settings = config.load_settings()
    text = formatters.format_day_report(date.today(), entries, settings.get("goals", {}))
    logger.info(f"Отчёт за день отправлен ({len(entries)} записей)")
    await send_long(update, text)


async def cmd_yesterday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/yesterday — {_who(update)}")
    token, secret = await get_tokens(update)
    if not token:
        return
    yesterday = date.today() - timedelta(days=1)
    entries = await fetch_day(update, token, secret, yesterday)
    if entries is None:
        return
    if not entries:
        logger.info(f"Нет записей за вчера ({formatters.fmt_date(yesterday)})")
        await update.message.reply_text(
            f"<b>{formatters.fmt_date(yesterday)}</b>\n\nЗа вчера записей нет.",
            parse_mode=ParseMode.HTML,
        )
        return
    settings = config.load_settings()
    text = formatters.format_day_report(yesterday, entries, settings.get("goals", {}))
    logger.info(f"Отчёт за вчера отправлен ({len(entries)} записей)")
    await send_long(update, text)


async def cmd_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/day {' '.join(context.args or [])} — {_who(update)}")
    if not context.args:
        await update.message.reply_text("Использование: /day YYYY-MM-DD\nПример: /day 2026-03-15")
        return
    try:
        d = parse_date(context.args[0])
    except ValueError as e:
        await update.message.reply_text(str(e))
        return
    token, secret = await get_tokens(update)
    if not token:
        return
    entries = await fetch_day(update, token, secret, d)
    if entries is None:
        return
    if not entries:
        await update.message.reply_text(
            f"<b>{formatters.fmt_date(d)}</b>\n\nЗа этот день записей нет.",
            parse_mode=ParseMode.HTML,
        )
        return
    settings = config.load_settings()
    text = formatters.format_day_report(d, entries, settings.get("goals", {}))
    logger.info(f"Отчёт за {formatters.fmt_date(d)} отправлен ({len(entries)} записей)")
    await send_long(update, text)


# ============================================================
# Команды за период
# ============================================================

async def _period_report(update: Update, start: date, end: date, title: str = None):
    """Общая логика для всех команд за период."""
    token, secret = await get_tokens(update)
    if not token:
        return
    days_data = await fetch_range(update, token, secret, start, end)
    if days_data is None:
        return
    settings = config.load_settings()
    summary = analytics.period_summary(days_data)
    days_with = summary["days_with_data"]
    total_days = summary["total_days"]
    logger.info(f"Сводка за период {formatters.fmt_date(start)}—{formatters.fmt_date(end)}: {days_with} из {total_days} дней с данными")
    text = formatters.format_period_summary(start, end, summary, settings.get("goals", {}), title=title)
    await send_long(update, text)


async def cmd_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/period {' '.join(context.args or [])} — {_who(update)}")
    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /period YYYY-MM-DD YYYY-MM-DD\n"
            "Пример: /period 2026-03-01 2026-03-20"
        )
        return
    try:
        start = parse_date(context.args[0])
        end = parse_date(context.args[1])
    except ValueError as e:
        await update.message.reply_text(str(e))
        return
    if start > end:
        await update.message.reply_text("Начальная дата должна быть раньше конечной.")
        return
    await _period_report(update, start, end)


async def cmd_last7(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/last7 — {_who(update)}")
    end = date.today()
    start = end - timedelta(days=6)
    await _period_report(update, start, end, f"Последние 7 дней ({formatters.fmt_date(start)} — {formatters.fmt_date(end)})")


async def cmd_last14(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/last14 — {_who(update)}")
    end = date.today()
    start = end - timedelta(days=13)
    await _period_report(update, start, end, f"Последние 14 дней ({formatters.fmt_date(start)} — {formatters.fmt_date(end)})")


async def cmd_last30(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/last30 — {_who(update)}")
    end = date.today()
    start = end - timedelta(days=29)
    await _period_report(update, start, end, f"Последние 30 дней ({formatters.fmt_date(start)} — {formatters.fmt_date(end)})")


# ============================================================
# Недели похудения
# ============================================================

async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/week {' '.join(context.args or [])} — {_who(update)}")
    settings = config.load_settings()
    if not settings.get("start_date"):
        await update.message.reply_text(
            "Дата старта похудения не задана.\n"
            "Используй: /set_start_date YYYY-MM-DD"
        )
        return
    if not context.args:
        await update.message.reply_text("Использование: /week N\nПример: /week 3")
        return
    try:
        week_num = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Номер недели должен быть числом.")
        return
    if week_num < 1:
        await update.message.reply_text("Номер недели должен быть >= 1.")
        return

    start_date = parse_date(settings["start_date"])
    week_start, week_end = analytics.week_date_range(week_num, start_date)
    week_end = min(week_end, date.today())  # не выходим за сегодня

    title = f"Неделя {week_num} ({formatters.fmt_date(week_start)} — {formatters.fmt_date(week_end)})"
    await _period_report(update, week_start, week_end, title=title)


async def cmd_current_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/current_week — {_who(update)}")
    settings = config.load_settings()
    if not settings.get("start_date"):
        await update.message.reply_text(
            "Дата старта похудения не задана.\n"
            "Используй: /set_start_date YYYY-MM-DD"
        )
        return

    start_date = parse_date(settings["start_date"])
    week_num = analytics.current_week_number(start_date)
    week_start, week_end = analytics.week_date_range(week_num, start_date)
    week_end = min(week_end, date.today())

    title = f"Текущая неделя — Неделя {week_num} ({formatters.fmt_date(week_start)} — {formatters.fmt_date(week_end)})"
    await _period_report(update, week_start, week_end, title=title)


# ============================================================
# Сравнение периодов
# ============================================================

async def cmd_compare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/compare {' '.join(context.args or [])} — {_who(update)}")
    if len(context.args) < 4:
        await update.message.reply_text(
            "Использование: /compare start1 end1 start2 end2\n"
            "Пример: /compare 2026-03-01 2026-03-07 2026-03-08 2026-03-14"
        )
        return
    try:
        start1 = parse_date(context.args[0])
        end1 = parse_date(context.args[1])
        start2 = parse_date(context.args[2])
        end2 = parse_date(context.args[3])
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    token, secret = await get_tokens(update)
    if not token:
        return

    days1 = await fetch_range(update, token, secret, start1, end1)
    if days1 is None:
        return
    days2 = await fetch_range(update, token, secret, start2, end2)
    if days2 is None:
        return

    comparison = analytics.compare_periods(days1, days2)
    logger.info(f"Сравнение отправлено: {formatters.fmt_date(start1)}—{formatters.fmt_date(end1)} vs {formatters.fmt_date(start2)}—{formatters.fmt_date(end2)}")
    text = formatters.format_comparison(start1, end1, start2, end2, comparison)
    await send_long(update, text)


# ============================================================
# Топ продуктов
# ============================================================

async def cmd_top_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/top_products {' '.join(context.args or [])} — {_who(update)}")
    args = context.args
    sort_by = "calories"
    end = date.today()
    start = end - timedelta(days=29)

    if len(args) >= 2:
        try:
            start = parse_date(args[0])
            end = parse_date(args[1])
        except ValueError as e:
            await update.message.reply_text(str(e))
            return
        if len(args) >= 3:
            sort_by = args[2]

    valid_sort = ["calories", "protein", "fat", "carbs", "sugar", "sodium", "count"]
    if sort_by not in valid_sort:
        await update.message.reply_text(f"Доступные варианты сортировки: {', '.join(valid_sort)}")
        return

    token, secret = await get_tokens(update)
    if not token:
        return

    days_data = await fetch_range(update, token, secret, start, end)
    if days_data is None:
        return

    products = analytics.top_products(days_data, n=15, sort_by=sort_by)
    logger.info(f"Топ продуктов отправлен: {len(products)} позиций, сортировка по {sort_by}")
    period_label = f"{formatters.fmt_date(start)} — {formatters.fmt_date(end)}"
    text = formatters.format_top_products(products, sort_by=sort_by, period_label=period_label)
    await send_long(update, text)


# ============================================================
# Настройки
# ============================================================

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    settings = config.load_settings()
    text = formatters.format_settings(settings)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_set_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Использование: /set_start_date YYYY-MM-DD\n"
            "Пример: /set_start_date 2026-02-26"
        )
        return
    try:
        d = parse_date(context.args[0])
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    settings = config.load_settings()
    settings["start_date"] = d.strftime("%Y-%m-%d")
    config.save_settings(settings)
    logger.info(f"Дата старта похудения установлена: {formatters.fmt_date(d)} — {_who(update)}")
    await update.message.reply_text(
        f"Дата старта похудения установлена: <b>{formatters.fmt_date(d)}</b>\n\n"
        "Теперь доступны команды /week N и /current_week",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# Диалог: настройка целей (/set_goals)
# ============================================================

async def cmd_set_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return ConversationHandler.END
    settings = config.load_settings()
    cur = settings.get("goals", {}).get("calories", "не задано")
    await update.message.reply_text(
        "<b>Настройка целей питания</b>\n\n"
        f"Текущая цель по калориям: {cur}\n\n"
        "Введи цель по калориям (например: 1800)\n"
        "Или <b>-</b> чтобы оставить без изменений\n"
        "Для отмены: /cancel",
        parse_mode=ParseMode.HTML,
    )
    return GOALS_CALORIES


async def goals_calories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["new_goals"] = {}
    if text != "-":
        try:
            context.user_data["new_goals"]["calories"] = float(text)
        except ValueError:
            await update.message.reply_text("Введи число или - для пропуска.")
            return GOALS_CALORIES
    settings = config.load_settings()
    cur = settings.get("goals", {}).get("protein", "не задано")
    await update.message.reply_text(
        f"Текущий минимум белка: {cur} г\n"
        "Введи минимум белка в день (г), например: 150\n"
        "Или - чтобы оставить без изменений"
    )
    return GOALS_PROTEIN


async def goals_protein(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "-":
        try:
            context.user_data["new_goals"]["protein"] = float(text)
        except ValueError:
            await update.message.reply_text("Введи число или - для пропуска.")
            return GOALS_PROTEIN
    settings = config.load_settings()
    cur = settings.get("goals", {}).get("max_sugar", "не задано")
    await update.message.reply_text(
        f"Текущий максимум сахара: {cur} г\n"
        "Введи максимум сахара в день (г), например: 30\n"
        "Или - чтобы оставить без изменений"
    )
    return GOALS_SUGAR


async def goals_sugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "-":
        try:
            context.user_data["new_goals"]["max_sugar"] = float(text)
        except ValueError:
            await update.message.reply_text("Введи число или - для пропуска.")
            return GOALS_SUGAR
    settings = config.load_settings()
    cur = settings.get("goals", {}).get("max_sodium", "не задано")
    await update.message.reply_text(
        f"Текущий максимум натрия: {cur} мг\n"
        "Введи максимум натрия в день (мг), например: 2000\n"
        "Или - чтобы оставить без изменений"
    )
    return GOALS_SODIUM


async def goals_sodium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "-":
        try:
            context.user_data["new_goals"]["max_sodium"] = float(text)
        except ValueError:
            await update.message.reply_text("Введи число или - для пропуска.")
            return GOALS_SODIUM

    # Сохраняем только изменённые цели
    new_goals = context.user_data.pop("new_goals", {})
    settings = config.load_settings()
    for key, val in new_goals.items():
        settings["goals"][key] = val
    config.save_settings(settings)
    logger.info(f"Цели обновлены — {_who(update)}: {new_goals}")

    g = settings["goals"]
    await update.message.reply_text(
        "<b>Цели сохранены:</b>\n"
        f"  Калории (цель): {g.get('calories', 'не задано')}\n"
        f"  Белок (мин): {g.get('protein', 'не задано')} г\n"
        f"  Сахар (макс): {g.get('max_sugar', 'не задано')} г\n"
        f"  Натрий (макс): {g.get('max_sodium', 'не задано')} мг",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def goals_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_goals", None)
    await update.message.reply_text("Настройка целей отменена.")
    return ConversationHandler.END


# ============================================================
# Google Sheets
# ============================================================

async def cmd_sheets_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return

    logger.info(f"/sheets_test — {_who(update)}")
    await update.message.reply_text("Проверяю подключение к Google Sheets...")

    try:
        result = await asyncio.to_thread(
            google_sheets.verify_connection,
            False,
            _who(update),
        )
    except google_sheets.GoogleSheetsConfigError as e:
        await update.message.reply_text(
            f"Google Sheets не настроен: {e}\n\n"
            "Добавь GOOGLE_SHEETS_SPREADSHEET_ID в .env и расшарь таблицу на service account."
        )
        return
    except Exception as e:
        logger.error(f"Ошибка Google Sheets для {_who(update)}: {e}")
        await update.message.reply_text(f"Ошибка Google Sheets: {e}")
        return

    await update.message.reply_text(
        "<b>Google Sheets подключён</b>\n\n"
        f"Таблица: {result['spreadsheet_title']}\n"
        f"Лист: {result['worksheet_title']}\n"
        f"Записан тест в диапазон: {result['updated_range']}\n"
        f"ID таблицы: <code>{result['spreadsheet_id']}</code>",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# Экспорт
# ============================================================

async def cmd_export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/export_excel {' '.join(context.args or [])} — {_who(update)}")
    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /export_excel YYYY-MM-DD YYYY-MM-DD\n"
            "Пример: /export_excel 2026-03-01 2026-03-20"
        )
        return
    try:
        start = parse_date(context.args[0])
        end = parse_date(context.args[1])
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    token, secret = await get_tokens(update)
    if not token:
        return

    days_data = await fetch_range(update, token, secret, start, end)
    if days_data is None:
        return

    settings = config.load_settings()
    await update.message.reply_text("Создаю Excel файл...")
    try:
        filepath = await asyncio.to_thread(
            exports.create_excel, days_data, start, end, settings.get("goals", {})
        )
        logger.info(f"Excel создан: {filepath.name}")
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=filepath.name,
                caption=f"Отчёт {formatters.fmt_date(start)} — {formatters.fmt_date(end)}",
            )
    except Exception as e:
        logger.error(f"Ошибка создания Excel: {e}")
        await update.message.reply_text(f"Ошибка при создании Excel: {e}")


async def cmd_export_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    logger.info(f"/export_pdf {' '.join(context.args or [])} — {_who(update)}")
    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /export_pdf YYYY-MM-DD YYYY-MM-DD\n"
            "Пример: /export_pdf 2026-03-01 2026-03-20"
        )
        return
    try:
        start = parse_date(context.args[0])
        end = parse_date(context.args[1])
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    token, secret = await get_tokens(update)
    if not token:
        return

    days_data = await fetch_range(update, token, secret, start, end)
    if days_data is None:
        return

    settings = config.load_settings()
    await update.message.reply_text("Создаю PDF файл...")
    try:
        filepath = await asyncio.to_thread(
            exports.create_pdf, days_data, start, end, settings.get("goals", {})
        )
        logger.info(f"PDF создан: {filepath.name}")
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=filepath.name,
                caption=f"Отчёт {formatters.fmt_date(start)} — {formatters.fmt_date(end)}",
            )
    except Exception as e:
        logger.error(f"Ошибка создания PDF: {e}")
        await update.message.reply_text(f"Ошибка при создании PDF: {e}")
