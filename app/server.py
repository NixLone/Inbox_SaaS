from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import get_settings
from . import db
from .telegram_api import TelegramClient
from .formatting import format_lead_text, lead_keyboard


class WebhookPayload(BaseModel):
    source: str = Field(..., description="From where the lead came (instagram/whatsapp/etc)")
    text: str = Field(..., description="User message text")
    name: Optional[str] = Field(None, description="Client name")
    phone: Optional[str] = Field(None, description="Client phone")


def create_app() -> FastAPI:
    settings = get_settings()
    db.init_schema(settings.db_path)

    app = FastAPI(title="Micro-SaaS Inbox", version="0.1.0")

    def _tg() -> TelegramClient:
        if not settings.bot_token:
            # backend still works without Telegram; it will store leads only
            return TelegramClient("", dry_run=True)
        return TelegramClient(settings.bot_token, dry_run=settings.telegram_dry_run)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/webhook/{token}")
    def webhook(token: str, payload: WebhookPayload):
        user = db.get_user_by_token(settings.db_path, token)
        if not user:
            raise HTTPException(status_code=404, detail="Unknown token")

        client_id = db.upsert_client(settings.db_path, user_id=int(user["id"]), name=payload.name, phone=payload.phone)

        lead_id = db.create_lead(
            settings.db_path,
            user_id=int(user["id"]),
            source=payload.source,
            text=payload.text,
            name=payload.name,
            phone=payload.phone,
            client_id=client_id,
            status="new",
            tg_chat_id=user.get("tg_chat_id"),
        )

        # Push to Telegram (if user already started the bot)
        chat_id = user.get("tg_chat_id")
        if chat_id:
            lead = db.get_lead_by_id(settings.db_path, lead_id)
            if lead:
                msg_id = _tg().send_message(int(chat_id), format_lead_text(lead), reply_markup=lead_keyboard(lead_id))
                db.set_lead_telegram_message(settings.db_path, lead_id, msg_id, int(chat_id))

        return {"ok": True, "lead_id": lead_id}

    @app.get("/debug/leads/{token}")
    def debug_list_leads(token: str, limit: int = 20):
        user = db.get_user_by_token(settings.db_path, token)
        if not user:
            raise HTTPException(status_code=404, detail="Unknown token")
        leads = db.list_recent_leads(settings.db_path, int(user["id"]), limit=limit)
        return {"ok": True, "leads": leads}

    return app


# For uvicorn: `uvicorn app.server:app`
app = create_app()
