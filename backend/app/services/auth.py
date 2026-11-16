from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import DUMMY_HASH, digest, passwords, secret, utc
from app.integrations.mail import send_account_mail
from app.models.entities import AccountToken, AuditLog, Session, User


async def issue_token(db, user, purpose):
    await db.execute(
        delete(AccountToken).where(AccountToken.user_id == user.id, AccountToken.purpose == purpose)
    )
    token = secret()
    db.add(
        AccountToken(
            user_id=user.id,
            token_hash=digest(token),
            purpose=purpose,
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
    )
    await send_account_mail(user.email, purpose, token)


async def register(db, data):
    email = str(data.email).lower()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Unable to register this email")
    user = User(
        email=email,
        password_hash=passwords.hash(data.password),
        display_name=data.display_name,
        roles=[data.role],
        adult_confirmed=True,
    )
    db.add(user)
    await db.flush()
    await issue_token(db, user, "verify")
    db.add(AuditLog(actor_id=user.id, action="account.register", resource_id=user.id))
    return user


async def login(db, data):
    user = await db.scalar(select(User).where(User.email == str(data.email).lower()))
    valid = passwords.verify(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or user.suspended:
        raise HTTPException(401, "Invalid email or password")
    token = secret()
    session = Session(
        user_id=user.id,
        token_hash=digest(token),
        expires_at=datetime.now(UTC) + timedelta(hours=get_settings().session_hours),
    )
    db.add(session)
    return user, token


async def consume_token(db, token, purpose):
    record = await db.scalar(
        select(AccountToken)
        .where(AccountToken.token_hash == digest(token), AccountToken.purpose == purpose)
        .with_for_update()
    )
    if not record or utc(record.expires_at) < datetime.now(UTC):
        raise HTTPException(400, "Invalid or expired link")
    user = await db.get(User, record.user_id)
    if not user or user.suspended:
        raise HTTPException(400, "Invalid or expired link")
    await db.delete(record)
    return user


async def revoke_sessions(db, user_id):
    await db.execute(delete(Session).where(Session.user_id == user_id))
