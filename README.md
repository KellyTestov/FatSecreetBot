# FatSecreetBot

Telegram-бот для аналитики питания на базе FatSecret с автоматической выгрузкой в Google Sheets.

Бот умеет:
- получать дневные и периодические отчёты из FatSecret
- считать калории, белок, жиры, углеводы и клетчатку
- экспортировать отчёты в `Excel` и `PDF`
- автоматически заполнять лист `Status` в Google Sheets
- задавать ежедневные и недельные вопросы в Telegram и сохранять ответы в таблицу

## Что умеет бот

### FatSecret
- `/auth` для авторизации
- `/today`, `/yesterday`, `/day`
- `/period`, `/last7`, `/last14`, `/last30`
- `/week`, `/current_week`
- `/compare`
- `/top_products`
- `/export_excel`, `/export_pdf`

### Google Sheets
- проверка подключения через `/sheets_test`
- запись питания в лист `Status`
- запись веса, аппетита, статуса укола и тренировок

### Автоматизация `Status`
- `00:00` вопрос про аппетит за текущий день
- после ответа на аппетит:
  - во вторник, четверг, субботу бот спрашивает про `Зал` и `Кардио`
  - в воскресенье бот спрашивает про `Бассейн`
- `05:00` запись питания за предыдущий день в Google Sheets
- `09:30` вопрос про вес в день окончания очередной недели похудения
- `19:00` вопрос про Тирзетту в нужный день

Все времена работают в таймзоне `Europe/Moscow`, если не переопределить это через `.env`.

## Структура проекта

- [bot.py](./bot.py) — запуск Telegram-бота
- [handlers.py](./handlers.py) — основные Telegram-команды
- [status_automation.py](./status_automation.py) — расписание и автоматические сценарии
- [fatsecret.py](./fatsecret.py) — авторизация и запросы к FatSecret
- [google_sheets.py](./google_sheets.py) — работа с Google Sheets
- [analytics.py](./analytics.py) — расчёт нутриентов и аналитика
- [exports.py](./exports.py) — экспорт в `Excel` и `PDF`
- [config.py](./config.py) — конфигурация проекта

## Требования

- Python `3.11+`
- Telegram Bot Token
- FatSecret API credentials
- Google service account с доступом к нужной таблице

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Настройка `.env`

Создай `.env` в корне проекта:

```env
FATSECRET_CONSUMER_KEY=your_fatsecret_key
FATSECRET_CONSUMER_SECRET=your_fatsecret_secret
FATSECRET_CALLBACK=oob

TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_ALLOWED_USER_ID=123456789

# Если Telegram недоступен напрямую:
# PROXY_URL=socks5://127.0.0.1:1080

GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_SHEETS_WORKSHEET=BotLogs
GOOGLE_STATUS_WORKSHEET=Status
BOT_TIMEZONE=Europe/Moscow
```

## Настройка Google Sheets

### 1. Service account key

Положи JSON-ключ сюда:

`data/google_service_account.json`

Либо укажи другой путь через:

```env
GOOGLE_SERVICE_ACCOUNT_FILE=path/to/google_service_account.json
```

### 2. Включи Google Sheets API

Нужно включить `Google Sheets API` в проекте Google Cloud.

### 3. Расшарь таблицу

Выдай доступ редактора сервисному аккаунту, например:

`fatsecretagent@your-project.iam.gserviceaccount.com`

### 4. Укажи ID таблицы

Если ссылка на таблицу выглядит так:

```text
https://docs.google.com/spreadsheets/d/1rHs0hcDdW5XnWrwIEecxaB4G8e1tqSdx2tLyXGAYaY0/edit
```

то `GOOGLE_SHEETS_SPREADSHEET_ID` будет:

```env
GOOGLE_SHEETS_SPREADSHEET_ID=1rHs0hcDdW5XnWrwIEecxaB4G8e1tqSdx2tLyXGAYaY0
```

## Формат листа `Status`

Лист должен содержать колонки:

```text
Дата | Вес (кг) | Калории | Белок (г) | Углеводы (г) | Клетчатка (г) | Жиры (г) | Аппетит / ощущения | Тирзетта | Зал | Бассейн | Кардио
```

Лучше заранее создать внутри таблицы Google Sheets запас пустых строк, если ты используешь именно новый компонент `Таблица` от Google, а не обычный диапазон ячеек.

## Первый запуск

### 1. Авторизуй FatSecret

```powershell
.\.venv\Scripts\python.exe bot.py
```

Дальше в Telegram:

```text
/auth
```

### 2. Проверь Google Sheets

В Telegram:

```text
/sheets_test
```

Или локально:

```powershell
.\.venv\Scripts\python.exe check_google_sheets.py
```

## Полезные команды

### Основные

- `/start`
- `/help`
- `/settings`
- `/set_start_date YYYY-MM-DD`
- `/set_goals`

### Отчёты

- `/today`
- `/yesterday`
- `/day 2026-03-20`
- `/period 2026-03-01 2026-03-20`
- `/last7`
- `/last14`
- `/last30`
- `/week 4`
- `/current_week`
- `/compare 2026-03-01 2026-03-07 2026-03-08 2026-03-14`
- `/top_products`

### Экспорт

- `/export_excel 2026-03-01 2026-03-20`
- `/export_pdf 2026-03-01 2026-03-20`

### Тестирование автоматизации

- `/test_status_sync 2026-03-20`
- `/test_appetite_prompt 2026-03-20`
- `/test_weight_prompt 2026-03-20`
- `/test_tirz_prompt 2026-03-20`
- `/test_training_prompt 2026-03-20`
- `/test_pool_prompt 2026-03-20`

## Как хранится локальное состояние

В репозиторий не попадают:

- `.env`
- `tokens.json`
- `data/`
- `logs/`
- `.venv/`

Это важно, потому что именно там лежат:
- токены
- service account key
- настройки пользователя
- техническое состояние автоматизации

## Известные нюансы

- Если Telegram API работает нестабильно, используй `PROXY_URL` или VPN.
- Если используешь новый Google-компонент `Таблица`, лучше заранее подготовить пустые строки внутри таблицы.
- Клетчатка заполняется только если FatSecret отдаёт это поле в API. Иначе бот пишет `0`.

## Запуск

```powershell
.\.venv\Scripts\python.exe bot.py
```

## Лицензия

Личная утилита под собственный workflow. Если хочешь, можешь потом добавить сюда свою лицензию отдельно.
