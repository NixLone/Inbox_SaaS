from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, date
from typing import Any, Dict, Optional

from .config import get_settings
from . import db
from .telegram_api import TelegramClient
from .formatting import format_lead_text, lead_keyboard


def _parse_command(text: str) -> tuple[str, str]:
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].split("@", 1)[0]
    arg = parts[1] if len(parts) > 1 else ""
    return cmd, arg


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _render_lead_list(leads: list[dict[str, Any]]) -> str:
    if not leads:
        return "Ничего не найдено."
    lines: list[str] = []
    for l in leads:
        created = l.get("created_at", "")
        created_short = created[11:16] if len(created) >= 16 else created
        lines.append(
            f"#{l.get('id')} [{l.get('status')}] {created_short} — { (l.get('name') or '—') } — { (l.get('source') or '—') }"
        )
    return "\n".join(lines)


def handle_message(client: TelegramClient, db_path: str, message: Dict[str, Any]) -> None:
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id is None:
        return

    text = (message.get("text") or "").strip()
    if not text:
        client.send_message(int(chat_id), "Понимаю только текстовые сообщения. Команды: /help")
        return

    if not text.startswith("/"):
        client.send_message(int(chat_id), "Напиши /help, чтобы увидеть команды.")
        return

    cmd, arg = _parse_command(text)

    if cmd == "/start":
        user = db.get_or_create_user_by_chat_id(db_path, int(chat_id))
        token = user["token"]
        msg = (
            "Привет! Я соберу все заявки в один Telegram.\n\n"
            "Твой токен (секретный):\n"
            f"`{token}`\n\n"
            "Webhook для интегратора (Make/Albato/свой скрипт):\n"
            f"POST /webhook/{token}\n"
            "JSON пример:\n"
            '{"source":"instagram","name":"Анна","phone":"+371...","text":"Хочу записаться"}'
            "\n\nКоманды: /help"
        )
        # Telegram supports MarkdownV2, but to keep MVP simple we won't set parse_mode.
        client.send_message(int(chat_id), msg)
        return

    if cmd == "/help":
        msg = (
            "Команды:\n"
            "/token — показать токен\n"
            "/today — заявки за сегодня (UTC)\n"
            "/day YYYY-MM-DD — заявки за дату (UTC)\n"
            "/last N — последние N заявок\n"
            "/find ТЕКСТ — поиск по имени/телефону/тексту\n"
        )
        client.send_message(int(chat_id), msg)
        return

    if cmd == "/token":
        user = db.get_or_create_user_by_chat_id(db_path, int(chat_id))
        client.send_message(int(chat_id), f"Токен: {user['token']}")
        return

    # All commands below require user row
    user = db.get_or_create_user_by_chat_id(db_path, int(chat_id))
    user_id = int(user["id"])

    if cmd == "/today":
        leads = db.list_leads_for_day(db_path, user_id, _utc_today())
        client.send_message(int(chat_id), _render_lead_list(leads))
        return

    if cmd == "/day":
        try:
            d = date.fromisoformat(arg.strip())
        except Exception:
            client.send_message(int(chat_id), "Формат: /day 2026-01-13")
            return
        leads = db.list_leads_for_day(db_path, user_id, d)
        client.send_message(int(chat_id), _render_lead_list(leads))
        return

    if cmd == "/last":
        try:
            n = int(arg.strip() or "20")
            n = max(1, min(n, 100))
        except Exception:
            client.send_message(int(chat_id), "Формат: /last 20")
            return
        leads = db.list_recent_leads(db_path, user_id, limit=n)
        client.send_message(int(chat_id), _render_lead_list(leads))
        return

    if cmd == "/find":
        q = arg.strip()
        if not q:
            client.send_message(int(chat_id), "Формат: /find Анна")
            return
        leads = db.find_leads_by_client(db_path, user_id, q, limit=50)
        client.send_message(int(chat_id), _render_lead_list(leads))
        return

    client.send_message(int(chat_id), "Неизвестная команда. /help")


def handle_callback_query(client: TelegramClient, db_path: str, cq: Dict[str, Any]) -> None:
    cq_id = cq.get("id")
    data = (cq.get("data") or "").strip()
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")

    if cq_id:
        client.answer_callback_query(cq_id)

    if not (data.startswith("lead:") and chat_id and message_id):
        return

    # lead:<id>:<status>
    parts = data.split(":")
    if len(parts) != 3:
        return

    try:
        lead_id = int(parts[1])
    except Exception:
        return

    status = parts[2]
    if status not in {"booked", "call_back", "rejected", "new"}:
        return

    db.set_lead_status(db_path, lead_id, status)
    lead = db.get_lead_by_id(db_path, lead_id)
    if not lead:
        return

    # Update original message
    client.edit_message_text(int(chat_id), int(message_id), format_lead_text(lead), reply_markup=lead_keyboard(lead_id))


def run() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO), format="%(asctime)s %(levelname)s %(message)s")

    if not settings.bot_token and not settings.telegram_dry_run:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required (or set TELEGRAM_DRY_RUN=1 for tests)")

    db.init_schema(settings.db_path)
    client = TelegramClient(settings.bot_token, dry_run=settings.telegram_dry_run)

    logging.info("Bot started. dry_run=%s", settings.telegram_dry_run)

    offset: Optional[int] = None
    while True:
        try:
            updates = client.get_updates(offset=offset, timeout_sec=30)
            for u in updates:
                offset = int(u.get("update_id", 0)) + 1
                if "message" in u:
                    handle_message(client, settings.db_path, u["message"])
                elif "callback_query" in u:
                    handle_callback_query(client, settings.db_path, u["callback_query"])
        except Exception as e:
            logging.exception("Bot loop error: %s", e)
            time.sleep(2.0)

        time.sleep(settings.poll_interval_sec)


if __name__ == "__main__":
    run()
