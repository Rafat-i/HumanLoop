from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import current_user, verified_user
from app.integrations.storage import MAX_BYTES, LocalPrivateStorage, validate_content
from app.models.entities import (
    Attachment,
    Message,
    Report,
    Review,
    Task,
    TaskApplication,
    TaskSubmission,
    User,
    now,
)
from app.repositories.common import public_record, require
from app.schemas.inputs import (
    ApplicationInput,
    MessageInput,
    ReasonInput,
    ReviewInput,
    SubmissionInput,
    TaskInput,
)
from app.services import tasks as service

router = APIRouter(tags=["Tasks"])


@router.get("/tasks")
async def task_list(
    q: str = Query("", max_length=100),
    category: str = "",
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(Task).where(Task.visibility == "PUBLIC", Task.status == "OPEN")
    if q:
        query = query.where(Task.title.ilike("%" + q.replace("%", r"\%").replace("_", r"\_") + "%"))
    if category:
        query = query.where(Task.category == category)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(
            query.order_by(Task.created_at.desc(), Task.id).offset((page - 1) * limit).limit(limit)
        )
    ).all()
    return {"items": [public_record(row) for row in rows], "total": total, "page": page, "limit": limit}


@router.get("/my/tasks")
async def my_tasks(
    user: User = Depends(current_user), page: int = Query(1, ge=1), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.scalars(
            select(Task)
            .where(or_(Task.owner_id == user.id, Task.assigned_worker_id == user.id))
            .where(Task.status != "DELETED")
            .order_by(Task.created_at.desc())
            .offset((page - 1) * 50)
            .limit(50)
        )
    ).all()
    return [public_record(row) for row in rows]


@router.get("/my/applications")
async def my_applications(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.scalars(
            select(TaskApplication)
            .where(TaskApplication.worker_id == user.id)
            .order_by(TaskApplication.created_at.desc())
            .limit(100)
        )
    ).all()
    return [public_record(row) for row in rows]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    task = await require(db, Task, task_id)
    service.readable(task, user)
    return public_record(task)


@router.post("/tasks", status_code=201)
async def create_task(
    data: TaskInput, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    return public_record(await service.create_task(db, user, data))


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_draft(task_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    await service.delete_draft(db, user, task_id)


@router.put("/tasks/{task_id}")
async def update_draft(
    task_id: str,
    data: TaskInput,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
):
    return public_record(await service.update_draft(db, user, task_id, data))


@router.post("/tasks/{task_id}/submit-for-approval")
async def submit_for_approval(
    task_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    return public_record(await service.submit_for_approval(db, user, task_id))


@router.post("/tasks/{task_id}/publish")
async def publish(task_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    return public_record(await service.publish(db, user, task_id))


@router.post("/tasks/{task_id}/applications", status_code=201)
async def apply(
    task_id: str,
    data: ApplicationInput,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
):
    return public_record(await service.apply(db, user, task_id, data))


@router.get("/tasks/{task_id}/applications")
async def applications(task_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    task = await require(db, Task, task_id)
    service.owner(task, user)
    rows = (
        await db.scalars(
            select(TaskApplication)
            .where(TaskApplication.task_id == task.id)
            .order_by(TaskApplication.created_at)
            .limit(100)
        )
    ).all()
    return [public_record(row) for row in rows]


@router.post("/tasks/{task_id}/applications/{application_id}/accept")
async def accept(
    task_id: str, application_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    return public_record(await service.accept_application(db, user, task_id, application_id))


@router.post("/applications/{application_id}/withdraw")
async def withdraw(
    application_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    application = await require(db, TaskApplication, application_id, lock=True)
    if application.worker_id != user.id:
        raise HTTPException(403, "Application owner required")
    if application.status != "PENDING":
        raise HTTPException(409, "Only pending applications may be withdrawn")
    application.status = "WITHDRAWN"
    return public_record(application)


@router.post("/tasks/{task_id}/start")
async def start(task_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    return public_record(await service.start_work(db, user, task_id))


@router.post("/tasks/{task_id}/results")
async def results(
    task_id: str,
    data: SubmissionInput,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
):
    return public_record(await service.submit_result(db, user, task_id, data))


@router.get("/tasks/{task_id}/results")
async def get_results(task_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    task = await require(db, Task, task_id)
    service.participant(task, user)
    return [
        public_record(row)
        for row in (
            await db.scalars(
                select(TaskSubmission)
                .where(TaskSubmission.task_id == task.id)
                .order_by(TaskSubmission.created_at)
            )
        ).all()
    ]


@router.post("/tasks/{task_id}/complete")
async def complete(task_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    return public_record(await service.complete(db, user, task_id))


@router.post("/tasks/{task_id}/cancel")
async def cancel(task_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    return public_record(await service.cancel(db, user, task_id))


@router.post("/tasks/{task_id}/dispute")
async def dispute(
    task_id: str, data: ReasonInput, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    return public_record(await service.dispute(db, user, task_id, data.reason))


@router.post("/tasks/{task_id}/report", status_code=201)
async def report(
    task_id: str, data: ReasonInput, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    task = await require(db, Task, task_id)
    service.readable(task, user)
    record = Report(task_id=task_id, reporter_id=user.id, reason=data.reason)
    db.add(record)
    await db.flush()
    return public_record(record)


@router.get("/tasks/{task_id}/messages")
async def messages(
    task_id: str,
    page: int = Query(1, ge=1),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await require(db, Task, task_id)
    service.participant(task, user)
    rows = (
        await db.scalars(
            select(Message)
            .where(Message.task_id == task.id)
            .order_by(Message.created_at.desc())
            .offset((page - 1) * 50)
            .limit(50)
        )
    ).all()
    return [public_record(row) for row in reversed(rows)]


@router.post("/tasks/{task_id}/messages", status_code=201)
async def message(
    task_id: str, data: MessageInput, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    task = await require(db, Task, task_id)
    service.participant(task, user)
    if not task.assigned_worker_id:
        raise HTTPException(409, "Messages open after assignment")
    row = Message(task_id=task.id, sender_id=user.id, content=data.content)
    db.add(row)
    service.notify(
        db, task.assigned_worker_id if user.id == task.owner_id else task.owner_id, "New message", task.id
    )
    await db.flush()
    return public_record(row)


@router.post("/tasks/{task_id}/messages/read")
async def mark_read(task_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    service.participant(await require(db, Task, task_id), user)
    await db.execute(
        update(Message)
        .where(Message.task_id == task_id, Message.sender_id != user.id, Message.read_at.is_(None))
        .values(read_at=now())
    )
    return {"message": "Messages marked read"}


@router.post("/tasks/{task_id}/reviews", status_code=201)
async def review(
    task_id: str, data: ReviewInput, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    task = await require(db, Task, task_id, lock=True)
    service.owner(task, user)
    if task.status != "COMPLETED" or task.assigned_worker_id == user.id or not task.assigned_worker_id:
        raise HTTPException(409, "Only completed work can be reviewed")
    if await db.scalar(select(Review).where(Review.task_id == task.id)):
        raise HTTPException(409, "This task already has a review")
    row = Review(task_id=task.id, reviewer_id=user.id, worker_id=task.assigned_worker_id, **data.model_dump())
    db.add(row)
    await db.flush()
    return public_record(row)


@router.post("/tasks/{task_id}/attachments", status_code=201)
async def upload(
    task_id: str, request: Request, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    task = await require(db, Task, task_id)
    service.participant(task, user)
    if get_settings().environment == "production":
        raise HTTPException(503, "Production uploads require a malware scanner and private object store")
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            raise HTTPException(413, "Evidence must not exceed 5 MB")
        chunks.append(chunk)
    content = b"".join(chunks)
    content_type = request.headers.get("content-type", "").split(";")[0]
    validate_content(content, content_type)
    key = await LocalPrivateStorage().save(content)
    row = Attachment(
        task_id=task.id,
        uploader_id=user.id,
        storage_key=key,
        filename=Path(unquote(request.headers.get("x-filename", "evidence"))).name[:200],
        content_type=content_type,
        size=len(content),
    )
    db.add(row)
    await db.flush()
    return public_record(row, ("storage_key",))


@router.get("/tasks/{task_id}/attachments")
async def attachments(task_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    service.participant(await require(db, Task, task_id), user)
    return [
        public_record(row, ("storage_key",))
        for row in (
            await db.scalars(select(Attachment).where(Attachment.task_id == task_id).limit(100))
        ).all()
    ]


@router.get("/attachments/{attachment_id}")
async def download(
    attachment_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    attachment = await require(db, Attachment, attachment_id)
    service.participant(await require(db, Task, attachment.task_id), user)
    path = LocalPrivateStorage().path(attachment.storage_key)
    if not path.exists():
        raise HTTPException(404, "Evidence unavailable")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=attachment.filename,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
