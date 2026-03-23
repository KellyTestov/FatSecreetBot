"""
Настройка логирования.

Логи пишутся одновременно в консоль и в файл logs/bot.log.
Файл ротируется автоматически: максимум 5 МБ, хранятся 5 файлов.

Формат строки лога:
  2026-03-20 14:23:01 | ИНФО     | Бот запущен и готов к работе
  2026-03-20 14:23:15 | ИНФО     | /today — @username
  2026-03-20 14:23:16 | ОШИБКА   | FatSecret: токен истёк
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGS_DIR = Path("logs")

_LEVEL_NAMES = {
    logging.DEBUG:    "DEBUG",
    logging.INFO:     "INFO",
    logging.WARNING:  "ATTENTION",
    logging.ERROR:    "ERROR",
    logging.CRITICAL: "CRITICAL",
}


class _RussianFormatter(logging.Formatter):
    """Форматтер с русскими названиями уровней."""

    def format(self, record: logging.LogRecord) -> str:
        record.level_ru = _LEVEL_NAMES.get(record.levelno, record.levelname).ljust(8)
        return super().format(record)


def setup_logging() -> None:
    """
    Инициализирует логирование. Вызывать один раз при старте бота.
    После вызова все модули пишут логи в одном стиле.
    """
    LOGS_DIR.mkdir(exist_ok=True)

    formatter = _RussianFormatter(
        fmt="%(asctime)s | %(level_ru)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- Файл (ротация: 5 МБ × 5 файлов) ---
    file_handler = RotatingFileHandler(
        LOGS_DIR / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # --- Консоль ---
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Глушим шумные библиотеки
    for noisy in ("httpx", "telegram", "urllib3", "requests", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
