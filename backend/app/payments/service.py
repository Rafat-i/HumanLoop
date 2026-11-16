from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import get_settings
from app.models.entities import Payment, PaymentTransaction, Task, TaskApplication, TaskAssignment
from app.payments.providers import provider
from app.repositories.common import require
from app.services.tasks import audit, notify, owner


async def checkout(db, user, task_id):
    task = await require(db, Task, task_id, lock=True)
    owner(task, user)
    if task.status != "COMPLETED":
        raise HTTPException(409, "Approve completed work before payment")
    payment = await db.scalar(select(Payment).where(Payment.task_id == task.id))
    if payment and payment.status in ("SUCCEEDED", "REFUNDED"):
        raise HTTPException(409, "This task has already been paid")
    if not payment:
        assignment = await db.scalar(select(TaskAssignment).where(TaskAssignment.task_id == task.id))
        application = await require(db, TaskApplication, assignment.application_id)
        payment = Payment(
            task_id=task.id,
            owner_id=user.id,
            amount=application.compensation,
            currency=task.currency,
            provider=get_settings().payment_provider,
        )
        db.add(payment)
        await db.flush()
    result = await provider(payment.provider).checkout(payment)
    payment.provider_id = result["provider_id"]
    audit(db, user, "payment.checkout", payment.id)
    return payment, result


async def record_event(db, payment, event_id, status):
    if await db.scalar(select(PaymentTransaction).where(PaymentTransaction.event_id == event_id)):
        return
    if payment.status == "REFUNDED" or (payment.status == "SUCCEEDED" and status != "REFUNDED"):
        return
    payment.status = status
    task = await require(db, Task, payment.task_id, lock=True)
    task.payment_status = status
    db.add(PaymentTransaction(payment_id=payment.id, event_id=event_id, status=status))
    notify(
        db,
        task.owner_id,
        "Payment succeeded" if status == "SUCCEEDED" else "Payment " + status.lower(),
        task.id,
    )
    notify(db, task.assigned_worker_id, "Payment " + status.lower(), task.id)


async def simulate(db, user, payment_id):
    payment = await locked_payment(db, payment_id)
    if payment.owner_id != user.id:
        raise HTTPException(403, "Payment owner required")
    if payment.provider != "mock" or get_settings().environment == "production":
        raise HTTPException(403, "Simulation is available only for local mock payments")
    if payment.status == "REFUNDED":
        raise HTTPException(409, "Refunded payment cannot be charged again")
    await record_event(db, payment, f"mock_success_{payment.id}", "SUCCEEDED")
    return payment


async def refund(db, user, payment_id):
    payment = await locked_payment(db, payment_id)
    if payment.owner_id != user.id and "admin" not in user.roles:
        raise HTTPException(403, "Payment owner required")
    if payment.status != "SUCCEEDED":
        raise HTTPException(409, "Only successful payments can be refunded")
    result = await provider(payment.provider).refund(payment)
    if result["status"] != "succeeded":
        raise HTTPException(409, "Provider has not confirmed the refund")
    await record_event(db, payment, result["id"], "REFUNDED")
    audit(db, user, "payment.refund", payment.id)
    return payment


async def locked_payment(db, payment_id):
    payment = await require(db, Payment, payment_id)
    await require(db, Task, payment.task_id, lock=True)
    return await require(db, Payment, payment_id, lock=True)
