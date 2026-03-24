"""
FatSecret OAuth 1.0 авторизация и запросы к API.

Токены хранятся в tokens.json и загружаются автоматически.
Повторная авторизация нужна только если токен истёк.
"""
import json
import logging
from datetime import date, timedelta
from urllib.parse import parse_qs

import requests
from oauthlib.oauth1 import SIGNATURE_TYPE_BODY, SIGNATURE_TYPE_QUERY
from requests_oauthlib import OAuth1

import config

logger = logging.getLogger(__name__)


class TokenExpiredError(Exception):
    """Токен FatSecret истёк или недействителен."""
    pass


def date_to_int(d: date) -> int:
    """Переводит дату в количество дней с 1970-01-01 (формат FatSecret)."""
    return (d - date(1970, 1, 1)).days


def load_tokens() -> tuple[str | None, str | None]:
    """Загружает сохранённые токены. Возвращает (token, secret) или (None, None)."""
    if not config.TOKENS_FILE.exists():
        logger.info("FatSecret: файл токенов не найден")
        return None, None
    with open(config.TOKENS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info("FatSecret: токены загружены из файла")
    return data.get("access_token"), data.get("access_token_secret")


def save_tokens(access_token: str, access_token_secret: str):
    """Сохраняет токены в файл."""
    with open(config.TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"access_token": access_token, "access_token_secret": access_token_secret},
            f,
            indent=2,
        )
    logger.info("FatSecret: токены сохранены в файл")


def get_request_token() -> tuple[str, str, str]:
    """
    Шаг 1 OAuth: получить request token.
    Возвращает (request_token, request_token_secret, auth_url).
    """
    logger.info("Авторизация FatSecret: запрос request token")
    oauth = OAuth1(
        client_key=config.FATSECRET_CONSUMER_KEY,
        client_secret=config.FATSECRET_CONSUMER_SECRET,
        callback_uri="oob",
        signature_method="HMAC-SHA1",
        signature_type=SIGNATURE_TYPE_BODY,
        force_include_body=True,
    )
    resp = requests.post(config.REQUEST_TOKEN_URL, data={}, auth=oauth, timeout=30)
    if resp.status_code != 200:
        logger.error(f"Авторизация FatSecret: не удалось получить request token ({resp.status_code})")
        raise RuntimeError(f"Ошибка получения request token: {resp.text}")

    token_data = parse_qs(resp.text)
    request_token = token_data["oauth_token"][0]
    request_token_secret = token_data["oauth_token_secret"][0]
    auth_url = f"{config.AUTHORIZE_URL}?oauth_token={request_token}"
    logger.info("Авторизация FatSecret: request token получен, ссылка отправлена пользователю")
    return request_token, request_token_secret, auth_url


def get_access_token(request_token: str, request_token_secret: str, verifier: str) -> tuple[str, str]:
    """
    Шаг 2 OAuth: обменять verifier на access token.
    Возвращает (access_token, access_token_secret).
    """
    oauth = OAuth1(
        client_key=config.FATSECRET_CONSUMER_KEY,
        client_secret=config.FATSECRET_CONSUMER_SECRET,
        resource_owner_key=request_token,
        resource_owner_secret=request_token_secret,
        verifier=verifier,
        signature_method="HMAC-SHA1",
        signature_type=SIGNATURE_TYPE_QUERY,
    )
    logger.info("Авторизация FatSecret: обмен verifier на access token")
    resp = requests.get(config.ACCESS_TOKEN_URL, auth=oauth, timeout=30)
    if resp.status_code != 200:
        logger.error(f"Авторизация FatSecret: не удалось получить access token ({resp.status_code})")
        raise RuntimeError(f"Ошибка получения access token: {resp.text}")

    data = parse_qs(resp.text)
    logger.info("Авторизация FatSecret: успешно, токены сохранены")
    return data["oauth_token"][0], data["oauth_token_secret"][0]


def _make_oauth(access_token: str, access_token_secret: str) -> OAuth1:
    return OAuth1(
        client_key=config.FATSECRET_CONSUMER_KEY,
        client_secret=config.FATSECRET_CONSUMER_SECRET,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
        signature_method="HMAC-SHA1",
        signature_type=SIGNATURE_TYPE_QUERY,
    )


def get_entries_for_date(access_token: str, access_token_secret: str, d: date) -> list:
    """
    Получает записи питания за конкретный день.
    Возвращает список записей (пустой список если записей нет).
    Бросает TokenExpiredError если токен истёк.
    """
    logger.info(f"FatSecret: запрос данных за {d.strftime('%d.%m.%Y')}")
    oauth = _make_oauth(access_token, access_token_secret)
    resp = requests.get(
        config.FOOD_ENTRIES_URL,
        params={"date": date_to_int(d), "format": "json"},
        auth=oauth,
        timeout=30,
    )

    if resp.status_code != 200:
        text = resp.text
        if any(x in text for x in ["Invalid access token", "Invalid oauth", "oauth_problem", "Token expired"]):
            logger.warning("FatSecret: токен истёк или недействителен")
            raise TokenExpiredError("FatSecret access token истёк или недействителен")
        logger.error(f"FatSecret: ошибка API {resp.status_code}: {text[:200]}")
        raise RuntimeError(f"FatSecret API ошибка {resp.status_code}: {text}")

    data = resp.json()
    # data.get("food_entries") может вернуть None если записей нет — используем "or {}" вместо дефолта
    entries = (data.get("food_entries") or {}).get("food_entry", [])

    # FatSecret возвращает одну запись как dict, а не list — исправляем
    if isinstance(entries, dict):
        entries = [entries]

    entries = entries or []
    if entries:
        logger.info(f"FatSecret: получено {len(entries)} записей за {d.strftime('%d.%m.%Y')}")
    else:
        logger.info(f"FatSecret: нет записей за {d.strftime('%d.%m.%Y')}")
    return entries


def get_entries_for_range(access_token: str, access_token_secret: str, start: date, end: date) -> dict:
    """
    Получает записи питания за диапазон дат.
    Возвращает {date: [entries]} для всех дат в диапазоне.
    Бросает TokenExpiredError если токен истёк.
    """
    result = {}
    current = start
    logger.info(f"FatSecret: начинаю загрузку диапазона {start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}")
    while current <= end:
        entries = get_entries_for_date(access_token, access_token_secret, current)
        result[current] = entries
        current += timedelta(days=1)
    logger.info(f"FatSecret: диапазон {start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')} загружен")
    return result
