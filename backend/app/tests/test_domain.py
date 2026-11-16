import pytest
from pydantic import ValidationError

from app.agents.matching import score_worker
from app.schemas.inputs import Register, TaskInput
from app.services.policy import CATEGORIES, TRANSITIONS, validate_task_policy, validate_transition


def test_terminal_states_cannot_transition():
    for source in ("CANCELLED", "COMPLETED", "DELETED"):
        for target in TRANSITIONS:
            with pytest.raises(ValueError):
                validate_transition(source, target)


@pytest.mark.parametrize("source,target", [(s, t) for s, targets in TRANSITIONS.items() for t in targets])
def test_declared_transitions_are_valid(source, target):
    validate_transition(source, target)


@pytest.mark.parametrize(
    "description",
    ["Find a home address", "Stalking a person", "Buy alcohol", "Unauthorized access to a building"],
)
def test_policy_rejects_prohibited_tasks(description):
    with pytest.raises(ValueError):
        validate_task_policy("Task request", description, CATEGORIES[0])


def test_unsupported_category_rejected():
    with pytest.raises(ValueError):
        validate_task_policy("Task request", "A legitimate looking description", "Weapons")


def task():
    return {
        "required_skills": ["research", "french"],
        "city": "Montréal",
        "category": "Retail checks",
        "budget": 3000,
        "currency": "CAD",
        "expected_minutes": 60,
    }


def worker():
    return {
        "skills": ["research", "french"],
        "city": "Montreal",
        "category": "Retail checks",
        "hourly_rate": 2500,
        "currency": "CAD",
        "available": True,
    }


def test_matching_full_fit_with_neutral_new_worker_history():
    result = score_worker(task(), worker())
    assert result["score"] == 95
    assert result["dimensions"]["location"] == 1
    assert "neutral" in result["explanations"][-1]


def test_matching_history_and_budget_and_currency():
    assert score_worker(task(), worker(), completed=10, assigned=10)["score"] == 100
    poor = {**worker(), "available": False, "currency": "USD", "city": "Ottawa", "skills": []}
    assert score_worker(task(), poor, completed=0, assigned=10)["score"] == 0
    expensive = score_worker(task(), {**worker(), "hourly_rate": 6000})
    assert expensive["dimensions"]["budget"] == 0.5


def test_matching_empty_skills_and_zero_rate_remain_bounded():
    result = score_worker({**task(), "required_skills": []}, {**worker(), "hourly_rate": 0})
    assert 0 <= result["score"] <= 100
    assert result["dimensions"]["budget"] == 0


def test_matching_invalid_weights_rejected():
    with pytest.raises(ValueError):
        score_worker(task(), worker(), weights={"skills": 1})


def test_registration_cannot_claim_admin_or_underage():
    data = {
        "email": "person@example.com",
        "password": "a-long-test-password",
        "display_name": "Person",
        "role": "admin",
        "adult_confirmed": True,
    }
    with pytest.raises(ValidationError):
        Register.model_validate(data)
    with pytest.raises(ValidationError):
        Register.model_validate({**data, "role": "worker", "adult_confirmed": False})


def test_money_requires_integer_minor_units():
    data = {
        "title": "A lawful task",
        "description": "A clear public information request.",
        "category": "Retail checks",
        "city": "Toronto",
        "budget": 30.25,
    }
    with pytest.raises(ValidationError):
        TaskInput.model_validate(data)
