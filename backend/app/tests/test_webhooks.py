import hashlib
import hmac
import json
import time
from uuid import uuid4

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.entities import Payment, PaymentTransaction, Task


def signature(payload, secret):
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


async def test_stripe_signature_amount_and_replay(api_env, monkeypatch):
    secret = "whsec_" + uuid4().hex
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    get_settings.cache_clear()
    owner, user = await api_env["account"]("webhook@example.com")
    with api_env["factory"]() as db:
        task = Task(
            owner_id=user["id"],
            title="Webhook task",
            description="Test-only webhook task",
            category="Retail checks",
            city="Toronto",
            budget=3000,
            status="COMPLETED",
        )
        db.add(task)
        db.flush()
        payment = Payment(
            task_id=task.id,
            owner_id=user["id"],
            amount=3000,
            currency="CAD",
            provider="stripe_test",
            provider_id="cs_test_example",
        )
        db.add(payment)
        db.commit()
        payment_id = payment.id
    event = {
        "id": "evt_test_" + uuid4().hex,
        "type": "checkout.session.completed",
        "livemode": False,
        "data": {
            "object": {
                "id": "cs_test_example",
                "metadata": {"payment_id": payment_id},
                "amount_total": 3000,
                "currency": "cad",
                "payment_status": "paid",
            }
        },
    }
    payload = json.dumps(event).encode()
    path = "/api/v1/payments/stripe/webhook"
    assert (
        await owner.post(path, content=payload, headers={"stripe-signature": "invalid"})
    ).status_code == 400
    for _ in range(2):
        response = await owner.post(
            path, content=payload, headers={"stripe-signature": signature(payload, secret)}
        )
        assert response.status_code == 200, response.text
    with api_env["factory"]() as db:
        assert db.get(Payment, payment_id).status == "SUCCEEDED"
        assert db.scalar(select(func.count()).select_from(PaymentTransaction)) == 1
    event["data"]["object"]["amount_total"] = 1
    payload = json.dumps(event).encode()
    assert (
        await owner.post(path, content=payload, headers={"stripe-signature": signature(payload, secret)})
    ).status_code == 400
    event["livemode"] = True
    payload = json.dumps(event).encode()
    assert (
        await owner.post(path, content=payload, headers={"stripe-signature": signature(payload, secret)})
    ).status_code == 400
