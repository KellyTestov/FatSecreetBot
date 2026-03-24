"""
Точка входа. Запускает Telegram-бота.
"""
import logging
import warnings

# Убираем шумное предупреждение о версии urllib3/chardet от библиотеки requests
warnings.filterwarnings("ignore", message="urllib3.*", category=Warning)
warnings.filterwarnings("ignore", message=".*chardet.*", category=Warning)

from logger_setup import setup_logging

setup_logging()

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    Defaults,
    MessageHandler,
    filters,
)
from telegram.error import NetworkError, TimedOut

import config
import status_automation
from handlers import (
    # Auth
    cmd_auth, auth_verifier_handler, auth_cancel, AUTH_VERIFIER,
    # Goals
    cmd_set_goals, goals_calories, goals_protein, goals_sugar, goals_sodium, goals_cancel,
    GOALS_CALORIES, GOALS_PROTEIN, GOALS_SUGAR, GOALS_SODIUM,
    # Commands
    cmd_start, cmd_help,
    cmd_today, cmd_yesterday, cmd_day,
    cmd_period, cmd_last7, cmd_last14, cmd_last30,
    cmd_week, cmd_current_week,
    cmd_compare,
    cmd_top_products,
    cmd_settings, cmd_set_start_date,
    cmd_sheets_test,
    cmd_export_excel, cmd_export_pdf,
    cmd_menu, cmd_main_menu, cmd_dev_menu, cmd_hide_keyboard, handle_menu_button,
)

logger = logging.getLogger(__name__)


async def _post_init(app: Application):
    main_commands = [
        BotCommand("start", "Главный экран"),
        BotCommand("menu", "Показать клавиатуру"),
        BotCommand("help", "Все команды"),
        BotCommand("today", "Отчет за сегодня"),
        BotCommand("yesterday", "Отчет за вчера"),
        BotCommand("last7", "Последние 7 дней"),
        BotCommand("current_week", "Текущая неделя"),
        BotCommand("top_products", "Топ продуктов"),
        BotCommand("settings", "Настройки"),
        BotCommand("set_goals", "Цели питания"),
    ]
    await app.bot.set_my_commands(main_commands, scope=BotCommandScopeDefault())

    if config.ALLOWED_USER_ID:
        await app.bot.set_my_commands(
            [
                BotCommand("main_menu", "Основные кнопки"),
                BotCommand("dev_menu", "Команды разработчика"),
                BotCommand("sheets_test", "Проверить Google Sheets"),
                BotCommand("test_status_sync", "Тест записи Status"),
                BotCommand("test_weekly_pdf", "Выбрать неделю и получить weekly PDF"),
                BotCommand("color_status_zones", "Покрасить старые зоны"),
                BotCommand("test_appetite_prompt", "Тест вопроса про аппетит"),
                BotCommand("test_weight_prompt", "Тест вопроса про вес"),
                BotCommand("test_tirz_prompt", "Тест Тирзетты"),
                BotCommand("test_training_prompt", "Тест тренировки"),
                BotCommand("test_pool_prompt", "Тест бассейна"),
            ],
            scope=BotCommandScopeChat(chat_id=config.ALLOWED_USER_ID),
        )


def main():
    builder = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .defaults(Defaults(tzinfo=config.BOT_TIMEZONE))
        .post_init(_post_init)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
    )

    if config.PROXY_URL:
        builder = builder.proxy(config.PROXY_URL).get_updates_proxy(config.PROXY_URL)
        logger.info(f"Прокси включён: {config.PROXY_URL}")
    else:
        logger.info("Прокси не настроен (прямое подключение)")

    app = builder.build()

    # Диалог авторизации FatSecret
    auth_conv = ConversationHandler(
        entry_points=[CommandHandler("auth", cmd_auth)],
        states={
            AUTH_VERIFIER: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth_verifier_handler)],
        },
        fallbacks=[CommandHandler("cancel", auth_cancel)],
    )

    # Диалог настройки целей
    goals_conv = ConversationHandler(
        entry_points=[CommandHandler("set_goals", cmd_set_goals)],
        states={
            GOALS_CALORIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, goals_calories)],
            GOALS_PROTEIN:  [MessageHandler(filters.TEXT & ~filters.COMMAND, goals_protein)],
            GOALS_SUGAR:    [MessageHandler(filters.TEXT & ~filters.COMMAND, goals_sugar)],
            GOALS_SODIUM:   [MessageHandler(filters.TEXT & ~filters.COMMAND, goals_sodium)],
        },
        fallbacks=[CommandHandler("cancel", goals_cancel)],
    )

    app.add_handler(auth_conv)
    app.add_handler(goals_conv)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("main_menu", cmd_main_menu))
    app.add_handler(CommandHandler("dev_menu", cmd_dev_menu))
    app.add_handler(CommandHandler("hide_keyboard", cmd_hide_keyboard))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("yesterday", cmd_yesterday))
    app.add_handler(CommandHandler("day", cmd_day))
    app.add_handler(CommandHandler("period", cmd_period))
    app.add_handler(CommandHandler("last7", cmd_last7))
    app.add_handler(CommandHandler("last14", cmd_last14))
    app.add_handler(CommandHandler("last30", cmd_last30))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("current_week", cmd_current_week))
    app.add_handler(CommandHandler("compare", cmd_compare))
    app.add_handler(CommandHandler("top_products", cmd_top_products))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("set_start_date", cmd_set_start_date))
    app.add_handler(CommandHandler("sheets_test", cmd_sheets_test))
    app.add_handler(CommandHandler("export_excel", cmd_export_excel))
    app.add_handler(CommandHandler("export_pdf", cmd_export_pdf))
    status_automation.register_automation_handlers(app)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_button), group=1)
    status_automation.schedule_automation_jobs(app)

    logger.info("=" * 50)
    logger.info("Бот запущен и готов к работе")
    logger.info("=" * 50)
    try:
        app.run_polling(drop_pending_updates=True, bootstrap_retries=3)
    except TimedOut:
        logger.exception("Таймаут подключения к Telegram API при запуске.")
        logger.error(
            "Бот не смог подключиться к Telegram API. "
            "Если проблема повторяется, укажи PROXY_URL в .env или запусти через VPN."
        )
        raise
    except NetworkError:
        logger.exception("Сетевая ошибка подключения к Telegram API при запуске.")
        logger.error(
            "Бот не смог подключиться к Telegram API. "
            "Проверь интернет, прокси и доступ к api.telegram.org."
        )
        raise


if __name__ == "__main__":
    main()
