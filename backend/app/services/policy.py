"""Pure domain rules shared by every human and agent entry point."""

import re
from enum import StrEnum

CATEGORIES = ("Retail checks", "Local research", "Photography", "Accessibility audits", "Translation")


class TaskState(StrEnum):
    DRAFT = "DRAFT"
    DELETED = "DELETED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    DISPUTED = "DISPUTED"


TRANSITIONS = {
    "DRAFT": {"PENDING_APPROVAL", "CANCELLED", "DELETED"},
    "DELETED": set(),
    "PENDING_APPROVAL": {"OPEN", "IN_REVIEW", "CANCELLED"},
    "OPEN": {"ASSIGNED", "IN_REVIEW", "CANCELLED"},
    "IN_REVIEW": {"OPEN", "CANCELLED"},
    "ASSIGNED": {"IN_PROGRESS", "CANCELLED", "DISPUTED"},
    "IN_PROGRESS": {"SUBMITTED", "DISPUTED"},
    "SUBMITTED": {"COMPLETED", "DISPUTED"},
    "DISPUTED": {"CANCELLED", "COMPLETED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


def validate_transition(current: str, target: str):
    if target not in TRANSITIONS.get(current, set()):
        raise ValueError(f"Cannot transition from {current} to {target}")


# This is a conservative first filter, not comprehensive moderation.
PROHIBITED = re.compile(
    r"\b(stalk|stalking|weapon|weapons|narcotics|doxx|doxxing|harass|harassment|trespass|trespassing|break in|home address|private address|buy alcohol|buy tobacco|sexual services|unauthorized access)\b",
    re.IGNORECASE,
)


def validate_task_policy(title: str, description: str, category: str):
    if category not in CATEGORIES:
        raise ValueError("Choose a supported low-risk category")
    if PROHIBITED.search(title + " " + description):
        raise ValueError("This request is outside the permitted marketplace policy")
