import hashlib
import secrets
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entities import APIKey, Session, User


class PasswordService:
    def __init__(self):
        self.hasher = PasswordHasher()

    def hash(self, password):
        return self.hasher.hash(password)

    def verify(self, password, encoded):
        try:
            return self.hasher.verify(encoded, password)
        except (VerificationError, InvalidHashError):
            return False


passwords = PasswordService()
DUMMY_HASH = passwords.hash("not-a-real-account-password")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def secret() -> str:
    return secrets.token_urlsafe(32)


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get("hl_session")
    if not token:
        raise HTTPException(401, "Sign in to continue")
    session = await db.scalar(select(Session).where(Session.token_hash == digest(token)))
    if not session or utc(session.expires_at) <= datetime.now(UTC):
        raise HTTPException(401, "Session expired")
    user = await db.get(User, session.user_id)
    if not user or user.suspended:
        raise HTTPException(403, "Account unavailable")
    request.state.user_id = user.id
    request.state.session_id = session.id
    return user


async def verified_user(user: User = Depends(current_user)) -> User:
    if not user.email_verified or not user.adult_confirmed:
        raise HTTPException(403, "Verify your email and confirm adult eligibility first")
    return user


async def admin_user(user: User = Depends(verified_user)) -> User:
    if "admin" not in user.roles:
        raise HTTPException(403, "Administrator access required")
    return user


def agent_scope(scope: str):
    async def dependency(request: Request, db: AsyncSession = Depends(get_db)):
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer hl_"):
            raise HTTPException(401, "Scoped API key required")
        key = await db.scalar(
            select(APIKey).where(APIKey.key_hash == digest(header[7:]), APIKey.revoked.is_(False))
        )
        if not key or scope not in key.scopes:
            raise HTTPException(403, "Key missing required scope")
        owner = await db.get(User, key.owner_id)
        if not owner or owner.suspended or not owner.email_verified or not owner.adult_confirmed:
            raise HTTPException(403, "Key owner unavailable")
        request.state.key_id = key.id
        request.state.user_id = owner.id
        return owner

    return dependency
