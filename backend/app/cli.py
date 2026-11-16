"""Development-only provisioning; passwords are supplied interactively, never seeded literals."""

import argparse
import asyncio
import getpass
import os

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionFactory, get_engine
from app.core.security import passwords
from app.models.entities import (
    Message,
    Payment,
    PaymentTransaction,
    Review,
    Service,
    Task,
    TaskApplication,
    TaskAssignment,
    TaskSubmission,
    User,
    WorkerProfile,
    now,
)


async def provision_admin(email, name, password):
    async with SessionFactory() as db:
        if await db.scalar(select(User).where(User.email == email.lower())):
            raise ValueError("Account already exists; refusing to silently grant administrator privileges")
        db.add(
            User(
                email=email.lower(),
                display_name=name,
                password_hash=passwords.hash(password),
                roles=["admin", "client"],
                email_verified=True,
                adult_confirmed=True,
            )
        )
        await db.commit()
    print("Development administrator created. No password was printed or stored in source.")


async def seed(password):
    settings = get_settings()
    if not settings.demo_mode:
        raise ValueError("Set DEMO_MODE=true explicitly before loading fictional records")
    async with SessionFactory() as db:
        if await db.scalar(select(User).where(User.email == "client@demo.humanloop.example")):
            print("Demo already exists; nothing changed.")
            return
        client = User(
            email="client@demo.humanloop.example",
            display_name="Demo Client",
            password_hash=passwords.hash(password),
            roles=["client"],
            adult_confirmed=True,
            email_verified=True,
            demo=True,
        )
        developer = User(
            email="developer@demo.humanloop.example",
            display_name="Demo Developer",
            password_hash=passwords.hash(password),
            roles=["client"],
            adult_confirmed=True,
            email_verified=True,
            demo=True,
        )
        db.add_all([client, developer])
        await db.flush()
        profiles = [
            (
                "Alex Morgan",
                "Montréal",
                "Retail checks",
                ["research", "retail", "french"],
                2500,
                "In-store stock checks with permitted shelf photos.",
            ),
            (
                "Sam Chen",
                "Toronto",
                "Photography",
                ["photography", "research"],
                4000,
                "Location photography with clear permission boundaries.",
            ),
            (
                "Jordan Ellis",
                "Ottawa",
                "Accessibility audits",
                ["accessibility", "research"],
                3500,
                "Entrance access observations, measurements and reports.",
            ),
        ]
        workers = []
        for index, (name, city, category, skills, rate, headline) in enumerate(profiles):
            worker = User(
                email=f"worker{index + 1}@demo.humanloop.example",
                display_name=name,
                password_hash=passwords.hash(password),
                roles=["worker"],
                adult_confirmed=True,
                email_verified=True,
                demo=True,
            )
            db.add(worker)
            await db.flush()
            profile = WorkerProfile(
                user_id=worker.id,
                display_name=name,
                headline=headline,
                bio=(
                    "Fictional demo profile. I compare product labels, sizes and shelf availability, and provide permitted photos with a concise report. No real service offer.",
                    "Fictional demo profile. I document public locations with permitted photography, careful framing and a written account of access restrictions. No real service offer.",
                    "Fictional demo profile. I record visible entrance features and access barriers without claiming a professional accessibility certification. No real service offer.",
                )[index],
                city=city,
                category=category,
                skills=skills,
                hourly_rate=rate,
                available=index != 2,
                published=True,
                review_status="APPROVED",
                identity_verified=False,
                demo=True,
            )
            db.add(profile)
            await db.flush()
            db.add(
                Service(
                    worker_id=profile.id,
                    title=f"Demonstration {category.lower()}",
                    description=(
                        "Fictional demo: verify a specified product in store; submit permitted shelf photos and a concise availability report. No purchase.",
                        "Fictional demo: photograph a public mural with permission.",
                        "Fictional demo: document publicly visible entrance features.",
                    )[index],
                    price=rate,
                )
            )
            workers.append(worker)
        for title, category, city, budget in [
            ("Verify a specified product on a retail shelf", "Retail checks", "Montréal", 3000),
            ("Photograph a public mural in daylight", "Photography", "Toronto", 6000),
            ("Document publicly visible entrance features", "Accessibility audits", "Ottawa", 4500),
        ]:
            db.add(
                Task(
                    owner_id=client.id,
                    title=title,
                    description="Fictional demonstration task. Observe public information only, obtain any necessary permission, and submit a short written report. Do not visit a location for this demo.",
                    category=category,
                    required_skills=["research"],
                    city=city,
                    budget=budget,
                    currency="CAD",
                    expected_minutes=60,
                    status="OPEN",
                    demo=True,
                )
            )
        completed = Task(
            owner_id=client.id,
            assigned_worker_id=workers[0].id,
            title="Demo: document public store hours",
            description="Fictional completed task for demonstrating the full workflow. No actual work occurred.",
            category="Retail checks",
            required_skills=["research"],
            city="Montréal",
            budget=3000,
            currency="CAD",
            expected_minutes=60,
            status="COMPLETED",
            payment_status="SUCCEEDED",
            demo=True,
        )
        db.add(completed)
        await db.flush()
        application = TaskApplication(
            task_id=completed.id,
            worker_id=workers[0].id,
            proposal="Fictional proposal: provide a clear public-information report.",
            compensation=3000,
            estimated_minutes=60,
            status="ACCEPTED",
        )
        db.add(application)
        await db.flush()
        db.add(
            TaskAssignment(
                task_id=completed.id,
                worker_id=workers[0].id,
                application_id=application.id,
                accepted_at=now(),
            )
        )
        db.add(
            TaskSubmission(
                task_id=completed.id,
                worker_id=workers[0].id,
                report="Fictional demo report: this illustrates a reviewed deliverable; no real observation took place.",
            )
        )
        db.add(
            Message(
                task_id=completed.id,
                sender_id=client.id,
                content="Demo message: please document only publicly displayed information.",
            )
        )
        db.add(
            Review(
                task_id=completed.id,
                reviewer_id=client.id,
                worker_id=workers[0].id,
                rating=5,
                comment="Fictional demo review for this seeded completed task.",
            )
        )
        payment = Payment(
            task_id=completed.id,
            owner_id=client.id,
            amount=3000,
            currency="CAD",
            provider="mock",
            status="SUCCEEDED",
        )
        db.add(payment)
        await db.flush()
        payment.provider_id = f"mock_{payment.id}"
        db.add(PaymentTransaction(payment_id=payment.id, event_id=f"seed_{payment.id}", status="SUCCEEDED"))
        await db.commit()
    print(
        "Fictional demo data created. Accounts: client@demo.humanloop.example, developer@demo.humanloop.example, worker1@demo.humanloop.example through worker3@demo.humanloop.example. Use the password you supplied."
    )


async def run(args):
    if get_settings().environment != "development":
        raise ValueError("Provisioning and demo seeding are restricted to development")
    password = (
        os.environ[args.password_env]
        if args.password_env
        else getpass.getpass("Choose a password (12+ characters): ")
    )
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Password must contain 12 to 128 characters")
    if args.command == "admin":
        await provision_admin(args.email, args.name, password)
    else:
        await seed(password)
    await get_engine().dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="Development Admin")
    seed_parser = sub.add_parser("seed")
    admin.add_argument(
        "--password-env",
        help="Read a password from this environment variable; never pass a password as a CLI argument",
    )
    seed_parser.add_argument("--password-env")
    asyncio.run(run(parser.parse_args()))
