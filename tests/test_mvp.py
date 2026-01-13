import importlib
import os
from datetime import datetime, timezone

from fastapi.testclient import TestClient


def test_webhook_creates_lead_and_sets_tg_message(tmp_path, monkeypatch):
    db_path = str(tmp_path / "app.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("TELEGRAM_DRY_RUN", "1")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    # Import after env vars are set
    from app import db
    import app.server as server

    importlib.reload(server)  # ensure app is created with our env

    # Create user (as if they started the bot)
    user = db.get_or_create_user_by_chat_id(db_path, 12345)
    token = user["token"]

    client = TestClient(server.app)

    r = client.post(
        f"/webhook/{token}",
        json={"source": "instagram", "name": "Анна", "phone": "+371000000", "text": "Хочу записаться"},
    )
    assert r.status_code == 200, r.text
    lead_id = r.json()["lead_id"]

    lead = db.get_lead_by_id(db_path, lead_id)
    assert lead is not None
    assert lead["status"] == "new"
    # In dry_run, we still generate a fake message id and store it
    assert lead["tg_message_id"] is not None
    assert lead["tg_chat_id"] == 12345


def test_callback_updates_status(tmp_path, monkeypatch):
    db_path = str(tmp_path / "app.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("TELEGRAM_DRY_RUN", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy")

    from app import db
    from app.telegram_api import TelegramClient
    from app.bot import handle_callback_query

    db.init_schema(db_path)

    user = db.get_or_create_user_by_chat_id(db_path, 777)
    lead_id = db.create_lead(db_path, user_id=int(user["id"]), source="whatsapp", text="test", tg_chat_id=777)
    db.set_lead_telegram_message(db_path, lead_id, 111, 777)

    client = TelegramClient("dummy", dry_run=True)

    cq = {
        "id": "cq1",
        "data": f"lead:{lead_id}:booked",
        "message": {"message_id": 111, "chat": {"id": 777}},
    }

    handle_callback_query(client, db_path, cq)

    lead = db.get_lead_by_id(db_path, lead_id)
    assert lead["status"] == "booked"
