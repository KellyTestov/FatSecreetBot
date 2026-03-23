import asyncio
import logging
from datetime import date, datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import analytics
import automation_state
import config
import fatsecret
import google_sheets

logger = logging.getLogger(__name__)

TRAINING_WEEKDAYS = {1, 3, 5}  # Tue, Thu, Sat
POOL_WEEKDAY = 6  # Sun


def _check_access(update: Update) -> bool:
    if config.ALLOWED_USER_ID is None:
        return True
    return update.effective_user and update.effective_user.id == config.ALLOWED_USER_ID


def _parse_date_arg(args: list[str], default: date) -> date:
    if not args:
        return default
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(args[0], fmt).date()
        except ValueError:
            continue
    raise ValueError("Используй YYYY-MM-DD или DD.MM.YYYY")


def _date_label(target_date: date) -> str:
    return target_date.strftime("%d.%m.%Y")


def _week_boundary_day(today: date, start_date: date) -> bool:
    if today < start_date:
        return False
    return (today - start_date).days % 7 == 0


def _yes_no_keyboard(prefix: str, target_date: date) -> InlineKeyboardMarkup:
    iso = target_date.isoformat()
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Да", callback_data=f"{prefix}:yes:{iso}"),
                InlineKeyboardButton("Нет", callback_data=f"{prefix}:no:{iso}"),
            ]
        ]
    )


def _tirz_keyboard(target_date: date) -> InlineKeyboardMarkup:
    iso = target_date.isoformat()
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Поставил", callback_data=f"tirz:set:{iso}"),
                InlineKeyboardButton("Отложить на день", callback_data=f"tirz:delay:{iso}"),
            ]
        ]
    )


def _allowed_chat_id() -> int | None:
    return config.ALLOWED_USER_ID


def _pending_state() -> dict:
    state = automation_state.load_state()
    state = automation_state.ensure_initialized(state)
    return state


def _save_state(state: dict):
    automation_state.save_state(state)


def _fetch_day_totals(target_date: date) -> dict:
    token, secret = fatsecret.load_tokens()
    if not token or not secret:
        raise RuntimeError("Токены FatSecret не найдены. Используй /auth.")

    entries = fatsecret.get_entries_for_date(token, secret, target_date)
    return analytics.day_totals(entries or [])


async def sync_status_for_day(target_date: date) -> dict:
    totals = await asyncio.to_thread(_fetch_day_totals, target_date)
    return await asyncio.to_thread(google_sheets.record_daily_status, target_date, totals)


async def send_appetite_prompt_to_chat(bot, chat_id: int, target_date: date):
    sent = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"Оценка дня • {_date_label(target_date)}\n\n"
            "Какой сегодня был аппетит?\n"
            "Ответь одним сообщением. Можно коротко или подробно."
        ),
    )
    state = _pending_state()
    automation_state.add_pending_text_prompt(
        state,
        kind="appetite",
        target_date=target_date,
        message_id=sent.message_id,
    )
    state["last_appetite_prompt_date"] = target_date.isoformat()
    _save_state(state)


async def send_weight_prompt_to_chat(bot, chat_id: int, target_date: date):
    sent = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"Контроль веса • {_date_label(target_date)}\n\n"
            "Пришли текущий вес в кг.\n"
            "Пример: 98.4"
        ),
    )
    state = _pending_state()
    automation_state.add_pending_text_prompt(
        state,
        kind="weight",
        target_date=target_date,
        message_id=sent.message_id,
    )
    state["last_weight_prompt_date"] = target_date.isoformat()
    _save_state(state)


async def send_tirz_prompt_to_chat(bot, chat_id: int, target_date: date):
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"Тирзетта • {_date_label(target_date)}\n\n"
            "Отметь статус укола:"
        ),
        reply_markup=_tirz_keyboard(target_date),
    )
    state = _pending_state()
    state["pending_tirz_prompt_for"] = target_date.isoformat()
    _save_state(state)


async def send_training_prompt_to_chat(bot, chat_id: int, target_date: date):
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"Тренировка • {_date_label(target_date)}\n\n"
            "Сегодня был зал?"
        ),
        reply_markup=_yes_no_keyboard("gym", target_date),
    )
    state = _pending_state()
    state["last_training_prompt_date"] = target_date.isoformat()
    _save_state(state)


async def send_pool_prompt_to_chat(bot, chat_id: int, target_date: date):
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"Активность • {_date_label(target_date)}\n\n"
            "Сегодня был бассейн?"
        ),
        reply_markup=_yes_no_keyboard("pool", target_date),
    )
    state = _pending_state()
    state["last_pool_prompt_date"] = target_date.isoformat()
    _save_state(state)


async def job_daily_status_sync(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(config.BOT_TIMEZONE).date()
    target_date = today - timedelta(days=1)
    state = _pending_state()
    if state.get("last_daily_sync_date") == target_date.isoformat():
        return

    try:
        await sync_status_for_day(target_date)
        state["last_daily_sync_date"] = target_date.isoformat()
        _save_state(state)
        logger.info(f"Status sync completed for {target_date.isoformat()}")
    except Exception as exc:
        logger.error(f"Status sync failed for {target_date.isoformat()}: {exc}")


async def job_weight_prompt(context: ContextTypes.DEFAULT_TYPE):
    chat_id = _allowed_chat_id()
    if not chat_id:
        logger.warning("Automation skipped: TELEGRAM_ALLOWED_USER_ID is not set.")
        return

    today = datetime.now(config.BOT_TIMEZONE).date()
    state = _pending_state()

    settings = config.load_settings()
    start_date_raw = settings.get("start_date")
    if start_date_raw:
        start_date = date.fromisoformat(start_date_raw)
        if _week_boundary_day(today, start_date):
            if state.get("last_weight_prompt_date") != today.isoformat():
                await send_weight_prompt_to_chat(context.bot, chat_id, today)


async def job_tirz_prompt(context: ContextTypes.DEFAULT_TYPE):
    chat_id = _allowed_chat_id()
    if not chat_id:
        return

    today = datetime.now(config.BOT_TIMEZONE).date()
    state = _pending_state()
    next_tirz_raw = state.get("next_tirz_date")
    if not next_tirz_raw:
        return
    next_tirz_date = date.fromisoformat(next_tirz_raw)
    if today >= next_tirz_date and state.get("pending_tirz_prompt_for") != today.isoformat():
        await send_tirz_prompt_to_chat(context.bot, chat_id, today)


async def job_appetite_prompt(context: ContextTypes.DEFAULT_TYPE):
    chat_id = _allowed_chat_id()
    if not chat_id:
        return

    today = datetime.now(config.BOT_TIMEZONE).date()
    state = _pending_state()
    if state.get("last_appetite_prompt_date") == today.isoformat():
        return

    await send_appetite_prompt_to_chat(context.bot, chat_id, today)


async def _send_post_appetite_followups(bot, chat_id: int, target_date: date):
    state = _pending_state()

    if target_date.weekday() in TRAINING_WEEKDAYS and state.get("last_training_prompt_date") != target_date.isoformat():
        await send_training_prompt_to_chat(bot, chat_id, target_date)
        state = _pending_state()

    if target_date.weekday() == POOL_WEEKDAY and state.get("last_pool_prompt_date") != target_date.isoformat():
        await send_pool_prompt_to_chat(bot, chat_id, target_date)


async def handle_pending_text_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_access(update) or not update.message or not update.message.text:
        return

    reply_to_message_id = None
    if update.message.reply_to_message:
        reply_to_message_id = update.message.reply_to_message.message_id

    state = _pending_state()
    prompt = automation_state.pop_pending_text_prompt(state, reply_to_message_id)
    if not prompt:
        return

    target_date = date.fromisoformat(prompt["target_date"])
    text = update.message.text.strip()

    try:
        if prompt["kind"] == "appetite":
            await asyncio.to_thread(google_sheets.record_appetite, target_date, text)
            _save_state(state)
            await update.message.reply_text(
                f"Оценка аппетита за {_date_label(target_date)} сохранена."
            )
            await _send_post_appetite_followups(context.bot, update.effective_chat.id, target_date)
            return

        if prompt["kind"] == "weight":
            weight = float(text.replace(",", "."))
            await asyncio.to_thread(google_sheets.record_weight, target_date, weight)
            _save_state(state)
            await update.message.reply_text(
                f"Вес за {_date_label(target_date)} сохранён: {weight:.1f} кг."
            )
            return
    except ValueError:
        state.setdefault("pending_text_prompts", []).append(prompt)
        _save_state(state)
        await update.message.reply_text("Нужен формат числа. Например: 98.4")
        return
    except Exception as exc:
        state.setdefault("pending_text_prompts", []).append(prompt)
        _save_state(state)
        await update.message.reply_text(f"Ошибка сохранения: {exc}")
        return

    state.setdefault("pending_text_prompts", []).append(prompt)
    _save_state(state)


async def handle_automation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not _check_access(update):
        return

    await query.answer()
    parts = (query.data or "").split(":")
    if len(parts) != 3:
        return

    kind, action, iso_date = parts
    target_date = date.fromisoformat(iso_date)

    if kind == "tirz":
        state = _pending_state()
        if action == "set":
            await asyncio.to_thread(google_sheets.record_tirz, target_date, "Поставил")
            state["next_tirz_date"] = (target_date + timedelta(days=7)).isoformat()
            state["pending_tirz_prompt_for"] = None
            _save_state(state)
            await query.edit_message_text(
                f"Тирзетта • {_date_label(target_date)}\n\nСтатус: поставил."
            )
            return

        if action == "delay":
            state["next_tirz_date"] = (target_date + timedelta(days=1)).isoformat()
            state["pending_tirz_prompt_for"] = None
            _save_state(state)
            await query.edit_message_text(
                f"Тирзетта • {_date_label(target_date)}\n\nПеренесено на следующий день."
            )
            return

    if kind == "gym":
        value = "Да" if action == "yes" else "Нет"
        await asyncio.to_thread(google_sheets.record_activity, target_date, gym=value)
        await query.edit_message_text(
            f"Тренировка • {_date_label(target_date)}\n\nЗал: {value}."
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                f"Тренировка • {_date_label(target_date)}\n\n"
                "Кардио было?"
            ),
            reply_markup=_yes_no_keyboard("cardio", target_date),
        )
        return

    if kind == "cardio":
        value = "Да" if action == "yes" else "Нет"
        await asyncio.to_thread(google_sheets.record_activity, target_date, cardio=value)
        await query.edit_message_text(
            f"Тренировка • {_date_label(target_date)}\n\nКардио: {value}."
        )
        return

    if kind == "pool":
        value = "Да" if action == "yes" else "Нет"
        await asyncio.to_thread(google_sheets.record_activity, target_date, pool=value)
        await query.edit_message_text(
            f"Активность • {_date_label(target_date)}\n\nБассейн: {value}."
        )


async def cmd_test_status_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_access(update):
        return
    try:
        target_date = _parse_date_arg(context.args, datetime.now(config.BOT_TIMEZONE).date() - timedelta(days=1))
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    await update.message.reply_text(f"Синхронизирую Status за {_date_label(target_date)}...")
    try:
        await sync_status_for_day(target_date)
        await update.message.reply_text(f"Status за {_date_label(target_date)} обновлён.")
    except Exception as exc:
        await update.message.reply_text(f"Ошибка sync: {exc}")


async def cmd_test_appetite_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_access(update):
        return
    try:
        target_date = _parse_date_arg(context.args, datetime.now(config.BOT_TIMEZONE).date())
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    await send_appetite_prompt_to_chat(context.bot, update.effective_chat.id, target_date)


async def cmd_test_weight_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_access(update):
        return
    try:
        target_date = _parse_date_arg(context.args, datetime.now(config.BOT_TIMEZONE).date())
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    await send_weight_prompt_to_chat(context.bot, update.effective_chat.id, target_date)


async def cmd_test_tirz_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_access(update):
        return
    try:
        target_date = _parse_date_arg(context.args, datetime.now(config.BOT_TIMEZONE).date())
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    await send_tirz_prompt_to_chat(context.bot, update.effective_chat.id, target_date)


async def cmd_test_training_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_access(update):
        return
    try:
        target_date = _parse_date_arg(context.args, datetime.now(config.BOT_TIMEZONE).date())
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    await send_training_prompt_to_chat(context.bot, update.effective_chat.id, target_date)


async def cmd_test_pool_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_access(update):
        return
    try:
        target_date = _parse_date_arg(context.args, datetime.now(config.BOT_TIMEZONE).date())
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    await send_pool_prompt_to_chat(context.bot, update.effective_chat.id, target_date)


def register_automation_handlers(app):
    app.add_handler(CommandHandler("test_status_sync", cmd_test_status_sync))
    app.add_handler(CommandHandler("test_appetite_prompt", cmd_test_appetite_prompt))
    app.add_handler(CommandHandler("test_weight_prompt", cmd_test_weight_prompt))
    app.add_handler(CommandHandler("test_tirz_prompt", cmd_test_tirz_prompt))
    app.add_handler(CommandHandler("test_training_prompt", cmd_test_training_prompt))
    app.add_handler(CommandHandler("test_pool_prompt", cmd_test_pool_prompt))
    app.add_handler(CallbackQueryHandler(handle_automation_callback, pattern=r"^(tirz|gym|cardio|pool):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pending_text_prompt))


def schedule_automation_jobs(app):
    if app.job_queue is None:
        logger.warning("JobQueue is not available. Install APScheduler to enable automation.")
        return

    app.job_queue.run_daily(
        job_daily_status_sync,
        time=time(hour=5, minute=0, tzinfo=config.BOT_TIMEZONE),
        name="status_daily_sync",
    )
    app.job_queue.run_daily(
        job_appetite_prompt,
        time=time(hour=0, minute=0, tzinfo=config.BOT_TIMEZONE),
        name="status_appetite_prompt",
    )
    app.job_queue.run_daily(
        job_weight_prompt,
        time=time(hour=9, minute=30, tzinfo=config.BOT_TIMEZONE),
        name="status_weight_prompt",
    )
    app.job_queue.run_daily(
        job_tirz_prompt,
        time=time(hour=19, minute=0, tzinfo=config.BOT_TIMEZONE),
        name="status_tirz_prompt",
    )
