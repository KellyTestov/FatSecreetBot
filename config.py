import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Нет TELEGRAM_BOT_TOKEN в .env")

# Опционально: ограничить доступ к боту только одному пользователю.
# Добавь в .env строку: TELEGRAM_ALLOWED_USER_ID=123456789
# Узнать свой ID можно у бота @userinfobot
ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID")
if ALLOWED_USER_ID:
    ALLOWED_USER_ID = int(ALLOWED_USER_ID)

# --- FatSecret ---
FATSECRET_CONSUMER_KEY = os.getenv("FATSECRET_CONSUMER_KEY")
FATSECRET_CONSUMER_SECRET = os.getenv("FATSECRET_CONSUMER_SECRET")
if not FATSECRET_CONSUMER_KEY or not FATSECRET_CONSUMER_SECRET:
    raise ValueError("Нет FATSECRET_CONSUMER_KEY или FATSECRET_CONSUMER_SECRET в .env")

# --- FatSecret API URLs ---
REQUEST_TOKEN_URL = "https://authentication.fatsecret.com/oauth/request_token"
AUTHORIZE_URL = "https://authentication.fatsecret.com/oauth/authorize"
ACCESS_TOKEN_URL = "https://authentication.fatsecret.com/oauth/access_token"
FOOD_ENTRIES_URL = "https://platform.fatsecret.com/rest/food-entries/v1"

# --- Прокси (опционально, нужен если Telegram заблокирован) ---
# Примеры: socks5://127.0.0.1:1080  или  http://127.0.0.1:8080
PROXY_URL = os.getenv("PROXY_URL") or None

# --- Хранилище ---
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "."))
DATA_DIR = STORAGE_DIR / "data"

# --- Пути к файлам ---
TOKENS_FILE = DATA_DIR / "tokens.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
EXPORTS_DIR = STORAGE_DIR / "exports_output"
GOOGLE_SERVICE_ACCOUNT_FILE = Path(
    os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(DATA_DIR / "google_service_account.json"))
)
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
GOOGLE_SHEETS_WORKSHEET = os.getenv("GOOGLE_SHEETS_WORKSHEET", "BotLogs")
STATUS_WORKSHEET = os.getenv("GOOGLE_STATUS_WORKSHEET", "Status")
AUTOMATION_STATE_FILE = DATA_DIR / "automation_state.json"
BOT_TIMEZONE_NAME = os.getenv("BOT_TIMEZONE", "Europe/Moscow")
BOT_TIMEZONE = ZoneInfo(BOT_TIMEZONE_NAME)


def ensure_storage_dirs():
    """Гарантирует наличие директорий для runtime-файлов."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


ensure_storage_dirs()


def load_settings() -> dict:
    """Загружает настройки пользователя из файла."""
    if not SETTINGS_FILE.exists():
        return {
            "start_date": None,
            "goals": {
                "calories": None,
                "protein": None,
                "max_sugar": None,
                "max_sodium": None,
            },
        }
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Гарантируем наличие всех ключей
    if "goals" not in data:
        data["goals"] = {"calories": None, "protein": None, "max_sugar": None, "max_sodium": None}
    return data


def save_settings(settings: dict):
    """Сохраняет настройки пользователя в файл."""
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
