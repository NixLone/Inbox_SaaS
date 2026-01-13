# Micro-SaaS Inbox (MVP)

Идея: заявки из любых источников (Instagram/WhatsApp/и т.д.) прилетают в **один Telegram**.

## Что уже умеет (MVP)
- Telegram-бот `/start` генерирует **персональный токен**.
- Backend принимает `POST /webhook/<TOKEN>` с JSON и:
  - сохраняет заявку в SQLite
  - отправляет её в Telegram с кнопками статуса (✅/⏰/❌)
- В боте:
  - /today, /day, /last, /find
  - кнопки меняют статус и обновляют сообщение

## Быстрый старт (локально)
1) Создай бота у @BotFather и получи токен.
2) В терминале:

```bash
cd micro_saas_inbox
export TELEGRAM_BOT_TOKEN="<TOKEN_FROM_BOTFATHER>"
export DB_PATH="$(pwd)/data/app.db"

# 1) backend
uvicorn app.server:app --host 0.0.0.0 --port 8000

# 2) в другом терминале: bot
python -m app.bot
```

3) Открой чат с ботом и введи `/start` — он покажет TOKEN.

## Тест webhook (без интегратора)
```bash
curl -X POST "http://127.0.0.1:8000/webhook/<TOKEN>" \
  -H 'Content-Type: application/json' \
  -d '{"source":"instagram","name":"Анна","phone":"+371000000","text":"Хочу записаться"}'
```

## Подключение Make/Albato
- Триггер: "New message" (Instagram/WhatsApp/...")
- Action: HTTP request → POST
- URL: `https://<твой-домен>/webhook/<TOKEN>`
- Body: JSON как выше.

## Публикация (самый простой вариант)
- подними backend на VPS (например, 5-10$)
- открой порт 8000 через nginx или Caddy
- на время разработки можно использовать Cloudflare Tunnel / ngrok.

## Переменные окружения
- `TELEGRAM_BOT_TOKEN` — токен бота
- `DB_PATH` — путь к SQLite файлу
- `TELEGRAM_DRY_RUN=1` — отключает реальные запросы в Telegram (для тестов)
- `POLL_INTERVAL_SEC=1.0`
- `LOG_LEVEL=INFO`

