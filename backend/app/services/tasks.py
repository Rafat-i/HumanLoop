from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import get_settings
from app.models.entities import (
    AuditLog,
    Dispute,
    Notification,
    Task,
    TaskApplication,
    TaskAssignment,
    TaskSubmission,
    User,
    WorkerProfile,
    now,
)
from app.repositories.common import require
from app.services.policy import validate_task_policy, validate_transition


def participant(task, user):
    if user.id not in (task.owner_id, task.assigned_worker_id) and "admin" not in user.roles:
        raise HTTPException(403, "Task participant access required")


def readable(task, user):
    if task.visibility != "PUBLIC" or task.status not in (
        "OPEN",
        "ASSIGNED",
        "IN_PROGRESS",
        "SUBMITTED",
        "COMPLETED",
    ):
        participant(task, user)


def owner(task, user):
    if task.owner_id != user.id:
        raise HTTPException(403, "Only the task owner can do this")


def notify(db, user_id, kind, task_id):
    if user_id:
        db.add(Notification(user_id=user_id, kind=kind, task_id=task_id))


def audit(db, user, action, resource_id, **details):
    db.add(AuditLog(actor_id=user.id, action=action, resource_id=resource_id, details=details))


def change_state(db, task, user, target):
    try:
        validate_transition(task.status, target)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    previous = task.status
    task.status = target
    audit(db, user, "task.transition", task.id, previous=previous, target=target)


async def create_task(db, user, data, agent=False):
    if "client" not in user.roles:
        raise HTTPException(403, "Enable the client role first")
    try:
        validate_task_policy(data.title, data.description + " " + data.requirements, data.category)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    task = Task(**data.model_dump(), owner_id=user.id, agent_created=agent, demo=get_settings().demo_mode)
    db.add(task)
    await db.flush()
    audit(db, user, "task.create", task.id, agent=agent)
    return task


async def update_draft(db, user, task_id, data):
    task = await require(db, Task, task_id, lock=True)
    owner(task, user)
    if task.status != "DRAFT":
        raise HTTPException(409, "Only drafts can be edited")
    try:
        validate_task_policy(data.title, data.description + " " + data.requirements, data.category)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    for field, value in data.model_dump().items():
        setattr(task, field, value)
    audit(db, user, "task.update_draft", task.id)
    await db.flush()
    return task


async def submit_for_approval(db, user, task_id):
    task = await require(db, Task, task_id, lock=True)
    owner(task, user)
    change_state(db, task, user, "PENDING_APPROVAL")
    notify(db, user.id, "Administrative review", task.id)
    return task


async def publish(db, user, task_id):
    task = await require(db, Task, task_id, lock=True)
    owner(task, user)
    if task.status != "PENDING_APPROVAL":
        raise HTTPException(409, "Only pending tasks can be published by their owner")
    settings = get_settings()
    if settings.environment == "production" or not settings.demo_mode:
        raise HTTPException(
            403, "Public bookings are disabled pending safety and legal review; use local demo mode"
        )
    validate_task_policy(task.title, task.description + " " + task.requirements, task.category)
    change_state(db, task, user, "OPEN")
    return task


async def apply(db, user, task_id, data):
    if "worker" not in user.roles:
        raise HTTPException(403, "Worker role required")
    task = await require(db, Task, task_id, lock=True)
    if task.owner_id == user.id:
        raise HTTPException(403, "You cannot apply for your own task")
    if task.status != "OPEN" or task.visibility != "PUBLIC":
        raise HTTPException(409, "Task is not accepting applications")
    profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == user.id))
    if not profile or profile.review_status != "APPROVED" or not profile.available:
        raise HTTPException(403, "An approved, available worker profile is required")
    if data.compensation > task.budget:
        raise HTTPException(422, "Proposal exceeds the task budget")
    if await db.scalar(
        select(TaskApplication).where(
            TaskApplication.task_id == task.id, TaskApplication.worker_id == user.id
        )
    ):
        raise HTTPException(409, "You already applied for this task")
    application = TaskApplication(task_id=task.id, worker_id=user.id, **data.model_dump())
    db.add(application)
    notify(db, task.owner_id, "New application", task.id)
    await db.flush()
    return application


async def accept_application(db, user, task_id, application_id):
    # All assignment contenders lock the same task before reading status.
    task = await require(db, Task, task_id, lock=True)
    owner(task, user)
    if task.status != "OPEN" or task.assigned_worker_id:
        raise HTTPException(409, "Task was already assigned or is no longer open")
    application = await require(db, TaskApplication, application_id, lock=True)
    if application.task_id != task.id or application.status != "PENDING":
        raise HTTPException(409, "Application is not eligible")
    if application.worker_id == user.id:
        raise HTTPException(403, "Self-assignment is prohibited")
    candidate = await require(db, User, application.worker_id)
    profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == candidate.id))
    if (
        candidate.suspended
        or not candidate.email_verified
        or not profile
        or profile.review_status != "APPROVED"
        or not profile.available
    ):
        raise HTTPException(409, "Worker is no longer eligible or available")
    task.assigned_worker_id = application.worker_id
    change_state(db, task, user, "ASSIGNED")
    db.add(TaskAssignment(task_id=task.id, worker_id=application.worker_id, application_id=application.id))
    others = (await db.scalars(select(TaskApplication).where(TaskApplication.task_id == task.id))).all()
    for item in others:
        if item.status == "PENDING":
            item.status = "ACCEPTED" if item.id == application.id else "REJECTED"
            notify(
                db,
                item.worker_id,
                "Application accepted" if item.id == application.id else "Application rejected",
                task.id,
            )
    return task


async def start_work(db, user, task_id):
    task = await require(db, Task, task_id, lock=True)
    if task.assigned_worker_id != user.id:
        raise HTTPException(403, "Only the assigned worker can accept and start")
    change_state(db, task, user, "IN_PROGRESS")
    assignment = await db.scalar(select(TaskAssignment).where(TaskAssignment.task_id == task.id))
    assignment.accepted_at = now()
    notify(db, task.owner_id, "Task assigned", task.id)
    return task


async def submit_result(db, user, task_id, data):
    task = await require(db, Task, task_id, lock=True)
    if task.assigned_worker_id != user.id:
        raise HTTPException(403, "Only the assigned worker may submit results")
    change_state(db, task, user, "SUBMITTED")
    db.add(TaskSubmission(task_id=task.id, worker_id=user.id, report=data.report))
    notify(db, task.owner_id, "Task submitted", task.id)
    return task


async def complete(db, user, task_id):
    task = await require(db, Task, task_id, lock=True)
    owner(task, user)
    if task.status != "SUBMITTED":
        raise HTTPException(409, "Only submitted work can be approved")
    change_state(db, task, user, "COMPLETED")
    notify(db, task.assigned_worker_id, "Task completed", task.id)
    return task


async def cancel(db, user, task_id):
    task = await require(db, Task, task_id, lock=True)
    participant(task, user)
    if user.id != task.owner_id and not (user.id == task.assigned_worker_id and task.status == "ASSIGNED"):
        raise HTTPException(403, "Only the owner or a worker declining an unstarted assignment can cancel")
    change_state(db, task, user, "CANCELLED")
    return task


async def dispute(db, user, task_id, reason):
    task = await require(db, Task, task_id, lock=True)
    participant(task, user)
    change_state(db, task, user, "DISPUTED")
    db.add(Dispute(task_id=task.id, opened_by=user.id, reason=reason))
    notify(db, task.owner_id, "Dispute opened", task.id)
    notify(db, task.assigned_worker_id, "Dispute opened", task.id)
    return task


async def delete_draft(db, user, task_id):
    task = await require(db, Task, task_id, lock=True)
    owner(task, user)
    if task.status != "DRAFT":
        raise HTTPException(409, "Only drafts can be deleted; cancel active tasks instead")
    # Retain audit and related records; resource lookups hide this tombstone.
    change_state(db, task, user, "DELETED")
    await db.flush()
