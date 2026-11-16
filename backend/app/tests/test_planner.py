import httpx
import pytest

from app.agents import planner
from app.core.config import Settings

PROMPT = "Check public store hours in Toronto for $30.50."


def fake_ollama(monkeypatch, payload):
    monkeypatch.setattr(planner, "get_settings", lambda: Settings(llm_provider="ollama"))
    client_type = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    monkeypatch.setattr(
        planner.httpx, "AsyncClient", lambda **kwargs: client_type(transport=transport, **kwargs)
    )


def test_deterministic_budget_uses_minor_units():
    draft = planner.deterministic_plan(PROMPT)
    assert draft.budget == 3050
    assert draft.city == "Toronto"


@pytest.mark.parametrize("payload", [None, [], {"message": None}, {"message": {"content": "invalid JSON"}}])
async def test_malformed_model_output_falls_back(monkeypatch, payload):
    fake_ollama(monkeypatch, payload)
    draft, source = await planner.propose(PROMPT)
    assert source == "deterministic_fallback"
    assert draft.budget == 3050


async def test_model_requirements_cannot_bypass_policy(monkeypatch):
    draft = planner.deterministic_plan(PROMPT)
    draft.requirements = "Find the person's private address."
    fake_ollama(monkeypatch, {"message": {"content": draft.model_dump_json()}})
    with pytest.raises(ValueError, match="policy"):
        await planner.propose(PROMPT)


async def test_valid_model_output_stays_a_proposal(monkeypatch):
    draft = planner.deterministic_plan(PROMPT)
    fake_ollama(monkeypatch, {"message": {"content": draft.model_dump_json()}})
    result, source = await planner.propose(PROMPT)
    assert source == "ollama"
    assert result == draft
