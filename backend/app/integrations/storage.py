"""Private local evidence store; no public static mount or user-controlled paths."""

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.core.config import get_settings

MAX_BYTES = 5 * 1024 * 1024


def validate_content(content: bytes, content_type: str):
    if not content or len(content) > MAX_BYTES:
        raise HTTPException(413, "Evidence must be between 1 byte and 5 MB")
    if content_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
        return
    if content_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff"):
        return
    if content_type == "text/plain":
        try:
            content.decode("utf-8")
            if b"\x00" not in content:
                return
        except UnicodeDecodeError:
            pass
    raise HTTPException(422, "Only UTF-8 text, PNG and JPEG evidence are accepted")


class LocalPrivateStorage:
    def __init__(self):
        self.root = Path(get_settings().upload_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key):
        if len(key) != 32 or any(c not in "0123456789abcdef" for c in key):
            raise HTTPException(400, "Invalid storage key")
        return self.root / key

    async def save(self, content):
        key = uuid4().hex
        self.path(key).write_bytes(content)
        return key
