import json
import os
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs

import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1
from oauthlib.oauth1 import SIGNATURE_TYPE_BODY, SIGNATURE_TYPE_QUERY

load_dotenv()

CONSUMER_KEY = os.getenv("FATSECRET_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("FATSECRET_CONSUMER_SECRET")
CALLBACK_URI = os.getenv("FATSECRET_CALLBACK", "oob")

REQUEST_TOKEN_URL = "https://authentication.fatsecret.com/oauth/request_token"
AUTHORIZE_URL = "https://authentication.fatsecret.com/oauth/authorize"
ACCESS_TOKEN_URL = "https://authentication.fatsecret.com/oauth/access_token"
FOOD_ENTRIES_URL = "https://platform.fatsecret.com/rest/food-entries/v1"

TOKENS_FILE = Path("tokens.json")

if not CONSUMER_KEY or not CONSUMER_SECRET:
    raise ValueError("Проверь .env: нет FATSECRET_CONSUMER_KEY или FATSECRET_CONSUMER_SECRET")


def get_days_since_1970() -> int:
    return int(time.time() // 86400)


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load_saved_tokens():
    if not TOKENS_FILE.exists():
        return None, None

    with open(TOKENS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("access_token"), data.get("access_token_secret")


def save_tokens(access_token: str, access_token_secret: str):
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "access_token": access_token,
                "access_token_secret": access_token_secret,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def authorize_and_get_tokens():
    print("Сохраненных токенов нет. Запускаю авторизацию...")

    oauth_request = OAuth1(
        client_key=CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        callback_uri=CALLBACK_URI,
        signature_method="HMAC-SHA1",
        signature_type=SIGNATURE_TYPE_BODY,
        force_include_body=True,
    )

    resp = requests.post(
        REQUEST_TOKEN_URL,
        data={},
        auth=oauth_request,
        timeout=30,
    )

    print("Request token status:", resp.status_code)
    if resp.status_code != 200:
        print(resp.text)
        raise RuntimeError("Не удалось получить request token")

    token_data = parse_qs(resp.text)
    request_token = token_data.get("oauth_token", [None])[0]
    request_token_secret = token_data.get("oauth_token_secret", [None])[0]

    if not request_token or not request_token_secret:
        raise RuntimeError("FatSecret не вернул oauth_token / oauth_token_secret")

    auth_url = f"{AUTHORIZE_URL}?oauth_token={request_token}"
    print("Открываю браузер для авторизации...")
    webbrowser.open(auth_url)

    verifier = input("После входа вставь сюда oauth_verifier: ").strip()
    if not verifier:
        raise RuntimeError("oauth_verifier пустой")

    oauth_access = OAuth1(
        client_key=CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=request_token,
        resource_owner_secret=request_token_secret,
        verifier=verifier,
        signature_method="HMAC-SHA1",
        signature_type=SIGNATURE_TYPE_QUERY,
    )

    resp = requests.get(
        ACCESS_TOKEN_URL,
        auth=oauth_access,
        timeout=30,
    )

    print("Access token status:", resp.status_code)
    if resp.status_code != 200:
        print(resp.text)
        raise RuntimeError("Не удалось получить access token")

    access_data = parse_qs(resp.text)
    access_token = access_data.get("oauth_token", [None])[0]
    access_token_secret = access_data.get("oauth_token_secret", [None])[0]

    if not access_token or not access_token_secret:
        raise RuntimeError("FatSecret не вернул access token / secret")

    save_tokens(access_token, access_token_secret)
    print("Токены сохранены в tokens.json")

    return access_token, access_token_secret


def get_food_entries(access_token: str, access_token_secret: str):
    oauth_api = OAuth1(
        client_key=CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
        signature_method="HMAC-SHA1",
        signature_type=SIGNATURE_TYPE_QUERY,
    )

    resp = requests.get(
        FOOD_ENTRIES_URL,
        params={"date": get_days_since_1970(), "format": "json"},
        auth=oauth_api,
        timeout=30,
    )

    return resp


def print_day_report(entries):
    if not entries:
        print("За этот день записей нет.")
        return

    total_calories = 0.0
    total_protein = 0.0
    total_fat = 0.0
    total_carbs = 0.0

    current_meal = None

    for entry in entries:
        meal = entry.get("meal", "Unknown")
        name = entry.get("food_entry_name", "Без названия")
        calories = to_float(entry.get("calories"))
        protein = to_float(entry.get("protein"))
        fat = to_float(entry.get("fat"))
        carbs = to_float(entry.get("carbohydrate"))

        if meal != current_meal:
            current_meal = meal
            print(f"\n=== {meal} ===")

        print(f"- {name}")
        print(
            f"  Калории: {calories:.2f} | "
            f"Белки: {protein:.2f} | "
            f"Жиры: {fat:.2f} | "
            f"Углеводы: {carbs:.2f}"
        )

        total_calories += calories
        total_protein += protein
        total_fat += fat
        total_carbs += carbs

    print("\n=== ИТОГО ЗА ДЕНЬ ===")
    print(f"Калории: {total_calories:.2f}")
    print(f"Белки: {total_protein:.2f}")
    print(f"Жиры: {total_fat:.2f}")
    print(f"Углеводы: {total_carbs:.2f}")


def main():
    access_token, access_token_secret = load_saved_tokens()

    if not access_token or not access_token_secret:
        access_token, access_token_secret = authorize_and_get_tokens()
    else:
        print("Найдены сохраненные токены. Пробую использовать их без логина...")

    resp = get_food_entries(access_token, access_token_secret)

    if resp.status_code != 200:
        print("Первый запрос не удался:")
        print(resp.text)

        if "Invalid access token" in resp.text:
            print("Токен недействителен. Повторная авторизация...")
            access_token, access_token_secret = authorize_and_get_tokens()
            resp = get_food_entries(access_token, access_token_secret)

    print("Food entries status:", resp.status_code)
    if resp.status_code != 200:
        print(resp.text)
        raise RuntimeError("Не удалось получить food entries")

    data = resp.json()
    food_entries = data.get("food_entries", {}).get("food_entry", [])

    if isinstance(food_entries, dict):
        food_entries = [food_entries]

    print_day_report(food_entries)


if __name__ == "__main__":
    main()