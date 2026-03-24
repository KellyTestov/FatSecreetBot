"""
Все обработчики команд Telegram-бота.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import analytics
import config
import exports
import fatsecret
import formatters
import google_sheets

logger = logging.getLogger(__name__)

BTN_MAIN = "Основные"
BTN_DEV = "Команды разработчика"
BTN_BACK = "Назад"
BTN_HELP = "Помощь"
BTN_TODAY = "Сегодня"
BTN_YESTERDAY = "Вчера"
BTN_LAST7 = "Последние 7 дней"
BTN_LAST30 = "Последние 30 дней"
BTN_CURRENT_WEEK = "Текущая неделя"
BTN_TOP_PRODUCTS = "Топ продуктов"
BTN_SETTINGS = "Настройки"
BTN_SET_GOALS = "Цели питания"
BTN_SET_START_DATE = "Дата старта"
BTN_AUTH = "Подключить FatSecret"
BTN_COMPLEX = "Сложные команды"
BTN_EXPORTS = "Экспорт"
BTN_DAY = "Отчет за дату"
BTN_PERIOD = "Отчет за период"
BTN_WEEK = "Неделя похудения"
BTN_COMPARE = "Сравнить периоды"
BTN_EXPORT_EXCEL = "Экспорт Excel"
BTN_EXPORT_PDF = "Экспорт PDF"
BTN_SHEETS_TEST = "Проверить Sheets"
BTN_TEST_STATUS_SYNC = "Тест Status sync"
BTN_TEST_APPETITE = "Тест аппетита"
BTN_TEST_WEIGHT = "Тест веса"
BTN_TEST_TIRZ = "Тест Тирзетты"
BTN_TEST_TRAINING = "Тест тренировки"
BTN_TEST_POOL = "Тест бассейна"
BTN_COLOR_ZONES = "Покрасить старые зоны"


def _root_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_MAIN), KeyboardButton(BTN_DEV)],
            [KeyboardButton(BTN_HELP)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери раздел",
    )


def _main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_TODAY), KeyboardButton(BTN_YESTERDAY)],
            [KeyboardButton(BTN_LAST7), KeyboardButton(BTN_LAST30)],
            [KeyboardButton(BTN_CURRENT_WEEK), KeyboardButton(BTN_TOP_PRODUCTS)],
            [KeyboardButton(BTN_SETTINGS), KeyboardButton(BTN_SET_GOALS)],
            [KeyboardButton(BTN_AUTH), KeyboardButton(BTN_COMPLEX)],
            [KeyboardButton(BTN_EXPORTS), KeyboardButton(BTN_BACK)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери основную команду",
    )


def _complex_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_DAY), KeyboardButton(BTN_PERIOD)],
            [KeyboardButton(BTN_WEEK), KeyboardButton(BTN_COMPARE)],
            [KeyboardButton(BTN_SET_START_DATE), KeyboardButton(BTN_BACK)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери сценарий",
    )


def _exports_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_EXPORT_EXCEL), KeyboardButton(BTN_EXPORT_PDF)],
            [KeyboardButton(BTN_BACK)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери экспорт",
    )


def _dev_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_SHEETS_TEST), KeyboardButton(BTN_TEST_STATUS_SYNC)],
            [KeyboardButton(BTN_TEST_APPETITE), KeyboardButton(BTN_TEST_WEIGHT)],
            [KeyboardButton(BTN_TEST_TIRZ), KeyboardButton(BTN_TEST_TRAINING)],
            [KeyboardButton(BTN_TEST_POOL), KeyboardButton(BTN_COLOR_ZONES)],
            [KeyboardButton(BTN_BACK)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери команду разработчика",
    )


def _menu_text() -> str:
    return (
        "<b>Меню бота</b>\n\n"
        f"• <b>{BTN_MAIN}</b> — питание, аналитика, настройки и экспорт\n"
        f"• <b>{BTN_DEV}</b> — тесты автоматизации и Google Sheets\n\n"
        "Сложные сценарии тоже доступны из кнопок: бот подскажет готовую команду и формат даты."
    )


def _main_section_text() -> str:
    return (
        "<b>Основные команды</b>\n\n"
        f"• <b>{BTN_TODAY}</b> и <b>{BTN_YESTERDAY}</b> — быстрый отчет за день\n"
        f"• <b>{BTN_LAST7}</b>, <b>{BTN_LAST30}</b>, <b>{BTN_CURRENT_WEEK}</b> — готовые периоды\n"
        f"• <b>{BTN_TOP_PRODUCTS}</b> — лидеры по еде за последние 30 дней\n"
        f"• <b>{BTN_SETTINGS}</b>, <b>{BTN_SET_GOALS}</b>, <b>{BTN_AUTH}</b> — настройка бота\n"
        f"• <b>{BTN_COMPLEX}</b> и <b>{BTN_EXPORTS}</b> — подсказки по командам с датами"
    )


def _dev_section_text() -> str:
    return (
        "<b>Команды разработчика</b>\n\n"
        f"• <b>{BTN_SHEETS_TEST}</b> — проверка подключения к Google Sheets\n"
        f"• <b>{BTN_TEST_STATUS_SYNC}</b> — тест записи статуса за вчера\n"
        f"• <b>{BTN_COLOR_ZONES}</b> — ретро-окраска старых строк Status\n"
        f"• Остальные кнопки — тесты ежедневных и еженедельных автоматизаций"
    )


async def _reply_with_menu(update: Update, text: str, keyboard: ReplyKeyboardMarkup):
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


def _log_user_event(update: Update, action: str, details: str | None = None):
    suffix = f": {details}" if details else ""
    logger.info(f"{action} — {_who(update)}{suffix}")


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
    _log_user_event(update, "/start")
    token, _ = fatsecret.load_tokens()
    status = "Токены FatSecret: найдены" if token else "Токены FatSecret: не найдены, нажми «Подключить FatSecret»"
    sheets_status = (
        "Google Sheets: настроен"
        if config.GOOGLE_SHEETS_SPREADSHEET_ID
        else "Google Sheets: не настроен, добавь GOOGLE_SHEETS_SPREADSHEET_ID"
    )
    automation_status = (
        "Автоматизация Status: активна"
        if config.ALLOWED_USER_ID and config.GOOGLE_SHEETS_SPREADSHEET_ID
        else "Автоматизация Status: проверь TELEGRAM_ALLOWED_USER_ID и GOOGLE_SHEETS_SPREADSHEET_ID"
    )
    await update.message.reply_text(
        "<b>FatSecret Analytics Bot</b>\n\n"
        "Бот собирает аналитику из FatSecret, пишет статус в Google Sheets и напоминает про ежедневные действия.\n\n"
        f"{status}\n"
        f"{sheets_status}\n"
        f"{automation_status}\n\n"
        "Выбери раздел кнопками ниже. Полный список slash-команд доступен в /help.",
        parse_mode=ParseMode.HTML,
        reply_markup=_root_keyboard(),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    _log_user_event(update, "/help")
    text = (
        "<b>Команды бота</b>\n\n"
        "<b>Быстрые кнопки:</b>\n"
        f"• {BTN_MAIN} — основное меню\n"
        f"• {BTN_DEV} — меню тестов и техкоманд\n\n"
        "<b>Основные slash-команды:</b>\n"
        "• /today — сегодня\n"
        "• /yesterday — вчера\n"
        "• /day 2026-03-20 — конкретный день\n"
        "• /period 2026-03-01 2026-03-20 — период\n"
        "• /last7, /last14, /last30 — готовые периоды\n"
        "• /week 3, /current_week — недели похудения\n"
        "• /compare start1 end1 start2 end2 — сравнение периодов\n"
        "• /top_products [start end sort] — топ продуктов\n"
        "• /settings, /set_start_date, /set_goals — настройки\n"
        "• /export_excel start end, /export_pdf start end — экспорт\n\n"
        "<b>Команды разработчика:</b>\n"
        "• /sheets_test — проверка Google Sheets\n"
        "• /test_status_sync [дата]\n"
        "• /color_status_zones [дата] [дата]\n"
        "• /test_appetite_prompt [дата]\n"
        "• /test_weight_prompt [дата]\n"
        "• /test_tirz_prompt [дата]\n"
        "• /test_training_prompt [дата]\n"
        "• /test_pool_prompt [дата]"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=_root_keyboard())


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
    _log_user_event(update, "/settings")
    settings = config.load_settings()
    text = formatters.format_settings(settings)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_set_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    _log_user_event(update, "/set_start_date", " ".join(context.args or []))
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
    _log_user_event(update, "/set_goals")
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
    logger.info(f"Цели питания: получен шаг по калориям от {_who(update)}: {text}")
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
    logger.info(f"Цели питания: получен шаг по белку от {_who(update)}: {text}")
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
    logger.info(f"Цели питания: получен шаг по сахару от {_who(update)}: {text}")
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
    logger.info(f"Цели питания: получен шаг по натрию от {_who(update)}: {text}")
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
    _log_user_event(update, "/cancel", "диалог целей питания")
    await update.message.reply_text("Настройка целей отменена.")
    return ConversationHandler.END


# ============================================================
# Google Sheets
# ============================================================

async def cmd_sheets_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return

    _log_user_event(update, "/sheets_test")
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
    logger.info(f"Google Sheets: ручная проверка успешно завершена для {_who(update)}")


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


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    _log_user_event(update, "/menu")
    await _reply_with_menu(update, _menu_text(), _root_keyboard())


async def cmd_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    _log_user_event(update, "/main_menu")
    await _reply_with_menu(update, _main_section_text(), _main_keyboard())


async def cmd_dev_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    _log_user_event(update, "/dev_menu")
    await _reply_with_menu(update, _dev_section_text(), _dev_keyboard())


async def cmd_hide_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update):
        return
    _log_user_event(update, "/hide_keyboard")
    await update.effective_message.reply_text(
        "Клавиатура скрыта. Вернуть ее можно командами /start или /menu.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update) or not update.message or not update.message.text:
        return

    from status_automation import (
        cmd_color_status_zones,
        cmd_test_appetite_prompt,
        cmd_test_pool_prompt,
        cmd_test_status_sync,
        cmd_test_tirz_prompt,
        cmd_test_training_prompt,
        cmd_test_weight_prompt,
    )

    text = update.message.text.strip()
    _log_user_event(update, "Кнопка меню", text)

    direct_actions = {
        BTN_TODAY: cmd_today,
        BTN_YESTERDAY: cmd_yesterday,
        BTN_LAST7: cmd_last7,
        BTN_LAST30: cmd_last30,
        BTN_CURRENT_WEEK: cmd_current_week,
        BTN_TOP_PRODUCTS: cmd_top_products,
        BTN_SETTINGS: cmd_settings,
        BTN_SHEETS_TEST: cmd_sheets_test,
        BTN_TEST_STATUS_SYNC: cmd_test_status_sync,
        BTN_TEST_APPETITE: cmd_test_appetite_prompt,
        BTN_TEST_WEIGHT: cmd_test_weight_prompt,
        BTN_TEST_TIRZ: cmd_test_tirz_prompt,
        BTN_TEST_TRAINING: cmd_test_training_prompt,
        BTN_TEST_POOL: cmd_test_pool_prompt,
        BTN_COLOR_ZONES: cmd_color_status_zones,
        BTN_HELP: cmd_help,
    }
    if text in direct_actions:
        await direct_actions[text](update, context)
        return

    if text == BTN_MAIN:
        await _reply_with_menu(update, _main_section_text(), _main_keyboard())
        return

    if text == BTN_DEV:
        await _reply_with_menu(update, _dev_section_text(), _dev_keyboard())
        return

    if text == BTN_COMPLEX:
        await _reply_with_menu(
            update,
            (
                "<b>Сложные команды</b>\n\n"
                "Здесь собраны сценарии, где нужно указать даты или номер недели. "
                "Нажми нужную кнопку, и бот подскажет готовый формат."
            ),
            _complex_keyboard(),
        )
        return

    if text == BTN_AUTH:
        await update.message.reply_text(
            "<b>Подключение FatSecret</b>\n\nЗапусти команду:\n<code>/auth</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if text == BTN_SET_GOALS:
        await update.message.reply_text(
            "<b>Цели питания</b>\n\nЗапусти команду:\n<code>/set_goals</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if text == BTN_EXPORTS:
        await _reply_with_menu(
            update,
            (
                "<b>Экспорт</b>\n\n"
                "Выбери формат. Для экспорта нужен диапазон дат, бот покажет готовый шаблон команды."
            ),
            _exports_keyboard(),
        )
        return

    if text == BTN_BACK:
        await _reply_with_menu(update, _menu_text(), _root_keyboard())
        return

    templates = {
        BTN_DAY: (
            "<b>Отчет за дату</b>\n\n"
            "Команда:\n<code>/day 2026-03-20</code>\n\n"
            "Можно использовать и формат <code>20.03.2026</code>."
        ),
        BTN_PERIOD: (
            "<b>Отчет за период</b>\n\n"
            "Команда:\n<code>/period 2026-03-01 2026-03-20</code>"
        ),
        BTN_WEEK: (
            "<b>Неделя похудения</b>\n\n"
            "Команда:\n<code>/week 4</code>\n\n"
            "Текущая неделя:\n<code>/current_week</code>"
        ),
        BTN_COMPARE: (
            "<b>Сравнение периодов</b>\n\n"
            "Команда:\n<code>/compare 2026-03-01 2026-03-07 2026-03-08 2026-03-14</code>"
        ),
        BTN_SET_START_DATE: (
            "<b>Дата старта похудения</b>\n\n"
            "Команда:\n<code>/set_start_date 2026-02-26</code>"
        ),
        BTN_EXPORT_EXCEL: (
            "<b>Экспорт в Excel</b>\n\n"
            "Команда:\n<code>/export_excel 2026-03-01 2026-03-20</code>"
        ),
        BTN_EXPORT_PDF: (
            "<b>Экспорт в PDF</b>\n\n"
            "Команда:\n<code>/export_pdf 2026-03-01 2026-03-20</code>"
        ),
    }
    if text in templates:
        await update.message.reply_text(templates[text], parse_mode=ParseMode.HTML)
