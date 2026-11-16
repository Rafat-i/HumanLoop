from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import current_user, verified_user
from app.models.entities import Bookmark, Review, Service, Task, User, WorkerProfile
from app.repositories.common import public_record, require
from app.schemas.inputs import ServiceInput, WorkerInput
from app.services.policy import CATEGORIES
from app.services.tasks import audit

router = APIRouter(tags=["Marketplace"])


def validate_worker_id(value: str) -> str:
    """Reject malformed UUIDs before PostgreSQL driver conversion."""
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise HTTPException(422, "Invalid worker identifier") from exc


def visible_workers():
    return (
        select(WorkerProfile)
        .join(User, User.id == WorkerProfile.user_id)
        .where(
            WorkerProfile.published.is_(True),
            WorkerProfile.review_status == "APPROVED",
            User.suspended.is_(False),
        )
    )


async def enrich(db, workers):
    ids = [w.user_id for w in workers]
    ratings = {
        row[0]: (row[1], row[2])
        for row in (
            await db.execute(
                select(Review.worker_id, func.avg(Review.rating), func.count())
                .where(Review.worker_id.in_(ids), Review.hidden.is_(False))
                .group_by(Review.worker_id)
            )
        ).all()
    }
    completed = dict(
        (
            await db.execute(
                select(Task.assigned_worker_id, func.count())
                .where(Task.assigned_worker_id.in_(ids), Task.status == "COMPLETED")
                .group_by(Task.assigned_worker_id)
            )
        ).all()
    )
    return [
        {
            **public_record(w),
            "rating": float(ratings[w.user_id][0]) if w.user_id in ratings else None,
            "review_count": ratings.get(w.user_id, (0, 0))[1],
            "completed_tasks": completed.get(w.user_id, 0),
        }
        for w in workers
    ]


@router.get("/categories")
async def categories():
    return list(CATEGORIES)


@router.get("/workers/showcase")
async def showcase(db: AsyncSession = Depends(get_db)):
    query = visible_workers()
    if get_settings().demo_mode:
        # Curated fictional seed accounts, never test-generated profiles or fake traction.
        query = query.where(User.email.in_([f"worker{n}@demo.humanloop.example" for n in range(1, 4)]))
    rows = (await db.scalars(query.order_by(WorkerProfile.display_name).limit(3))).all()
    return await enrich(db, rows)


@router.get("/workers")
async def workers(
    q: str = Query("", max_length=100),
    city: str = Query("", max_length=80),
    category: str = "",
    max_rate: int | None = Query(None, ge=100),
    available: bool | None = None,
    sort: str = "recent",
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = visible_workers()
    if q:
        term = "%" + q.replace("%", r"\%").replace("_", r"\_") + "%"
        query = query.where(
            or_(
                WorkerProfile.display_name.ilike(term),
                cast(WorkerProfile.skills, String).ilike(term),
                WorkerProfile.headline.ilike(term),
            )
        )
    if city:
        query = query.where(func.lower(WorkerProfile.city) == city.lower())
    if category:
        query = query.where(WorkerProfile.category == category)
    if max_rate is not None:
        query = query.where(WorkerProfile.hourly_rate <= max_rate)
    if available is not None:
        query = query.where(WorkerProfile.available == available)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    order = {
        "rate_asc": WorkerProfile.hourly_rate.asc(),
        "rate_desc": WorkerProfile.hourly_rate.desc(),
        "recent": WorkerProfile.created_at.desc(),
    }.get(sort)
    if order is None:
        raise HTTPException(422, "Unsupported sort")
    rows = (
        await db.scalars(query.order_by(order, WorkerProfile.id).offset((page - 1) * limit).limit(limit))
    ).all()
    return {"items": await enrich(db, rows), "total": total, "page": page, "limit": limit}


@router.get("/workers/{worker_id}")
async def worker(worker_id: str, db: AsyncSession = Depends(get_db)):
    worker_id = validate_worker_id(worker_id)
    profile = await db.scalar(visible_workers().where(WorkerProfile.id == worker_id))
    if not profile:
        raise HTTPException(404, "Worker not found")
    return (await enrich(db, [profile]))[0]


@router.get("/workers/{worker_id}/reviews")
async def reviews(worker_id: str, page: int = Query(1, ge=1), db: AsyncSession = Depends(get_db)):
    worker_id = validate_worker_id(worker_id)
    profile = await db.scalar(visible_workers().where(WorkerProfile.id == worker_id))
    if not profile:
        raise HTTPException(404, "Worker not found")
    rows = (
        await db.scalars(
            select(Review)
            .where(Review.worker_id == profile.user_id, Review.hidden.is_(False))
            .order_by(Review.created_at.desc())
            .offset((page - 1) * 20)
            .limit(20)
        )
    ).all()
    return [public_record(row, ("reviewer_id",)) for row in rows]


@router.get("/profile")
async def profile(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == user.id))
    return public_record(row) if row else None


@router.put("/profile")
async def update_profile(
    data: WorkerInput, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    if "worker" not in user.roles:
        raise HTTPException(403, "Worker role required")
    profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == user.id).with_for_update())
    if not profile:
        profile = WorkerProfile(user_id=user.id)
        db.add(profile)
    # Editing public content requires a new review; availability alone does not.
    content_changed = any(
        getattr(profile, key, None) != value
        for key, value in data.model_dump().items()
        if key not in ("available", "published")
    )
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    if content_changed:
        profile.review_status = "PENDING"
    await db.flush()
    audit(db, user, "profile.update", profile.id)
    return public_record(profile)


@router.get("/services")
async def services(
    worker_id: str | None = None, page: int = Query(1, ge=1), db: AsyncSession = Depends(get_db)
):
    query = (
        select(Service)
        .join(WorkerProfile, Service.worker_id == WorkerProfile.id)
        .join(User, User.id == WorkerProfile.user_id)
        .where(
            WorkerProfile.published.is_(True),
            WorkerProfile.review_status == "APPROVED",
            User.suspended.is_(False),
        )
    )
    if worker_id:
        query = query.where(Service.worker_id == validate_worker_id(worker_id))
    return [
        public_record(row)
        for row in (
            await db.scalars(query.order_by(Service.created_at.desc()).offset((page - 1) * 20).limit(20))
        ).all()
    ]


@router.post("/services", status_code=201)
async def create_service(
    data: ServiceInput, user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
):
    profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == user.id))
    if not profile:
        raise HTTPException(409, "Create a worker profile first")
    service = Service(worker_id=profile.id, **data.model_dump())
    db.add(service)
    profile.review_status = "PENDING"
    await db.flush()
    return public_record(service)


@router.get("/bookmarks")
async def bookmarks(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    query = (
        visible_workers()
        .join(Bookmark, Bookmark.worker_id == WorkerProfile.id)
        .where(Bookmark.user_id == user.id)
    )
    return await enrich(db, (await db.scalars(query)).all())


@router.put("/bookmarks/{worker_id}")
async def bookmark(worker_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await require(db, WorkerProfile, worker_id)
    if not await db.scalar(
        select(Bookmark).where(Bookmark.user_id == user.id, Bookmark.worker_id == worker_id)
    ):
        db.add(Bookmark(user_id=user.id, worker_id=worker_id))
    return {"message": "Worker saved"}


@router.delete("/bookmarks/{worker_id}")
async def unbookmark(worker_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Bookmark).where(Bookmark.user_id == user.id, Bookmark.worker_id == worker_id))
    return {"message": "Bookmark removed"}
