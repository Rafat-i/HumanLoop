from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import current_user
from app.models.entities import AgentToolCall, Message, Notification, Payment, Task, TaskApplication, User
from app.repositories.common import public_record, require

router = APIRouter(tags=["Dashboard"])


@router.get("/notifications")
async def notifications(
    page: int = Query(1, ge=1), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * 30)
            .limit(30)
        )
    ).all()
    unread = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read.is_(False))
    )
    return {"items": [public_record(row) for row in rows], "unread": unread}


@router.post("/notifications/{notification_id}/read")
async def read_notification(
    notification_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    row = await require(db, Notification, notification_id)
    if row.user_id != user.id:
        raise HTTPException(403, "Notification owner required")
    row.read = True
    return public_record(row)


@router.get("/analytics")
async def analytics(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    own = (Task.owner_id == user.id) & (Task.status != "DELETED")
    worker = Task.assigned_worker_id == user.id
    statuses = (
        await db.execute(select(Task.status, func.count()).where(or_(own, worker)).group_by(Task.status))
    ).all()
    created = await db.scalar(select(func.count()).select_from(Task).where(own)) or 0
    completed = (
        await db.scalar(select(func.count()).select_from(Task).where(worker, Task.status == "COMPLETED")) or 0
    )
    client_completed = (
        await db.scalar(select(func.count()).select_from(Task).where(own, Task.status == "COMPLETED")) or 0
    )
    applications = (
        await db.scalar(
            select(func.count())
            .select_from(TaskApplication)
            .where(TaskApplication.worker_id == user.id, TaskApplication.status == "PENDING")
        )
        or 0
    )
    payments = (
        await db.execute(
            select(Payment.currency, func.sum(Payment.amount))
            .join(Task, Task.id == Payment.task_id)
            .where(worker, Payment.status == "SUCCEEDED")
            .group_by(Payment.currency)
        )
    ).all()
    tool_counts = (
        await db.execute(
            select(AgentToolCall.status, func.count())
            .where(AgentToolCall.owner_id == user.id)
            .group_by(AgentToolCall.status)
        )
    ).all()
    unread = (
        await db.scalar(
            select(func.count())
            .select_from(Message)
            .join(Task, Message.task_id == Task.id)
            .where(or_(own, worker), Message.sender_id != user.id, Message.read_at.is_(None))
        )
        or 0
    )
    return {
        "tasks_created": created,
        "tasks_completed": completed,
        "client_tasks_completed": client_completed,
        "client_completion_rate": round(client_completed / created * 100, 1) if created else 0,
        "active_applications": applications,
        "test_earnings": [{"currency": c, "amount": amount} for c, amount in payments],
        "statuses": [{"name": name, "count": count} for name, count in statuses],
        "tool_calls": [{"name": name, "count": count} for name, count in tool_counts],
        "unread_messages": unread,
    }
