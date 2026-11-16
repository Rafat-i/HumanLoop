import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import current_user, verified_user
from app.models.entities import Payment, Task, User
from app.payments import service
from app.repositories.common import public_record

router = APIRouter(tags=["Test payments"])


@router.get("/payments")
async def payments(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.scalars(
            select(Payment)
            .join(Task, Payment.task_id == Task.id)
            .where(or_(Payment.owner_id == user.id, Task.assigned_worker_id == user.id))
            .order_by(Payment.created_at.desc())
            .limit(100)
        )
    ).all()
    return [public_record(row) for row in rows]


@router.post("/tasks/{task_id}/checkout")
async def checkout(task_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    payment, result = await service.checkout(db, user, task_id)
    return {"payment": public_record(payment), **result}


@router.post("/payments/{payment_id}/simulate")
async def simulate(payment_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    return public_record(await service.simulate(db, user, payment_id))


@router.post("/payments/{payment_id}/refund")
async def refund(payment_id: str, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)):
    return public_record(await service.refund(db, user, payment_id))


@router.post("/payments/stripe/webhook")
async def webhook(request: Request, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Stripe webhook is not configured")
    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            body, request.headers.get("stripe-signature", ""), settings.stripe_webhook_secret
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(400, "Invalid webhook signature") from exc
    if event.get("livemode"):
        raise HTTPException(400, "Live payments are not supported")
    if event["type"] not in (
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
    ):
        return {"received": True}
    session = event["data"]["object"]
    payment_id = session.get("metadata", {}).get("payment_id")
    if not payment_id:
        raise HTTPException(400, "Missing payment reference")
    payment = await service.locked_payment(db, payment_id)
    if payment.provider != "stripe_test" or payment.provider_id != session["id"]:
        raise HTTPException(400, "Payment reference mismatch")
    if (
        session.get("amount_total") != payment.amount
        or session.get("currency", "").upper() != payment.currency
    ):
        raise HTTPException(400, "Payment amount or currency mismatch")
    if session.get("payment_status") == "paid":
        await service.record_event(db, payment, event["id"], "SUCCEEDED")
    elif event["type"] == "checkout.session.async_payment_failed":
        await service.record_event(db, payment, event["id"], "FAILED")
    return {"received": True}
