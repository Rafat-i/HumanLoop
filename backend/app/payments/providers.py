import asyncio
from abc import ABC, abstractmethod

import stripe

from app.core.config import get_settings


class PaymentProvider(ABC):
    @abstractmethod
    async def checkout(self, payment):
        raise NotImplementedError

    @abstractmethod
    async def refund(self, payment):
        raise NotImplementedError


class MockPaymentProvider(PaymentProvider):
    async def checkout(self, payment):
        return {"provider_id": f"mock_{payment.id}", "url": None, "simulated": True}

    async def refund(self, payment):
        return {"id": f"mock_refund_{payment.id}", "status": "succeeded"}


class StripeTestPaymentProvider(PaymentProvider):
    def __init__(self):
        self.settings = get_settings()
        if not self.settings.stripe_secret_key.startswith("sk_test_"):
            raise ValueError("A Stripe test key is required")

    async def checkout(self, payment):
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            api_key=self.settings.stripe_secret_key,
            idempotency_key=f"checkout_{payment.id}",
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": payment.currency.lower(),
                        "unit_amount": payment.amount,
                        "product_data": {"name": "HumanLoop task - test payment"},
                    },
                    "quantity": 1,
                }
            ],
            metadata={"payment_id": payment.id},
            success_url=self.settings.frontend_url + "/dashboard/payments?checkout=returned",
            cancel_url=self.settings.frontend_url + "/dashboard/payments?checkout=cancelled",
        )
        return {"provider_id": session.id, "url": session.url, "simulated": False}

    async def refund(self, payment):
        session = await asyncio.to_thread(
            stripe.checkout.Session.retrieve, payment.provider_id, api_key=self.settings.stripe_secret_key
        )
        refund = await asyncio.to_thread(
            stripe.Refund.create,
            payment_intent=session.payment_intent,
            api_key=self.settings.stripe_secret_key,
            idempotency_key=f"refund_{payment.id}",
        )
        return {"id": refund.id, "status": refund.status}


def provider(name):
    if name == "mock":
        return MockPaymentProvider()
    if name == "stripe_test":
        return StripeTestPaymentProvider()
    raise ValueError("Unknown payment provider")
