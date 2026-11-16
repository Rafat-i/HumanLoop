from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import admin_user
from app.models.entities import (
    AuditLog,
    Dispute,
    FeatureFlag,
    Payment,
    Report,
    Review,
    Task,
    TaskSubmission,
    User,
    WorkerProfile,
)
from app.repositories.common import public_record, require
from app.services.auth import revoke_sessions
from app.services.tasks import audit, change_state, notify

router = APIRouter(prefix="/admin", tags=["Administration"])


class Moderation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "reject", "suspend", "restore", "resolve", "hide", "hold", "cancel"]


@router.get("/overview")
async def overview(user: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    values = {}
    for name, model in (
        ("users", User),
        ("workers", WorkerProfile),
        ("tasks", Task),
        ("reports", Report),
        ("disputes", Dispute),
    ):
        query = select(func.count()).select_from(model)
        if model is Task:
            query = query.where(Task.status != "DELETED")
        values[name] = await db.scalar(query)
    values["payments"] = [
        {"currency": currency, "amount": amount}
        for currency, amount in (
            await db.execute(
                select(Payment.currency, func.sum(Payment.amount))
                .where(Payment.status == "SUCCEEDED")
                .group_by(Payment.currency)
            )
        ).all()
    ]
    return values


MODELS = {
    "users": User,
    "workers": WorkerProfile,
    "tasks": Task,
    "reports": Report,
    "disputes": Dispute,
    "payments": Payment,
    "audit-logs": AuditLog,
    "reviews": Review,
    "settings": FeatureFlag,
}


@router.get("/{section}")
async def records(
    section: str,
    page: int = Query(1, ge=1),
    user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db),
):
    model = MODELS.get(section)
    if not model:
        raise HTTPException(404, "Unknown admin section")
    query = select(model)
    if model is Task:
        query = query.where(Task.status != "DELETED")
    rows = (await db.scalars(query.order_by(model.created_at.desc()).offset((page - 1) * 30).limit(30))).all()
    return [public_record(row, ("password_hash",)) for row in rows]


@router.post("/{section}/{identifier}")
async def moderate(
    section: str,
    identifier: str,
    data: Moderation,
    user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db),
):
    model = MODELS.get(section)
    if model not in (User, WorkerProfile, Task, Report, Dispute, Review):
        raise HTTPException(422, "Unsupported moderation target")
    row = await require(db, model, identifier, lock=True)
    if model is User and data.action in ("suspend", "restore"):
        if row.id == user.id or "admin" in row.roles:
            raise HTTPException(409, "Administrator accounts cannot be changed here")
        row.suspended = data.action == "suspend"
        if row.suspended:
            await revoke_sessions(db, row.id)
    elif model is WorkerProfile and data.action in ("approve", "reject"):
        row.review_status = "APPROVED" if data.action == "approve" else "REJECTED"
        # Review approval never marks identity as verified.
        notify(db, row.user_id, "Administrative review", None)
    elif model is Task and data.action in ("hold", "cancel"):
        change_state(db, row, user, "IN_REVIEW" if data.action == "hold" else "CANCELLED")
    elif model is Report and data.action == "resolve":
        row.status = "RESOLVED"
    elif model is Dispute and data.action in ("approve", "cancel"):
        task = await require(db, Task, row.task_id, lock=True)
        if data.action == "approve" and not await db.scalar(
            select(TaskSubmission).where(TaskSubmission.task_id == task.id)
        ):
            raise HTTPException(409, "Cannot complete a dispute without submitted results")
        change_state(db, task, user, "COMPLETED" if data.action == "approve" else "CANCELLED")
        row.status = "RESOLVED"
    elif model is Review and data.action == "hide":
        row.hidden = True
    else:
        raise HTTPException(422, "Unsupported moderation action")
    audit(db, user, f"admin.{section}.{data.action}", row.id)
    return public_record(row, ("password_hash",))
