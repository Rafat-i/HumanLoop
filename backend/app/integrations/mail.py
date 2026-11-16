"""Development-only mail sink. Never represents a message as delivered."""

import json
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings


async def send_account_mail(email: str, purpose: str, token: str):
    settings = get_settings()
    if settings.environment == "production":
        raise RuntimeError("Configure a reviewed production email adapter before enabling accounts")
    folder = Path(settings.mail_dir)
    folder.mkdir(parents=True, exist_ok=True)
    route = "verify-email" if purpose == "verify" else "reset-password"
    payload = {
        "to": email,
        "purpose": purpose,
        "url": f"{settings.frontend_url}/{route}?token={token}",
        "delivery": "local_sink_only",
    }
    (folder / f"{uuid4()}.json").write_text(json.dumps(payload), encoding="utf-8")
