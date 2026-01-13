from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


STATUS_EMOJI = {
    "new": "🆕",
    "booked": "✅",
    "call_back": "⏰",
    "rejected": "❌",
}

STATUS_LABEL = {
    "new": "Новая",
    "booked": "Записан(а)",
    "call_back": "Перезвонить",
    "rejected": "Отказ",
}


def _safe(v: Optional[str]) -> str:
    return (v or "—").strip() or "—"


def format_lead_text(lead: Dict[str, Any]) -> str:
    status = lead.get("status", "new")
    emoji = STATUS_EMOJI.get(status, "📝")

    created_at = lead.get("created_at")
    created_human = ""
    try:
        if created_at:
            created_human = datetime.fromisoformat(created_at.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        created_human = str(created_at or "")

    lines = [
        f"{emoji} Заявка #{lead.get('id')} — {STATUS_LABEL.get(status, status)}",
    ]
    if created_human:
        lines.append(f"🕒 {created_human} (UTC)")

    lines.extend(
        [
            f"👤 {_safe(lead.get('name'))}",
            f"📞 {_safe(lead.get('phone'))}",
            f"📩 {_safe(lead.get('source'))}",
            "",
            f"💬 {(_safe(lead.get('text')))}",
        ]
    )

    return "\n".join(lines)


def lead_keyboard(lead_id: int) -> Dict[str, Any]:
    # callback_data must be short
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Записан", "callback_data": f"lead:{lead_id}:booked"},
                {"text": "⏰ Перезвонить", "callback_data": f"lead:{lead_id}:call_back"},
            ],
            [
                {"text": "❌ Отказ", "callback_data": f"lead:{lead_id}:rejected"},
            ],
        ]
    }
