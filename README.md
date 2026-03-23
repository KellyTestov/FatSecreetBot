# FatSecreetBot

Telegram-бот для личного контроля питания, веса, активности и еженедельных рутин на базе FatSecret и Google Sheets.

## Бизнес-логика

Этот бот нужен для одной задачи: не руками вести дневник в Google Sheets, а собирать его автоматически из FatSecret и коротких ответов в Telegram.

В основе есть лист `Status` в Google Sheets со строками по дням и колонками:

```text
Дата | Вес (кг) | Калории | Белок (г) | Углеводы (г) | Клетчатка (г) | Жиры (г) | Аппетит / ощущения | Тирзетта | Зал | Бассейн | Кардио
```

Бот каждый день или по расписанию дополняет эту таблицу.

### Что бот делает автоматически

#### 1. Питание

Бот берёт данные из FatSecret и записывает в `Status`:
- дату
- калории
- белок
- углеводы
- клетчатку
- жиры

Запись питания идёт **за предыдущий день**.

Сейчас это происходит в:
- `05:00` по таймзоне `Europe/Moscow`

Это сделано специально не в полночь, чтобы поздние записи в FatSecret успели сохраниться.

#### 2. Аппетит / ощущения

Каждый день бот пишет в Telegram вопрос про аппетит.

Время:
- `00:00`

Бот ждёт обычный текстовый ответ и сохраняет его в колонку:
- `Аппетит / ощущения`

#### 3. Тренировки

После того как ты ответил на вопрос про аппетит, бот может задать дополнительные вопросы по активности:

- во `вторник`, `четверг`, `субботу`
  - спрашивает про `Зал`
  - потом спрашивает про `Кардио`

- в `воскресенье`
  - спрашивает про `Бассейн`

Это сделано именно **после ответа про аппетит**, чтобы бот не спамил несколькими сообщениями одновременно в `00:00`.

#### 4. Вес

Бот спрашивает вес не по календарной неделе, а по **неделям похудения**, которые считаются от `start_date`.

Пример:
- если старт похудения `2026-02-26`
- и четвёртая неделя у тебя заканчивается `2026-03-26`
- значит вопрос про вес придёт именно `2026-03-26`

Время вопроса:
- `09:30`

Ответ сохраняется в колонку:
- `Вес (кг)`

#### 5. Тирзетта

Бот отдельно напоминает про укол Тирзетты.

Время:
- `19:00`

У сообщения две кнопки:
- `Поставил`
- `Отложить на день`

Логика такая:
- если нажал `Поставил`, бот пишет статус в таблицу и переносит следующий вопрос на `+7 дней`
- если нажал `Отложить на день`, бот ничего не отмечает как выполненное и переносит вопрос на следующий день

#### 6. Google Sheets как главный журнал

Итоговая точка правды для дневника — это таблица Google Sheets.

FatSecret даёт данные по еде.
Telegram даёт ручные ответы:
- аппетит
- вес
- статус Тирзетты
- зал
- бассейн
- кардио

Всё это собирается в одном листе `Status`.

## Как это выглядит в реальной жизни

Обычный день выглядит так:

1. В `00:00` бот спрашивает про аппетит.
2. Ты отвечаешь одним сообщением.
3. Если это тренировочный день, бот после этого задаёт ещё вопрос(ы) про активность.
4. В `05:00` бот сам подтягивает питание за вчера из FatSecret.

Дополнительно:
- в нужный день в `09:30` он спросит вес
- в нужный день в `19:00` спросит про Тирзетту

То есть бот не должен долбить тебя хаотично в течение дня. Основная идея — короткие понятные касания по расписанию, а остальное он делает сам.

## Что умеет бот

### Отчёты и аналитика

- `/auth`
- `/today`
- `/yesterday`
- `/day`
- `/period`
- `/last7`
- `/last14`
- `/last30`
- `/week`
- `/current_week`
- `/compare`
- `/top_products`

### Экспорт

- `/export_excel`
- `/export_pdf`

### Работа с Google Sheets

- `/sheets_test`

### Тестирование автоматизации

- `/test_status_sync 2026-03-20`
- `/test_appetite_prompt 2026-03-20`
- `/test_weight_prompt 2026-03-20`
- `/test_tirz_prompt 2026-03-20`
- `/test_training_prompt 2026-03-20`
- `/test_pool_prompt 2026-03-20`

---

## Техническая часть

## Стек

- Python `3.11+`
- `python-telegram-bot`
- FatSecret API
- Google Sheets API
- `openpyxl`
- `reportlab`

## Структура проекта

- [bot.py](./bot.py) — запуск Telegram-бота
- [handlers.py](./handlers.py) — основные Telegram-команды
- [status_automation.py](./status_automation.py) — расписание и автоматические сценарии
- [fatsecret.py](./fatsecret.py) — авторизация и запросы к FatSecret
- [google_sheets.py](./google_sheets.py) — работа с Google Sheets
- [analytics.py](./analytics.py) — расчёт нутриентов и аналитика
- [exports.py](./exports.py) — экспорт в `Excel` и `PDF`
- [config.py](./config.py) — конфигурация проекта

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

Выдай доступ редактора сервисному аккаунту.

### 4. Укажи ID таблицы

Если ссылка выглядит так:

```text
https://docs.google.com/spreadsheets/d/1rHs0hcDdW5XnWrwIEecxaB4G8e1tqSdx2tLyXGAYaY0/edit
```

то ID будет таким:

```env
GOOGLE_SHEETS_SPREADSHEET_ID=1rHs0hcDdW5XnWrwIEecxaB4G8e1tqSdx2tLyXGAYaY0
```

## Формат листа `Status`

Лист должен содержать колонки:

```text
Дата | Вес (кг) | Калории | Белок (г) | Углеводы (г) | Клетчатка (г) | Жиры (г) | Аппетит / ощущения | Тирзетта | Зал | Бассейн | Кардио
```

Если используется новый Google-компонент `Таблица`, лучше заранее создать внутри таблицы запас пустых строк.

## Первый запуск

### 1. Запуск бота

```powershell
.\.venv\Scripts\python.exe bot.py
```

### 2. Авторизация FatSecret

В Telegram:

```text
/auth
```

### 3. Проверка Google Sheets

В Telegram:

```text
/sheets_test
```

Или локально:

```powershell
.\.venv\Scripts\python.exe check_google_sheets.py
```

## Деплой на Railway

Проект уже подготовлен под Railway:

- есть [railway.json](./railway.json)
- есть [`.env.example`](./.env.example)
- есть `STORAGE_DIR` для постоянного хранилища
- можно передать Google service account через `GOOGLE_SERVICE_ACCOUNT_JSON`

### Что выбрать в Railway

1. Создай новый проект
2. Подключи GitHub-репозиторий
3. Railway сам соберёт проект
4. Start command уже задан: `python bot.py`

### Что обязательно добавить в Variables

- `FATSECRET_CONSUMER_KEY`
- `FATSECRET_CONSUMER_SECRET`
- `FATSECRET_CALLBACK=oob`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_ID`
- `GOOGLE_SHEETS_SPREADSHEET_ID`
- `GOOGLE_SHEETS_WORKSHEET=BotLogs`
- `GOOGLE_STATUS_WORKSHEET=Status`
- `BOT_TIMEZONE=Europe/Moscow`

Также одно из двух:

1. Либо:
   `GOOGLE_SERVICE_ACCOUNT_JSON={...полный json...}`

2. Либо:
   `GOOGLE_SERVICE_ACCOUNT_FILE=/data/storage/data/google_service_account.json`

### Что лучше примонтировать как Volume

Создай Railway Volume и используй:

```env
STORAGE_DIR=/data/storage
```

Тогда там будут жить:
- `tokens.json`
- `settings.json`
- `automation_state.json`
- временные выгрузки

Это важно, чтобы после рестарта Railway бот не терял:
- авторизацию FatSecret
- дату старта и цели
- состояние автоматизации
- дату следующей Тирзетты

### Важное замечание

Если Telegram API у тебя из региона ходит нестабильно, добавь:

```env
PROXY_URL=socks5://host:port
```

## Все основные команды

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

## Хранение локальных данных

В git не попадают:

- `.env`
- `tokens.json`
- `data/`
- `logs/`
- `.venv/`

Там лежат:
- токены
- service account key
- настройки пользователя
- состояние автоматизации

## Известные нюансы

- Если Telegram API работает нестабильно, используй `PROXY_URL` или VPN.
- Если используешь новый Google-компонент `Таблица`, поведение форматирования может отличаться от обычного диапазона.
- Клетчатка заполняется только если FatSecret отдаёт это поле в API.

## Запуск

```powershell
.\.venv\Scripts\python.exe bot.py
```

## Лицензия

Личная утилита под собственный workflow.
