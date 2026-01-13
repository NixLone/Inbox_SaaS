import json
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


class TelegramApiError(RuntimeError):
    pass


def _post(base_url: str, method: str, payload: Dict[str, Any], timeout: float = 20.0) -> Dict[str, Any]:
    url = f"{base_url}/{method}"
    r = requests.post(url, json=payload, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        raise TelegramApiError(f"Non-JSON response from Telegram: status={r.status_code} body={r.text[:200]}")
    if not data.get("ok"):
        raise TelegramApiError(f"Telegram error: {data}")
    return data


def _get(base_url: str, method: str, params: Dict[str, Any], timeout: float = 20.0) -> Dict[str, Any]:
    url = f"{base_url}/{method}"
    r = requests.get(url, params=params, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        raise TelegramApiError(f"Non-JSON response from Telegram: status={r.status_code} body={r.text[:200]}")
    if not data.get("ok"):
        raise TelegramApiError(f"Telegram error: {data}")
    return data


class TelegramClient:
    def __init__(self, bot_token: str, dry_run: bool = False):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.dry_run = dry_run

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        disable_web_page_preview: bool = True,
    ) -> int:
        if self.dry_run:
            # deterministic-ish fake message id
            return int(time.time())
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        data = _post(self.base_url, "sendMessage", payload)
        return int(data["result"]["message_id"])

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        disable_web_page_preview: bool = True,
    ) -> None:
        if self.dry_run:
            return
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        _post(self.base_url, "editMessageText", payload)

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> None:
        if self.dry_run:
            return
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        _post(self.base_url, "answerCallbackQuery", payload)

    def get_updates(self, offset: Optional[int] = None, timeout_sec: int = 30) -> List[Dict[str, Any]]:
        if self.dry_run:
            return []
        params: Dict[str, Any] = {"timeout": timeout_sec}
        if offset is not None:
            params["offset"] = offset
        data = _get(self.base_url, "getUpdates", params=params, timeout=float(timeout_sec) + 10.0)
        return data.get("result", [])


def inline_keyboard(rows: List[List[Tuple[str, str]]]) -> Dict[str, Any]:
    """rows: [[(button_text, callback_data), ...], ...]"""
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": cb} for (text, cb) in row] for row in rows
        ]
    }
