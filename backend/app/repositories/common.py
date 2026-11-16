from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.entities import Task


async def require(db, model, identifier, lock=False):
    try:
        UUID(str(identifier))
    except ValueError as exc:
        raise HTTPException(422, "Invalid resource identifier") from exc
    query = select(model).where(model.id == identifier)
    if lock:
        query = query.with_for_update()
    record = await db.scalar(query)
    if record is None or (isinstance(record, Task) and record.status == "DELETED"):
        raise HTTPException(404, "Resource not found")
    return record


def public_record(record, exclude=()):
    return {
        column.name: getattr(record, column.name)
        for column in record.__table__.columns
        if column.name not in exclude
    }


def user_record(user):
    return public_record(user, ("password_hash",))
