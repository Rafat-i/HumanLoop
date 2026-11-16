import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.matching import score_worker
from app.agents.planner import propose
from app.api.marketplace import enrich, visible_workers
from app.core.database import get_db
from app.core.security import agent_scope, current_user, digest, secret, verified_user
from app.models.entities import (
    AgentToolCall,
    APIKey,
    IdempotencyRecord,
    Message,
    Notification,
    Task,
    TaskSubmission,
    User,
)
from app.repositories.common import public_record, require
from app.schemas.inputs import AgentMessage, KeyInput, PlaygroundInput, TaskInput
from app.services import tasks

router = APIRouter(tags=["Agents"])


@router.get("/keys")
async def keys(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return [
        public_record(key, ("key_hash",))
        for key in (
            await db.scalars(
                select(APIKey).where(APIKey.owner_id == user.id).order_by(APIKey.created_at.desc())
            )
        ).all()
    ]


async def new_key(db, user, data):
    token = "hl_" + secret()
    key = APIKey(
        owner_id=user.id,
        name=data.name,
        prefix=token[:12],
        key_hash=digest(token),
        scopes=sorted(set(data.scopes)),
    )
    db.add(key)
    await db.flush()
    tasks.audit(db, user, "key.create", key.id)
    return {**public_record(key, ("key_hash",)), "key": token}


@router.post("/keys", status_code=201)
async def create_key(data: KeyInput, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    return await new_key(db, user, data)


@router.delete("/keys/{key_id}")
async def revoke_key(key_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    key = await require(db, APIKey, key_id, lock=True)
    if key.owner_id != user.id:
        raise HTTPException(403, "Key owner required")
    key.revoked = True
    tasks.audit(db, user, "key.revoke", key.id)
    return {"message": "Key revoked"}


@router.post("/keys/{key_id}/rotate")
async def rotate(key_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    key = await require(db, APIKey, key_id, lock=True)
    if key.owner_id != user.id:
        raise HTTPException(403, "Key owner required")
    key.revoked = True
    return await new_key(db, user, KeyInput(name=key.name, scopes=key.scopes))


async def recommendations(db, task_data):
    workers = (await db.scalars(visible_workers().limit(200))).all()
    ids = [w.user_id for w in workers]
    assignments = dict(
        (
            await db.execute(
                select(Task.assigned_worker_id, func.count())
                .where(Task.assigned_worker_id.in_(ids))
                .group_by(Task.assigned_worker_id)
            )
        ).all()
    )
    enriched = await enrich(db, workers)
    ranked = [
        {"worker": w, **score_worker(task_data, w, w["completed_tasks"], assignments.get(w["user_id"], 0))}
        for w in enriched
    ]
    return sorted(ranked, key=lambda row: (-row["score"], row["worker"]["id"]))[:10]


@router.get("/tasks/{task_id}/matches")
async def matches(task_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    task = await require(db, Task, task_id)
    tasks.participant(task, user)
    return await recommendations(db, public_record(task))


@router.post("/playground/propose")
async def playground(
    data: PlaygroundInput, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    try:
        draft, source = await propose(data.prompt)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(AgentToolCall(owner_id=user.id, tool="playground.propose", status="SUCCEEDED"))
    return {
        "draft": draft.model_dump(),
        "source": source,
        "matches": await recommendations(db, draft.model_dump()),
        "requires_confirmation": True,
    }


@router.get("/agent/account")
async def account(user: User = Depends(agent_scope("tasks:read"))):
    return {"owner_id": user.id, "roles": user.roles}


@router.get("/agent/tasks")
async def agent_tasks(
    page: int = Query(1, ge=1),
    user: User = Depends(agent_scope("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    return [
        public_record(row)
        for row in (
            await db.scalars(
                select(Task)
                .where(Task.owner_id == user.id)
                .where(Task.status != "DELETED")
                .order_by(Task.created_at.desc())
                .offset((page - 1) * 20)
                .limit(20)
            )
        ).all()
    ]


@router.get("/agent/tasks/{task_id}")
async def agent_task(
    task_id: str, user: User = Depends(agent_scope("tasks:read")), db: AsyncSession = Depends(get_db)
):
    task = await require(db, Task, task_id)
    tasks.owner(task, user)
    return public_record(task)


async def idempotency(db, user, key, operation, payload):
    if not key or len(key) > 128:
        raise HTTPException(422, "Provide an Idempotency-Key of 1 to 128 characters")
    await require(db, User, user.id, lock=True)
    fingerprint = digest(json.dumps(payload, sort_keys=True, default=str))
    record = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.owner_id == user.id,
            IdempotencyRecord.key == key,
            IdempotencyRecord.operation == operation,
        )
    )
    if record and record.request_hash != fingerprint:
        raise HTTPException(409, "Idempotency key was already used with different input")
    return record, fingerprint


@router.post("/agent/tasks/drafts", status_code=201)
async def agent_draft(
    data: TaskInput,
    request: Request,
    idempotency_key: str | None = Header(None),
    user: User = Depends(agent_scope("tasks:write")),
    db: AsyncSession = Depends(get_db),
):
    previous, fingerprint = await idempotency(db, user, idempotency_key, "draft", data.model_dump())
    if previous:
        return public_record(await require(db, Task, previous.resource_id))
    task = await tasks.create_task(db, user, data, agent=True)
    db.add(
        IdempotencyRecord(
            owner_id=user.id,
            key=idempotency_key,
            operation="draft",
            request_hash=fingerprint,
            resource_id=task.id,
        )
    )
    db.add(
        AgentToolCall(
            owner_id=user.id, key_id=request.state.key_id, tool="create_task_draft", status="SUCCEEDED"
        )
    )
    return public_record(task)


@router.post("/agent/tasks/{task_id}/submit")
async def agent_submit(
    task_id: str,
    request: Request,
    idempotency_key: str | None = Header(None),
    user: User = Depends(agent_scope("tasks:write")),
    db: AsyncSession = Depends(get_db),
):
    operation = "submit:" + task_id
    previous, fingerprint = await idempotency(db, user, idempotency_key, operation, {"task_id": task_id})
    if previous:
        return public_record(await require(db, Task, previous.resource_id))
    task = await tasks.submit_for_approval(db, user, task_id)
    db.add(
        IdempotencyRecord(
            owner_id=user.id,
            key=idempotency_key,
            operation=operation,
            request_hash=fingerprint,
            resource_id=task.id,
        )
    )
    db.add(
        AgentToolCall(
            owner_id=user.id, key_id=request.state.key_id, tool="submit_task_for_approval", status="SUCCEEDED"
        )
    )
    return public_record(task)


@router.get("/agent/tasks/{task_id}/results")
async def agent_results(
    task_id: str, user: User = Depends(agent_scope("tasks:read")), db: AsyncSession = Depends(get_db)
):
    task = await require(db, Task, task_id)
    tasks.owner(task, user)
    return [
        public_record(row)
        for row in (await db.scalars(select(TaskSubmission).where(TaskSubmission.task_id == task_id))).all()
    ]


@router.post("/agent/messages", status_code=201)
async def agent_message(
    data: AgentMessage,
    idempotency_key: str | None = Header(None),
    user: User = Depends(agent_scope("messages:write")),
    db: AsyncSession = Depends(get_db),
):
    previous, fingerprint = await idempotency(db, user, idempotency_key, "message", data.model_dump())
    if previous:
        return public_record(await require(db, Message, previous.resource_id))
    task = await require(db, Task, data.task_id)
    tasks.owner(task, user)
    if not task.assigned_worker_id:
        raise HTTPException(409, "Messages require an assigned task")
    message = Message(task_id=task.id, sender_id=user.id, content=data.content)
    db.add(message)
    await db.flush()
    db.add(
        IdempotencyRecord(
            owner_id=user.id,
            key=idempotency_key,
            operation="message",
            request_hash=fingerprint,
            resource_id=message.id,
        )
    )
    tasks.notify(db, task.assigned_worker_id, "New message", task.id)
    return public_record(message)


@router.get("/agent/notifications")
async def agent_notifications(
    page: int = Query(1, ge=1),
    user: User = Depends(agent_scope("notifications:read")),
    db: AsyncSession = Depends(get_db),
):
    return [
        public_record(row)
        for row in (
            await db.scalars(
                select(Notification)
                .where(Notification.user_id == user.id)
                .order_by(Notification.created_at.desc())
                .offset((page - 1) * 20)
                .limit(20)
            )
        ).all()
    ]


@router.get("/tool-calls")
async def tool_calls(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return [
        public_record(row)
        for row in (
            await db.scalars(
                select(AgentToolCall)
                .where(AgentToolCall.owner_id == user.id)
                .order_by(AgentToolCall.created_at.desc())
                .limit(100)
            )
        ).all()
    ]


@router.get("/agent/workers")
async def agent_workers(
    q: str = Query("", max_length=100),
    city: str = Query("", max_length=80),
    page: int = Query(1, ge=1),
    user: User = Depends(agent_scope("workers:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.api.marketplace import workers

    return await workers(
        q=q, city=city, category="", max_rate=None, available=None, sort="recent", page=page, limit=20, db=db
    )


@router.get("/agent/workers/{worker_id}")
async def agent_worker(
    worker_id: str, user: User = Depends(agent_scope("workers:read")), db: AsyncSession = Depends(get_db)
):
    from app.api.marketplace import worker

    return await worker(worker_id, db)


@router.get("/agent/services")
async def agent_services(
    page: int = Query(1, ge=1),
    user: User = Depends(agent_scope("workers:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.api.marketplace import services

    return await services(worker_id=None, page=page, db=db)
