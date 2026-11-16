from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import current_user, digest, passwords
from app.models.entities import Session, User
from app.repositories.common import public_record, user_record
from app.schemas.inputs import ChangePassword, EmailInput, Login, Register, ResetPassword, TokenInput
from app.services import auth

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=201)
async def register(data: Register, db: AsyncSession = Depends(get_db)):
    user = await auth.register(db, data)
    return {
        "user": user_record(user),
        "message": "Account created. Check the development mail sink for your verification link.",
    }


@router.post("/login")
async def login(data: Login, response: Response, db: AsyncSession = Depends(get_db)):
    user, token = await auth.login(db, data)
    response.set_cookie(
        "hl_session",
        token,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        max_age=get_settings().session_hours * 3600,
        path="/",
    )
    return user_record(user)


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("hl_session")
    if token:
        await db.execute(delete(Session).where(Session.token_hash == digest(token)))
    response.delete_cookie("hl_session", path="/")
    return {"message": "Signed out"}


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return user_record(user)


@router.post("/forgot-password")
async def forgot(data: EmailInput, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(
        select(User).where(User.email == str(data.email).lower(), User.suspended.is_(False))
    )
    if user:
        await auth.issue_token(db, user, "reset")
    return {
        "message": "If this account exists, a recovery message has been queued to the configured mail sink."
    }


@router.post("/request-verification")
async def request_verification(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if not user.email_verified:
        await auth.issue_token(db, user, "verify")
    return {"message": "Verification message queued to the configured mail sink"}


@router.post("/verify-email")
async def verify(data: TokenInput, db: AsyncSession = Depends(get_db)):
    user = await auth.consume_token(db, data.token, "verify")
    user.email_verified = True
    return {"message": "Email verified"}


@router.post("/reset-password")
async def reset(data: ResetPassword, db: AsyncSession = Depends(get_db)):
    user = await auth.consume_token(db, data.token, "reset")
    user.password_hash = passwords.hash(data.password)
    await auth.revoke_sessions(db, user.id)
    return {"message": "Password reset. Sign in again."}


@router.post("/change-password")
async def change(
    data: ChangePassword, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    if not passwords.verify(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = passwords.hash(data.password)
    await auth.revoke_sessions(db, user.id)
    return {"message": "Password updated; all sessions revoked"}


@router.get("/sessions")
async def sessions(request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Session).where(Session.user_id == user.id))).all()
    return [
        {**public_record(row, ("token_hash",)), "current": row.id == request.state.session_id} for row in rows
    ]


@router.delete("/sessions/{session_id}")
async def revoke(session_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Session).where(Session.id == session_id, Session.user_id == user.id))
    return {"message": "Session revoked"}


@router.post("/roles/{role}")
async def role(role: str, user: User = Depends(current_user)):
    if role not in ("worker", "client"):
        raise HTTPException(422, "Unsupported role")
    user.roles = sorted(set(user.roles + [role]))
    return user_record(user)


@router.delete("/account")
async def deactivate(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    user.suspended = True
    await auth.revoke_sessions(db, user.id)
    return {"message": "Account deactivated. Contact the operator for data deletion requests."}
